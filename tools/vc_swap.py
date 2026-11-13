"""台詞換字（不重拍影片）：H3 念錯一兩個字時，把那個字換成 Ming 用角色參考音念的正確字，接回原位置。整句長度、每個字的時間都不變 → 嘴型照樣對。
改寫自上游 tools/vc_swap.py（上游 96a6b0f，2026-11-07；3d0dc4b 補用法）。與上游不同：
  - Ming 走本分支的 ming_batch.py＋voice_pick.py（同 make_ming.cmd），文字照樣過讀音替換表、繁轉簡、「著」改「着」。
  - 分人聲用 audio_separator API（同 h3_line_harvest.py），聽寫走 stt.load_asr()，音高走 pron_check.f0_track（沒有 parselmouth 時用 librosa）。
  - 只接字（移調＋拉長＋音量對齊＋交叉淡化）。上游接完還會整句換聲（cosy_vc.py，要 BreezyVoice 環境）抹平音色與接縫，
    本分支沒有 BreezyVoice，不移植；也不量 CAM++「像角色」。
  - 重混時人聲與背景照原音量相加（不做 loudnorm，make_film.py 的 cut 會統一響度）。
  - 可用 "who" 從 film.json 帶出角色參考音與 voice_sample。

用法（Voice venv）：
  "%PY_VOICE%" <repo>\\tools\\vc_swap.py job.json
接進 make_film.py：把 work/h3/<鏡>/clip.mp4 改名 clip_h3.mp4 當 src、out 寫回 work/h3/<鏡>/clip.mp4 → 再跑 make_film.py h3
（鏡頭不重拍，結尾的 h3_line_harvest 看到 clip 比較新會重新聽寫比對）→ edl、cut。
job.json（相對路徑以 job.json 所在資料夾為準）：
  {"src": "work/h3/S3/clip.mp4",          # 影片（自動分人聲／背景，做完重混換回影片）或乾淨人聲 .wav
   "line": "我站在桌上。他看著我說，先下來。",  # 來源「實際念的」字（含標點；念錯的字照正確字寫，用來對齊）
   "who": "liu",                           # 選填：film.json 的 chars 代號（vo＝旁白）或 battle.json 的 K（DJ），往上找設定檔
                                           #   → ref 預設 work/voice/ref_<who>.wav、ref_text＝voice_sample
   "ref": "work/voice/ref_liu.wav",        # 角色參考音（有 who 時可省）
   "ref_text": "...",                      # 參考音逐字稿（有 who 時可省；也會找 ref 旁的 voice_profile.json）
   "swaps": [{"at": "桌上", "char": "上",   # 用 line 裡的片段定位（片段要唯一；char 預設＝片段最後一字）
              "tts": "我站在桌上。",          # 選填：Ming 要念的句子，預設＝line 裡含這個字的那一小句
              "tts_at": "桌上", "tts_char": "上"}],   # 選填：同音字技巧時（tts 寫「交學」）指定 tts 裡要切的字
   "out": "work/h3/S3/clip_fixed.mp4",     # .mp4（影片）或 .wav（人聲）
   "work": "選填，預設 <out 檔名>_vcswap/"}

流程：
  1. 影片 → BS-RoFormer 分出人聲／背景。
  2. 找字的位置：MMS 強制對齊（pron_check.align）逐字找起訖 → 用音量修邊界
     （起點＝MMS 起點前 80 毫秒內最安靜的地方；後面接停頓時，終點延到音量比該字最大聲低 25 dB 為止）。
  3. Ming（角色參考音克隆、4 seed、voice_pick 自動挑）念 tts → 同樣方法找到要切的字。
  4. 切下 Ming 的字 → 照前後字的音高比例移調（Ming 的音域常跟來源不同，上游實測 +10 半音）→ 拉成原本那格的長度 → 音量對齊 → 12 毫秒交叉淡化接回。
  5. 跟背景重混 → 換回影片。
  6. 報告 <work>/report.json：每個換的字的位置、拉長倍率、移調、聲調判定前後（pron_check）、整句聽寫前後、長度是否不變。
限制與用法（上游實測）：
  - 只修「聲音」。換成嘴型差很多的字（號→日）要看畫面；聲調、破音字、腔調這類嘴型幾乎一樣的最適合。
  - 連前一字一起換才不殘留原音；喊的句子挑同音字，讓聽寫與強制對齊都對。
  - 聲調看起來低降先別判錯：用同一個聲音念兩種音當對照。
  - 拉長倍率超出 0.7–1.4、要大幅移調或斷聲，就改整句 fixed 重念（make_film.py 該句 "voice_mode": "fixed"）。
  - 結果一定要人聽接縫。"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["PYTHONIOENCODING"] = "utf-8"
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import pron_check as pc  # noqa: E402

AI = Path(os.environ.get("AI_ROOT", r"C:\AI"))
SEP_DIR = AI / "Voice" / "models" / "separator"
SEP_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
XF = 0.012          # 交叉淡化（秒）
PUNCT = "。，！？、；：…,.!?;:「」『』（）()—～~ "


def run(*a, **k):
    subprocess.run([str(x) for x in a], check=True, **k)


def hanzi(text):
    """line 裡的漢字（跟 pron_check.expected 的 chars 一一對應）＋每個漢字後面是不是標點（停頓）。"""
    chars, pause = [], []
    for c in text:
        if "\u4e00" <= c <= "\u9fff" or c.isdigit():
            chars.append(c); pause.append(False)
        elif chars and c in PUNCT:
            pause[-1] = True
    return chars, pause


def locate(chars, at, ch):
    s = "".join(chars)
    i = s.find(at)
    if i < 0 or s.find(at, i + 1) >= 0:
        raise SystemExit(f"[vc_swap] 「{at}」在「{s}」裡找不到或不只一處，請把 at 寫長一點")
    j = at.find(ch) if ch else len(at) - 1
    if j < 0:
        raise SystemExit(f"[vc_swap] 「{ch}」不在「{at}」裡")
    return i + j


def intensity(x, sr):
    """10 毫秒一格的音量（dB）。"""
    hop = int(sr * 0.01)
    n = len(x) // hop
    fr = x[:n * hop].reshape(n, hop)
    return 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-6)


def spans(wav, text):
    """逐字（起, 終）秒；MMS 對齊後用音量修邊界，讓起點落在子音前的低點、停頓前的字包含整個收尾。"""
    import librosa
    x, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    x = x.mean(1)
    chars, base, _, _ = pc.expected(text)
    hz, pause = hanzi(text)
    if len(hz) != len(chars):
        raise SystemExit(f"[vc_swap] 字數對不上（{''.join(hz)} vs {''.join(chars)}）：line 裡的數字、英文請寫成國字")
    sp = pc.align(librosa.resample(x, orig_sr=sr, target_sr=16000), base)
    db = intensity(x, sr)
    out = []
    for k, (a, b) in enumerate(sp):
        prev_end = out[-1][1] if out else 0.0
        lo = max(prev_end, a - 0.08)
        f0, f1 = int(lo * 100), max(int(lo * 100) + 1, int(a * 100) + 1)
        a2 = (f0 + int(np.argmin(db[f0:f1]))) / 100 if f1 > f0 else a
        nxt = sp[k + 1][0] if k + 1 < len(sp) else len(x) / sr
        if pause[k] or k == len(sp) - 1:                 # 後面停頓：延到音量掉 25 dB
            peak = db[int(a * 100):max(int(a * 100) + 1, int(b * 100))].max()
            e = int(b * 100)
            while e < min(len(db) - 1, int(nxt * 100) - 2, int((b + 0.35) * 100)) and db[e] > peak - 25:
                e += 1
            b2 = e / 100
        else:                                            # 後面緊接下一字：切在兩字之間最安靜的地方
            g0, g1 = int(b * 100), max(int(b * 100) + 1, int(nxt * 100))
            b2 = (g0 + int(np.argmin(db[g0:g1]))) / 100
        out.append((round(a2, 3), round(max(b2, a2 + 0.05), 3)))
    return chars, out


def local_f0(wav, a, b, win=0.6):
    """[a, b] 前後各 win 秒（不含本字）的濁音 F0 中位數＝這個字周圍的說話音域。"""
    t, f = pc.f0_track(wav)
    t, f = np.asarray(t), np.asarray(f)
    sel = (f > 0) & (((t >= a - win) & (t < a)) | ((t > b) & (t <= b + win)))
    return float(np.median(f[sel])) if sel.sum() >= 5 else None


def clause_of(line, idx):
    """line 裡含第 idx 個漢字的那一小句（標點切開，保留句尾標點）。"""
    parts = re.findall(r"[^。，！？；：…,!?;:]+[。，！？；：…,!?;:]?", line)
    n = 0
    for p in parts:
        c = len(hanzi(p)[0])
        if n <= idx < n + c:
            return p.strip().rstrip("，,") + ("" if p.strip()[-1:] in "。！？" else "。")
        n += c
    return line


def separate(src, work):
    voc, bg = work / "src_vocal.wav", work / "src_bg.wav"
    if voc.exists() and bg.exists():
        return voc, bg
    wav = work / "src.wav"
    run("ffmpeg", "-y", "-v", "error", "-i", src, "-vn", "-ac", "2", "-ar", "44100", wav)
    from audio_separator.separator import Separator
    for f in work.glob("src_(*"):
        f.unlink()
    sep = Separator(model_file_dir=str(SEP_DIR), output_dir=str(work), output_format="WAV", log_level=40)
    sep.load_model(model_filename=SEP_MODEL)
    sep.separate(str(wav))
    next(work.glob("src_(Vocals)*.wav")).replace(voc)
    next(work.glob("src_(Instrumental)*.wav")).replace(bg)
    return voc, bg


def ming(work, items, ref, ref_text):
    """ming_batch.py 生 4 個候選（全被截斷時句尾改「……」再抽 4 個）→ voice_pick.py 挑 → <work>/ming/<name>.wav。"""
    jobs = {"out_dir": str(work / "ming"), "seeds": 4, "extra_seeds": 4,
            "jobs": [{"name": n, "text": t, "ref_audio": str(ref), "ref_text": ref_text} for n, t in items]}
    jp = work / "ming_jobs.json"
    jp.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8")
    run(sys.executable, TOOLS / "ming_batch.py", jp, stdin=subprocess.DEVNULL)
    run(sys.executable, TOOLS / "voice_pick.py", jp)
    res = {n: work / "ming" / f"{n}.wav" for n, _ in items}
    miss = [n for n, p in res.items() if not p.exists()]
    if miss:
        raise SystemExit(f"[vc_swap] Ming 沒挑出 {miss}（看 {work / 'ming' / 'picks.json'}），改 tts 寫法重跑")
    return res


def measure(wavs, line, idxs):
    """整句聽寫、換的字的聲調判定。"""
    from stt import DEFAULT_PROMPT, load_asr
    asr = load_asr()
    res = {}
    for name, p in wavs.items():
        segs, _ = asr.transcribe(str(p), language="zh", initial_prompt=DEFAULT_PROMPT)
        pr = pc.check(p, line)
        res[name] = {"asr": "".join(s.text for s in segs).strip(), "sec": round(sf.info(str(p)).duration, 3),
                     "chars": [{k: pr["chars"][i][k] for k in ("char", "pinyin", "tone", "verdict", "desc")} for i in idxs]}
    return res


def find_film(start):
    for d in [start, *start.parents]:
        for n in ("film.json", "battle.json"):
            if (d / n).exists():
                return d / n
    raise SystemExit(f"[vc_swap] 寫了 who 但從 {start} 往上找不到 film.json／battle.json")


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    jp = Path(sys.argv[1]).resolve()
    job = json.loads(jp.read_text(encoding="utf-8-sig"))
    P = lambda v: Path(v) if Path(v).is_absolute() else (jp.parent / v).resolve()  # noqa: E731
    ref, ref_text = (P(job["ref"]) if job.get("ref") else None), job.get("ref_text")
    if job.get("who"):
        fj = find_film(jp.parent)
        F = json.loads(fj.read_text(encoding="utf-8"))
        ch = {**F.get("chars", {}), **({"vo": F["narrator"]} if F.get("narrator") else {}),
              **({"K": F["dj"]} if F.get("dj") else {})}.get(job["who"])     # battle.json 的 DJ＝K（參考音 work/voice/ref_K.wav）
        if ch is None:
            raise SystemExit(f"[vc_swap] {fj.name} 沒有「{job['who']}」（film.json 的 chars 代號、vo＝旁白；battle.json 的 K＝DJ）")
        ref = ref or fj.parent / "work" / "voice" / f"ref_{job['who']}.wav"
        ref_text = ref_text or ch.get("voice_sample")
    if ref is None or not ref.exists():
        raise SystemExit(f"[vc_swap] 找不到角色參考音 {ref}")
    if not ref_text and (ref.parent / "voice_profile.json").exists():
        ref_text = json.loads((ref.parent / "voice_profile.json").read_text(encoding="utf-8"))["reference_text"]
    if not ref_text:
        raise SystemExit("[vc_swap] 要 ref_text（參考音逐字稿），或寫 who 讓工具讀 film.json 的 voice_sample")
    src, out = P(job["src"]), P(job["out"])
    work = P(job["work"]) if job.get("work") else out.with_name(out.stem + "_vcswap")
    work.mkdir(parents=True, exist_ok=True)
    line = job["line"]
    is_video = src.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm")

    voc, bg = separate(src, work) if is_video else (src, None)
    chars, sp = spans(voc, line)
    print("[vc_swap] 來源逐字：" + " ".join(f"{c}{a:.2f}-{b:.2f}" for c, (a, b) in zip(chars, sp)))

    plan = []
    for k, s in enumerate(job["swaps"]):
        i = locate(chars, s["at"], s.get("char"))
        tts = s.get("tts") or clause_of(line, i)
        plan.append(dict(name=f"swap{k + 1}", idx=i, char=chars[i], tts=tts, tts_at=s.get("tts_at") or s["at"],
                         tts_char=s.get("tts_char") or s.get("char") or s["at"][-1]))
    wavs = ming(work, [(p["name"], p["tts"]) for p in plan], ref, ref_text)

    x, sr = sf.read(str(voc), dtype="float32", always_2d=True)
    y = x.copy()
    rms = lambda v: float(np.sqrt(np.mean(v ** 2)) + 1e-9)  # noqa: E731
    for p in plan:
        tchars, tsp = spans(wavs[p["name"]], p["tts"])
        ts = "".join(tchars)
        j0 = ts.find(p["tts_at"])
        j = (j0 + p["tts_at"].find(p["tts_char"])) if j0 >= 0 and p["tts_char"] in p["tts_at"] else ts.find(p["tts_char"])
        if j < 0:
            raise SystemExit(f"[vc_swap] tts「{p['tts']}」裡找不到「{p['tts_char']}」")
        (a, b), (c, d) = sp[p["idx"]], tsp[j]
        seg, fit = work / f"{p['name']}_cut.wav", work / f"{p['name']}_fit.wav"
        run("ffmpeg", "-y", "-v", "error", "-i", wavs[p["name"]], "-ss", max(0, c - XF), "-to", d + XF, "-ac", x.shape[1], "-ar", sr, seg)
        tempo = (d - c) / (b - a)
        # 音域對齊：Ming 的角色聲音可能比來源高或低（上游實測來源 106 Hz vs Ming 144 Hz）→ 照前後字的音高比例移調
        f_src, f_tts = local_f0(voc, a, b), local_f0(wavs[p["name"]], c, d)
        pitch = min(1.5, max(0.67, f_src / f_tts)) if f_src and f_tts else 1.0
        af = f"asetrate={int(sr * pitch)},aresample={sr},atempo={tempo / pitch:.4f}"
        run("ffmpeg", "-y", "-v", "error", "-i", seg, "-af", af, "-ar", sr, "-ac", x.shape[1], fit)
        p["pitch_shift_semitones"] = round(12 * np.log2(pitch), 1)
        new, _ = sf.read(str(fit), dtype="float32", always_2d=True)
        n0, n1 = int((a - XF) * sr), int((b + XF) * sr)
        new = np.pad(new, ((0, max(0, (n1 - n0) - len(new))), (0, 0)))[:n1 - n0]
        new *= rms(x[n0:n1]) / rms(new)
        m = int(XF * sr); ramp = np.linspace(0, 1, m)[:, None]
        new[:m] = y[n0:n0 + m] * (1 - ramp) + new[:m] * ramp
        new[-m:] = new[-m:] * (1 - ramp) + y[n1 - m:n1] * ramp
        y[n0:n1] = new
        p.update(src_span=[a, b], tts_span=[c, d], stretch=round(1 / tempo, 3))
        warn = "  ⚠ 倍率超出 0.7–1.4，可能不自然，考慮整句改 fixed" if not 0.7 <= 1 / tempo <= 1.4 else ""
        if abs(p["pitch_shift_semitones"]) >= 6:
            warn += "  ⚠ 移調很大，聽接縫；不自然就整句改 fixed"
        print(f"[vc_swap] {p['char']}：來源 {a:.2f}-{b:.2f}  ←  Ming「{p['tts']}」{c:.2f}-{d:.2f}  拉長 ×{1 / tempo:.2f}"
              f"  移調 {p['pitch_shift_semitones']:+} 半音{warn}")
    spliced = work / "vocal_spliced.wav"
    sf.write(str(spliced), y, sr)

    final = spliced

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".wav":
        run("ffmpeg", "-y", "-v", "error", "-i", final, out)
    elif is_video:
        # 人聲照原音量放回背景（不做 loudnorm：clip 的音量要跟其他鏡一致，響度交給 make_film.py 的 cut）
        flt = ("[1:a]aresample=48000,aformat=channel_layouts=stereo[v];[2:a]aresample=48000,aformat=channel_layouts=stereo[b];"
               "[v][b]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.97:level=false[a]")
        run("ffmpeg", "-y", "-v", "error", "-i", src, "-i", final, "-i", bg, "-filter_complex", flt,
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", out)
    else:
        raise SystemExit("[vc_swap] 來源是 wav 時 out 也要是 .wav")

    rep = {"src": str(src), "out": str(out), "line": line, "swaps": plan,
           "measure": measure({"before": voc, "after": final}, line, [p["idx"] for p in plan])}
    rep["length_same"] = abs(rep["measure"]["before"]["sec"] - rep["measure"]["after"]["sec"]) < 0.05
    (work / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for k in ("before", "after"):
        mm = rep["measure"][k]
        print(f"[vc_swap] {k}: 聽寫「{mm['asr']}」  長度 {mm['sec']}s  " +
              " ".join(f"{c['char']}({c['pinyin']}→{c['tone']}聲 {c['verdict']} {c['desc']})" for c in mm["chars"]))
    print(f"[vc_swap] 完成 {out}（長度不變 {rep['length_same']}）；報告 {work / 'report.json'}；接縫一定要人聽")


if __name__ == "__main__":
    main()
