"""配音候選自動挑選（Voice venv）：挑 voxcpm_batch.py 生的候選。2026-10-07 建立。
比對與 edge-tts 答案卷都用「套過讀音替換表（tts-lexicon.md）的台詞」，跟 voxcpm_batch.py 實際念的一致。
每句的所有 seed 候選：
  1. faster-whisper large-v3 聽寫，必須和台詞逐字相同（數字、標點、注音標記不計）才算合格；
  2. 長度要在 edge-tts 台灣國語參考音的 0.5–2.5 倍之間（擋掉拖長、亂音）；
  3. 音量音質：響度（LUFS）跟同角色所有候選的中位數差 ≤ 6 dB，4 kHz 以上能量比不異常高（嘶聲）（2026-10-19 加：
     〈歐幾里得的完美數〉自動挑到大 10 dB、音色不同與嘶聲的候選，旁白忽大忽小、音質不一被退件）；
  4. 合格者依 pron_compare（對照 edge-tts 台灣國語參考音的每字音高曲線）分數排序，同分取離響度中位數近、平均距離小的。
都不合格 → 取聽寫最接近的，標 needs_review（review_reason "asr"）；聽寫對的全都音量音質異常 → 照舊挑，標 needs_review（"sound"）。
picks.json 每個候選記 lufs、hf_4k、lufs_dev、sound_ok。已挑過的句子不改（H3 可能已照長度拍好），只補量數字；要重挑用 --rerank。
輸出 <out_dir>/<name>.wav（選中的那支，已去頭尾靜音：保留開頭 80 ms、結尾 150 ms）＋ <out_dir>/picks.json（全部候選分數）。
用法（同一個 cmd 視窗先 call <repo>\\configs\\profile.cmd）："%PY_VOICE%" <repo>\\tools\\voice_pick.py jobs.json
edge-tts 只產生參考音當「答案卷」，不進影片（要連網；微軟介面無公開授權）。job 給 "tw_ref"（自備參考音路徑）就不呼叫 edge-tts。"""
import difflib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stt import load_asr  # noqa: E402  (faster-whisper；裝不了時自動改 openai-whisper)
import soundfile as sf  # noqa: E402
import opencc  # noqa: E402
from pron_compare import compare  # noqa: E402
from tts_lexicon import load_lexicon, speakable  # noqa: E402

DIG = "零一二三四五六七八九"


def int_zh(n):
    if n < 10: return DIG[n]
    if n < 100:
        t, o = divmod(n, 10); return ("" if t == 1 else DIG[t]) + "十" + (DIG[o] if o else "")
    if n < 1000:
        h, r = divmod(n, 100)
        return DIG[h] + "百" + ("" if r == 0 else ("零" + DIG[r] if r < 10 else ("一" + int_zh(r) if r < 20 else int_zh(r))))
    return "".join(DIG[int(c)] for c in str(n))


def norm(s):
    s = re.sub(r"\[:[^\]]*\]", "", s)
    s = re.sub(r"\d+", lambda m: int_zh(int(m.group())), s)
    return re.sub(r"[^\u4e00-\u9fffA-Za-z]", "", s).upper()


def dur(p):
    """有聲長度（切掉頭尾靜音；edge-tts 會把刪節號念成長停頓，不切會誤判長度）"""
    import librosa
    x, sr = sf.read(str(p), dtype="float32"); x = x.mean(axis=1) if x.ndim > 1 else x
    y, _ = librosa.effects.trim(x, top_db=35); return max(len(y), 1) / sr


def py_same(a, b):
    """拼音＋聲調相同就算對（ASR 把「阿禾」寫成「阿和」、「課」寫成「客」不算錯；聲調不同仍算錯）"""
    if a == b:
        return True
    if re.search(r"[A-Za-z]", a + b):
        return False
    from pron_check import expected                 # 已套台灣讀音（TW_OVERRIDE，例：連假＝jia4，pypinyin 會標成三聲）
    f = lambda s: [(x, t) for _, x, t, _ in zip(*expected(s))]
    return f(a) == f(b)


def judge(r, plain, rd, cand_path):
    r["asr_ok"] = py_same(norm(r["asr"]), norm(plain))
    r["sim"] = round(difflib.SequenceMatcher(None, norm(r["asr"]), norm(plain)).ratio(), 3)
    r["len_ratio"] = round(dur(cand_path) / rd, 2)
    r["len_ok"] = 0.5 <= r["len_ratio"] <= 2.5
    return r


RERANK = "--rerank" in sys.argv      # 不重跑 ASR，只用 picks.json 裡的聽寫結果重新判定與排序
LUFS_DEV = 6.0                       # 跟同角色所有候選的響度中位數差超過這麼多 dB → 響度離群
HF_CUT, HF_MIN, HF_MUL = 4000, 0.30, 3.0   # 4 kHz 以上能量比 > max(0.30, 同角色中位數 × 3) → 嘶聲


def lufs(p):
    """整體響度（ffmpeg ebur128，跟 make_film.py 的 voice_lufs 同一把尺）；量不到（太短）回 None"""
    e = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(p), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    m = re.findall(r"I:\s*(-?[\d.]+) LUFS", e)
    return float(m[-1]) if m and float(m[-1]) > -70 else None


def hf_ratio(p):
    """4 kHz 以上能量佔全部能量的比例。正常人聲 0.01–0.2；嘶聲候選 0.5 以上（2026-10-19〈歐幾里得的完美數〉line12_s5 是 0.63）"""
    import numpy as np
    x, sr = sf.read(str(p), dtype="float32"); x = x.mean(axis=1) if x.ndim > 1 else x
    S = np.abs(np.fft.rfft(x)) ** 2; f = np.fft.rfftfreq(len(x), 1 / sr)
    return round(float(S[f >= HF_CUT].sum() / (S.sum() + 1e-12)), 3)


def measure(out, rows):
    for r in rows:                                   # 舊的 picks.json 沒有這兩欄：補量（不用重跑 ASR）
        if "lufs" not in r:
            r["lufs"] = lufs(out / "cand" / r["file"])
        if "hf_4k" not in r:
            r["hf_4k"] = hf_ratio(out / "cand" / r["file"])
    return rows


def role(j):
    """同角色＝同一個參考音（bv.json 沒寫 who 時看 ref_audio）"""
    return j.get("who") or Path(j.get("ref_audio", "")).stem or "all"


def sound_judge(rows, med_lufs, hf_lim):
    for r in rows:
        r["lufs_dev"] = None if r["lufs"] is None or med_lufs is None else round(r["lufs"] - med_lufs, 1)
        r["sound_ok"] = (r["lufs_dev"] is None or abs(r["lufs_dev"]) <= LUFS_DEV) and r["hf_4k"] <= hf_lim
    return rows


def main():
    import numpy as np
    spec_path = Path([a for a in sys.argv[1:] if not a.startswith("--")][0]).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    out = (spec_path.parent / spec.get("out_dir", "bv")).resolve()
    refdir = out / "edge_ref"; refdir.mkdir(exist_ok=True)
    picks_path = out / "picks.json"
    picks = json.loads(picks_path.read_text(encoding="utf-8")) if picks_path.exists() else {}
    asr, s2t, todo = None, opencc.OpenCC("s2twp"), []
    lex = load_lexicon(spec_path.parent)
    for j in spec["jobs"]:                           # 第一輪：每句候選聽寫、腔調、響度、高頻比
        name, plain = j["name"], re.sub(r"\[:[^\]]*\]", "", speakable(j["text"], lex))
        cands = sorted((out / "cand").glob(f"{name}_s*.wav"), key=lambda p: int(p.stem.rsplit("_s", 1)[1]))
        if not cands:
            print("[miss]", name); continue
        if name in picks and len(picks[name]["cands"]) == len(cands) and (out / f"{name}.wav").exists():
            rows = measure(out, picks[name]["cands"])
            if RERANK:
                rows = [judge(r, plain, dur(refdir / f"{name}.mp3"), out / "cand" / r["file"]) for r in rows]
            # 已挑過的不改（H3 可能已照它的長度拍好），只補量數字；audition.py 人工改挑的（manual）連 --rerank 也不改
            todo.append((j, rows, RERANK and not picks[name].get("manual"))); continue
        if asr is None:
            asr = load_asr("large-v3")
        ref = refdir / f"{name}.mp3"
        if j.get("tw_ref"):                              # 自備的台灣國語參考音（make_film.py 先用 gen_voice.py 的 edge-tts 做好；沒網路時用 VoxCPM2 播報聲音）
            tw = Path(j["tw_ref"]); tw = tw if tw.is_absolute() else spec_path.parent / tw
            if not ref.exists() or ref.stat().st_mtime < tw.stat().st_mtime:
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tw), str(ref)], check=True)
        elif not ref.exists() or ref.stat().st_size == 0:     # edge-tts 失敗會留下 0 位元組的檔
            subprocess.run([sys.executable, "-m", "edge_tts", "--voice", j.get("edge_voice", "zh-TW-YunJheNeural"), "--text", plain, "--write-media", str(ref)], check=True)
        rd = dur(ref)
        rows = []
        for c in cands:
            heard = s2t.convert("".join(s.text for s in asr.transcribe(str(c), language="zh", beam_size=5)[0]))
            r = judge({"file": c.name, "asr": heard}, plain, rd, c)
            try:
                cp = compare(str(c), str(ref), plain); r.update(tw_score=cp["score"], tw_dist=cp["mean_dist"], tw_bad=cp["bad"])
            except Exception as e:                       # 單字句等對不齊時不計腔調分
                r.update(tw_score=0.5, tw_dist=9.0, tw_err=str(e)[:80])
            rows.append(r)
        todo.append((j, measure(out, rows), True))
    groups = {}                                      # 第二輪：同角色所有候選的中位數當基準，再挑
    for j, rows, _ in todo:
        groups.setdefault(role(j), []).extend(rows)
    base = {}
    for k, rows in groups.items():
        ls = [r["lufs"] for r in rows if r["lufs"] is not None]
        base[k] = (float(np.median(ls)) if ls else None, max(HF_MIN, HF_MUL * float(np.median([r["hf_4k"] for r in rows]))))
        print(f"[base] {k} 響度中位數 {base[k][0] if base[k][0] is None else round(base[k][0], 1)} LUFS、高頻比上限 {base[k][1]:.2f}", flush=True)
    for j, rows, redo in todo:
        med, lim = base[role(j)]
        sound_judge(rows, med, lim)
        if redo:
            choose(out, picks, picks_path, j["name"], j, rows, med)
        else:
            p = picks[j["name"]]; best = next(r for r in rows if r["file"] == p["pick"])
            p.update(lufs=best["lufs"], hf_4k=best["hf_4k"], role_lufs=None if med is None else round(med, 1))
            picks_path.write_text(json.dumps(picks, ensure_ascii=False, indent=1), encoding="utf-8")
            if not best["sound_ok"]:
                print(f"[warn] {j['name']} 已挑的 {best['file']} 響度差 {best['lufs_dev']} dB／高頻比 {best['hf_4k']}，"
                      "要換就用 --rerank（H3 已拍好的鏡頭要確認新候選不比鏡長更長）", flush=True)


def write_trimmed(src, dst, head=0.08, tail=0.15):
    """選中的那支去掉頭尾靜音（保留開頭 80 ms、結尾 150 ms），台詞放到時間軸上才會準時開口、字幕對得上。
    TTS 候選頭尾常有 0.3–1.0 秒靜音（2026-10-07 全新安裝測試發現）。回傳 [裁掉的開頭秒數, 保留的長度秒數]。"""
    import librosa
    x, sr = sf.read(str(src), dtype="float32")
    mono = x.mean(axis=1) if x.ndim > 1 else x
    _, (a, b) = librosa.effects.trim(mono, top_db=40)
    a = max(0, a - int(head * sr)); b = min(len(x), b + int(tail * sr))
    sf.write(str(dst), x[a:b], sr, subtype="PCM_16")
    return [round(float(a) / sr, 3), round(float(b - a) / sr, 3)]


def choose(out, picks, picks_path, name, j, rows, med=None):
    said = [r for r in rows if r["asr_ok"] and r["len_ok"]]
    good = [r for r in said if r["sound_ok"]]          # 聽寫、長度、音量音質都正常
    pool = good or said or [r for r in rows if r["len_ok"]] or rows
    off = lambda r: -max(0.0, abs(r["lufs_dev"] or 0) - 3)   # 腔調同分時，離中位數 3 dB 以內的優先
    best = max(pool, key=lambda r: (r["asr_ok"], r["sim"], r["tw_score"], -(r["tw_dist"] or 9)) if not said else (r["tw_score"], off(r), -(r["tw_dist"] or 9)))
    trim = write_trimmed(out / "cand" / best["file"], out / f"{name}.wav")
    why = None if good else ("sound" if said else "asr")   # sound＝聽寫對的候選全部響度離群或嘶聲；asr＝聽寫全錯
    picks[name] = {"text": j["text"], "pick": best["file"], "n_ok": len(good), "needs_review": not good, "review_reason": why, "trim_s": trim,
                   "lufs": best["lufs"], "hf_4k": best["hf_4k"], "role_lufs": None if med is None else round(med, 1), "cands": rows}
    picks_path.write_text(json.dumps(picks, ensure_ascii=False, indent=1), encoding="utf-8")
    note = {"asr": "NEEDS_REVIEW " + best["asr"], "sound": f"NEEDS_REVIEW 音量音質（響度差 {best['lufs_dev']} dB、高頻比 {best['hf_4k']}）"}.get(why, "")
    print(f"[pick] {name} {best['file']} ok={len(good)}/{len(rows)} tw={best['tw_score']} {best['lufs']} LUFS hf={best['hf_4k']} {note}", flush=True)


if __name__ == "__main__":
    main()
