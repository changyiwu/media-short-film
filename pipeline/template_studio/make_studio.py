"""單人錄音室範本（橫式 1920x1080、24 fps）：讀 studio.json，從一首歌一路做到成片＋自審。做新的一支只改 studio.json。
古代人物在現代錄音室對著麥克風唱一首華語流行歌（錄音室一鏡到底的感覺，只有一位主唱）。改寫自 pipeline/template_battle/make_battle.py：
拿掉 DJ、第二位饒舌手、換場、觀眾聲、對決特效與投票卡；加上候選歌比較（pick）、定妝圖從 output/角色/ 複製、錄音室母版、ASS 燒字幕。
Voice venv 執行（librosa、transformers 在這個環境；生圖、H3、生歌、放大會自己叫 H3 venv）。ComfyUI 要先開（tools/start_comfy.cmd）：
  <Voice venv>/python make_studio.py [stage ...] [--studio 別的設定.json] [--ver 1]
stage（不給＝從 songs 依序跑到 srt；lyrics、music3、yue、pick 不在預設順序裡，生歌時手動跑）：
  lyrics    把 lyrics 寫成 Music 3／YuE2 用的歌詞與風格檔（work/songtext/）
  music3    MiniMax Music 3 抽 MUSIC3_SEEDS 首（預設 1,2,3,4）→ work/gen/music3/
  yue       YuE2 抽 YUE_SEEDS 首（預設 1–6，--cfg 1.3 --temp 0.85）→ work/gen/yue/
  pick      work/gen/ 底下全部候選：分人聲 → 歌詞對齊 → 逐句聽寫 → 排序（work/gen/pick.json）＋每首一支試聽影片（work/試聽/）
            → 人聽完挑一首，把路徑填進 studio.json 的 song
  songs     定案的歌：分人聲 → 歌詞強制對齊 → 逐句聽寫、BPM、最後一個字唱完的時間 → work/song/align_S.json
  audio     全片音軌：片名卡需要的話前面墊靜音 → 整首歌 → 最後一個字後留 tail 秒、淡出 → work/audio/（mix、vocals、timeline）
  chars     從 output/角色/<角色>/ 複製轉面圖、表情表、臉部近照 → work/chars/S_<turn|expr|face>.png
  studio    錄音室母版（空景）→ work/scenes/studio.png
  frames    每鏡首幀 → work/first/<鏡>.png＋接觸表 work/first/_sheet.jpg（人工關卡 1）
  fix       只修首幀局部：那鏡寫 "fix"（英文），拿現有首幀＋麥克風架參考圖修圖，舊圖留在 work/first/_old/
  last      生自訂尾幀：那鏡寫 "last"（英文，鏡頭結束時哪裡不一樣），存 work/first/<鏡>_last.png，specs 當 H3 尾幀
  specs     每鏡 H3 spec（對嘴音軌、限制句）→ work/h3/<鏡>/
  h3        跑 H3 → work/h3/<鏡>/clip.mp4＋work/review/clips_*.jpg（人工關卡 2）
  cut       放大 → 剪接 → −16 LUFS → ASS 字幕（片名卡＋歌詞）→ work/cut/film_1080p.mp4＋手機版 film_phone.mp4
  review    每秒一格接觸表、H3 自己切鏡偵測、響度、人聲檢查 → work/review/（人工關卡 3：一定要人看完整成片）
  srt       YouTube 字幕檔 → work/cut/film.srt
已存在的輸出會跳過（中斷後重跑會接著做）。重做某一鏡：刪 work/first/<鏡>.png 或 work/h3/<鏡>/clip.mp4，或在 studio.json 那鏡加 seed_bump。
還沒跑 H3 的鏡，cut 會用首幀靜態圖代替（沒有首幀就用灰底鏡號），可以先看節奏。"""
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zlib
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
ARGS = sys.argv[1:]
CFG_FILE = HERE / (ARGS[ARGS.index("--studio") + 1] if "--studio" in ARGS else "studio.json")
CFG = json.loads(CFG_FILE.read_text(encoding="utf-8"))
VER = ARGS[ARGS.index("--ver") + 1] if "--ver" in ARGS else "1"
OUT = HERE / "work"; OUT.mkdir(exist_ok=True)
REPO = (HERE / CFG.get("repo_dir", "../../..")).resolve()
AI = Path(os.environ.get("AI_ROOT", r"C:\AI"))
T = Path(os.environ.get("AI_TOOLS", REPO / "tools"))     # 預設直接用 repo 的 tools/
_EXE = "Scripts/python.exe" if os.name == "nt" else "bin/python"
PYH3 = os.environ.get("PY_H3", str(AI / "H3" / "venv" / _EXE))
PYV = os.environ.get("PY_VOICE", str(AI / "Voice" / "venv" / _EXE))
SEP_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
UPSCALE = os.environ.get("UPSCALE", "rtxvsr" if os.name == "nt" else "lanczos")   # rtxvsr（只有 Windows）｜lanczos
SR, FPS, W, H = 48000, 24, 1920, 1080
S = CFG["singer"]
DIST = {"ECU": "an extreme close-up of the face", "CU": "a close-up from the chest up", "MCU": "a medium close-up from the waist up",
        "MS": "a medium shot from the knees up", "WIDE": "a wide shot showing the whole booth"}
# 中景、全景加正常成人比例（〈別碰我的圓〉O01 全身鏡上身短、腿過長、腰線太高，使用者退件）
BODY = {"MS": " He is a TALL man, about 195 cm tall. Natural adult male body proportions: normal shoulder width, a normal-length torso, the waist at a natural height.",
        "WIDE": " He is a TALL man, about 195 cm tall, with a long straight torso and long legs. Natural adult male body proportions as in the turnaround sheet: the head is about one-seventh of his whole height, normal "
                "shoulder width, a normal-length torso, the waist (rope belt) at about the middle of his body, the legs NOT elongated. The "
                "camera is at his chest height, a normal lens, no wide-angle distortion. The microphone stand's tripod base stands on the "
                "floor right next to his feet, at the same distance from the camera as he is."}
CLOSE = ("ECU", "CU", "MCU")
SHEETS = {"turn": "turnaround sheet", "expr": "expression sheet", "face": "close-up face sheet"}
SHEETS_BY_DIST = {"ECU": ["face", "expr"], "CU": ["face", "expr"], "MCU": ["face", "turn"], "MS": ["turn", "face"], "WIDE": ["turn", "face"]}
FONT = os.environ.get("SUB_FONT_NAME", "Microsoft JhengHei" if os.name == "nt" else "Noto Sans CJK TC")
TIMING = OUT / "timing.json"
timing = json.loads(TIMING.read_text(encoding="utf-8")) if TIMING.exists() else {}
CUT_NAME = "film" if VER == "1" else f"film_v{VER}"


# ------------------------------------------------------------------------------------------------ 共用
def run(cmd, cwd=HERE, check=True, **kw):
    print("$", " ".join(map(str, cmd))[:220], flush=True)
    env = {**os.environ, **kw.pop("env", {}), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=env, stdin=subprocess.DEVNULL, **kw)
    if check and r.returncode != 0:
        raise SystemExit(f"FAILED: {' '.join(map(str, cmd))[:220]}\n{(r.stdout + r.stderr)[-2500:]}")
    return r


def stage(name):
    def deco(fn):
        def wrap():
            t0 = time.time(); a = time.strftime("%H:%M:%S"); fn()
            timing[name] = dict(sec=round(time.time() - t0, 1), start=a, end=time.strftime("%H:%M:%S"))
            TIMING.write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[stage] {name} {timing[name]['sec']}s", flush=True)
        wrap.__name__ = name
        return wrap
    return deco


def free_comfy():
    try:
        r = urllib.request.Request(HOST + "/free", data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
                                   headers={"Content-Type": "application/json"})
        urllib.request.urlopen(r, timeout=30); time.sleep(5)
    except Exception:
        pass


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def newest(d, ext=".png"):
    fs = sorted(Path(d).glob(f"*{ext}"), key=lambda f: f.stat().st_mtime)
    return fs[-1] if fs else None


def load_audio(p, sr=SR):
    import librosa
    import numpy as np
    a, _ = librosa.load(str(p), sr=sr, mono=False)
    return (a.T if a.ndim > 1 else np.stack([a, a], 1)).astype(np.float32)


def lines_all():
    """所有歌詞句（照順序）：sing＝送給歌曲模型的寫法（可用同音字修讀音），show＝字幕寫法，en＝選填英文字幕。"""
    out = []
    for sec in CFG["lyrics"]:
        for ln in sec["lines"]:
            out.append(dict(ln, section=sec["sec"]))
    return out


def show_text(ln):
    if ln.get("show"):
        return ln["show"]
    t = ln["sing"]
    for a, b in CFG.get("show_replace", []):
        t = t.replace(a, b)
    return t.replace(" ", "　")


def song_path():
    p = CFG.get("song")
    if not p:
        raise SystemExit("studio.json 的 song 還沒填：先跑 music3／yue → pick，人聽完挑一首，把路徑（相對片子資料夾）填進 song")
    p = (HERE / p).resolve()
    if not p.exists():
        raise SystemExit(f"找不到歌：{p}")
    return p


# ------------------------------------------------------------------------------------------------ 生歌
TAG = [("pre", "Pre-Chorus"), ("chorus", "Chorus"), ("bridge", "Bridge"), ("verse", "Verse"), ("outro", "Outro"), ("intro", "Intro")]
YUE_TAG = [("pre", "PRE-CHORUS"), ("chorus", "CHORUS"), ("bridge", "BRIDGE"), ("verse", "VERSE"), ("outro", "OUTRO")]


@stage("lyrics")
def lyrics():
    """Music 3 與 YuE2 的歌詞、風格檔（送進模型前 gen_music3.py／yue_song.py 會再經 tools/song_lyrics.py 繁轉簡＋讀音替換表）。"""
    d = OUT / "songtext"; d.mkdir(exist_ok=True)
    m3 = []
    for s in CFG["lyrics"]:
        tag = next((v for k, v in TAG if k in s["sec"].lower()), "Verse")
        m3.append(f"[{tag}]" + "".join("\n" + ln["sing"] for ln in s["lines"]))
    (d / "music3_lyrics.txt").write_text("\n\n".join(m3) + "\n", encoding="utf-8")
    (d / "music3_caption.txt").write_text(CFG["song_style"]["music3"], encoding="utf-8")
    yue = []
    for s in CFG["lyrics"]:
        if not s["lines"]:
            continue                                           # YuE2 不要空段落（14 版範本：空的 Intro／Interlude 會變差）
        tag = next((v for k, v in YUE_TAG if k in s["sec"].lower()), "VERSE")
        for i in range(0, len(s["lines"]), 4):                 # 每段最多 4 句
            yue.append(f"[{tag}]\n" + "\n".join(ln["sing"] for ln in s["lines"][i:i + 4]))
    (d / "yue_lyrics.txt").write_text("\n\n".join(yue) + "\n", encoding="utf-8")
    (d / "yue_style.txt").write_text(CFG["song_style"]["yue"], encoding="utf-8")
    print(f"→ {d}：{len(lines_all())} 句", flush=True)


@stage("music3")
def music3():
    """MiniMax Music 3 抽 MUSIC3_SEEDS 首（超過約 100 秒一律 --tiled，不然整段解碼會讓 ComfyUI 退出）。已有的 seed 跳過。"""
    lyrics()
    d = OUT / "gen" / "music3"; d.mkdir(parents=True, exist_ok=True)
    secs = float(CFG.get("song_seconds", 180))
    for seed in os.environ.get("MUSIC3_SEEDS", "1,2,3,4").split(","):
        tag = f"m3_s{seed.strip()}"
        if any(d.glob(f"{tag}_*")):
            print(tag, "已經有了，跳過", flush=True); continue
        t0 = time.time()
        run([PYH3, T / "gen_music3.py", "--caption-file", OUT / "songtext" / "music3_caption.txt", "--lyrics-file", OUT / "songtext" / "music3_lyrics.txt",
             "--seconds", secs, "--seed", seed.strip(), "--tiled", "--prefix", f"audio/studio/{tag}", "--out", d])
        print(f"{tag} {time.time() - t0:.0f}s", flush=True)
    free_comfy()


@stage("yue")
def yue():
    """YuE2 抽 YUE_SEEDS 首（--cfg 1.3 --temp 0.85 比較貼歌詞）。YuE2 換 seed 是另一首歌，不能拿來局部接。"""
    lyrics()
    d = OUT / "gen" / "yue"
    seeds = os.environ.get("YUE_SEEDS", "1,2,3,4,5,6")
    run([PYV, T / "yue_song.py", "studio", "S", "--style", OUT / "songtext" / "yue_style.txt", "--lyrics", OUT / "songtext" / "yue_lyrics.txt",
         "--out", d, "--seeds", seeds, "--secs", float(CFG.get("song_seconds", 180)), "--cfg", "1.3", "--temp", "0.85"])
    free_comfy()


def sep_stems(src, d):
    """BS-RoFormer 分出人聲與伴奏（只做一次）。"""
    d.mkdir(parents=True, exist_ok=True)
    voc = next(d.glob(f"{src.stem}_(Vocals)*"), None); ins = next(d.glob(f"{src.stem}_(Instrumental)*"), None)
    if voc is None or ins is None:
        from audio_separator.separator import Separator
        sep = Separator(model_file_dir=str(AI / "Voice" / "models" / "separator"), output_dir=str(d), output_format="FLAC", log_level=40)
        sep.load_model(model_filename=SEP_MODEL)
        sep.separate(str(src))
        voc = next(d.glob(f"{src.stem}_(Vocals)*")); ins = next(d.glob(f"{src.stem}_(Instrumental)*"))
    return voc, ins


def last_word_end(voc, word_end):
    """最後一個字唱完：強制對齊的最後一個詞結束時間，人聲還很大聲就往後延，最多 0.3 秒（同 make_battle.py）。"""
    import numpy as np
    import soundfile as sf
    a, sr = sf.read(str(voc), dtype="float32", always_2d=True); a = a.mean(1)
    hop = int(0.05 * sr); n = len(a) // hop
    rms = np.sqrt(np.mean(a[:n * hop].reshape(n, hop) ** 2, 1)); ref = np.sqrt(np.mean(rms[rms > 0] ** 2))
    i = int(word_end / 0.05)
    while i < min(n, int((word_end + 0.3) / 0.05)) and rms[i] >= 0.25 * ref:
        i += 1
    return round(max(word_end, i * 0.05), 3)


def vocal_gaps(voc, rows, min_gap=3.0):
    """逐句之間有沒有「人聲還在唱、歌詞卻沒對到」的空檔（模型自己多唱一遍副歌）。"""
    import librosa
    import numpy as np
    v, sr = librosa.load(str(voc), sr=16000)
    rms = lambda a, b: float(np.sqrt(np.mean(v[int(a * sr):int(b * sr)] ** 2)))
    sung = float(np.median([rms(x["start"], x["end"]) for x in rows if x["end"] - x["start"] > 0.3]))
    return [(round(x["end"], 1), round(n["start"], 1)) for x, n in zip(rows, rows[1:]) if n["start"] - x["end"] >= min_gap and rms(x["end"] + 0.2, n["start"] - 0.2) > sung * 0.4]


def analyse(src, sep_dir, align, hear):
    """一首歌：分人聲 → 對齊 → 逐句聽寫 → {song, vocals, instrumental, bpm, last_word_end, rows}（listen_video.py 吃這個格式）。"""
    import librosa
    import numpy as np
    import opencc
    import soundfile as sf
    cc = opencc.OpenCC("s2twp")
    norm = lambda s: re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", cc.convert(s)).upper()
    voc, ins = sep_stems(src, sep_dir)
    lines = lines_all()
    a, sr = sf.read(str(voc), dtype="float32", always_2d=True); a = a.mean(1)
    aa = a
    if CFG.get("align_from"):                                  # 前奏有模型自己加的哼唱，把前幾句對齊拉走 → 對齊時把這秒數之前靜音
        aa = a.copy(); aa[:int(float(CFG["align_from"]) * sr)] = 0
    rows = []
    for ln, s in zip(lines, align(aa, sr, [re.sub(r"[：，、。！？「」『』（）—…]", " ", x["sing"]) for x in lines])):
        t = cc.convert(hear(a[int(max(0, s["start"] - 0.1) * sr):int((s["end"] + 0.15) * sr)], sr))
        rows.append({"section": ln["section"], "text": ln["sing"], "start": s["start"], "end": s["end"], "words": s["words"],
                     "asr": t, "ok": round(difflib.SequenceMatcher(None, norm(ln["sing"]), norm(t)).ratio(), 2)})
    lw = CFG.get("last_word_end") or last_word_end(voc, rows[-1]["words"][-1]["e"] if rows[-1]["words"] else rows[-1]["end"])
    y, s2 = librosa.load(str(src), sr=22050)
    bpm = float(np.atleast_1d(librosa.beat.beat_track(y=y, sr=s2, start_bpm=float(CFG.get("bpm", 76)))[0])[0])
    return {"song": str(src), "vocals": str(voc), "instrumental": str(ins), "bpm": round(bpm, 1), "last_word_end": lw,
            "duration": round(len(y) / s2, 1), "rows": rows}


@stage("pick")
def pick():
    """work/gen/ 底下所有候選歌排序：逐句聽寫平均分（char_ok）、低分句數、長度、BPM；每首做一支試聽影片（tools/listen_video.py：
    歌詞逐字掃色＋下方逐句聽寫與分數，低分與漏字紅字）。聽寫只是初篩，一定要人看著試聽影片聽完再挑。"""
    sys.path.insert(0, str(T)); import stt   # noqa: E401
    free_comfy()
    cands = sorted(p for p in (OUT / "gen").glob("*/*") if p.suffix.lower() in (".flac", ".mp3", ".wav") and "(Vocals)" not in p.name
                   and "(Instrumental)" not in p.name and p.parent.name != "sep")
    if not cands:
        raise SystemExit("work/gen/ 底下沒有候選歌：先跑 music3 或 yue")
    pj = OUT / "gen" / "pick.json"
    old = json.loads(pj.read_text(encoding="utf-8")) if pj.exists() else {}
    align = hear = None; rep = dict(old)
    for src in cands:
        key = f"{src.parent.name}_{src.stem}".upper()          # listen_video.py 會把代號轉大寫
        af = OUT / "song" / f"align_{key}.json"
        if key in old and af.exists():
            continue
        if align is None:
            align, hear = stt.load_song_aligner(), stt.load_song_asr()
        info = analyse(src, OUT / "gen" / "sep", align, hear)
        af.parent.mkdir(exist_ok=True); af.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        rows = info["rows"]
        rep[key] = {"file": str(src.relative_to(HERE)).replace("\\", "/"), "char_ok": round(sum(x["ok"] for x in rows) / len(rows), 2),
                    "low": sum(1 for x in rows if x["ok"] < 0.5), "bpm": info["bpm"], "duration": info["duration"],
                    "first": round(rows[0]["start"], 1), "last_word_end": info["last_word_end"],
                    "gaps": vocal_gaps(info["vocals"], rows)}
        print(key, json.dumps(rep[key], ensure_ascii=False), flush=True)
    rep = dict(sorted(rep.items(), key=lambda kv: (-kv[1]["char_ok"], kv[1]["low"])))
    pj.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    for key in rep:
        if not (OUT / "試聽" / f"試聽_{key}.mp4").exists():
            run([PYV, T / "listen_video.py", HERE, key])
    print("排序（逐句聽寫平均，越高越好；low＝低於 0.5 的句數）：", flush=True)
    for i, (k, v) in enumerate(rep.items(), 1):
        print(f"  {i}. {k}  ok {v['char_ok']}  低分 {v['low']} 句  {v['duration']} 秒  BPM {v['bpm']}  → work/試聽/試聽_{k}.mp4", flush=True)
    print("→ 一定要人看著 work/試聽/ 的影片聽：唱錯字、聲音不像角色、多唱一遍副歌（gaps）就換一首或多抽；"
          "挑好的把 file 填進 studio.json 的 song，再跑 songs", flush=True)


@stage("songs")
def songs():
    """定案的歌：分人聲 → 歌詞強制對齊（Qwen3-ForcedAligner）→ 逐句聽寫分數（Qwen3-ASR）、BPM、最後一個字唱完的時間 → work/song/align_S.json。"""
    sys.path.insert(0, str(T)); import stt   # noqa: E401
    free_comfy()
    src = song_path()
    info = analyse(src, OUT / "song" / "sep", stt.load_song_aligner(), stt.load_song_asr())
    (OUT / "song" / "align_S.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    rows = info["rows"]
    print(f"BPM {info['bpm']}、{info['duration']} 秒、第一句 {rows[0]['start']:.1f} 秒、最後一個字 {info['last_word_end']} 秒、"
          f"逐句聽寫平均 {sum(x['ok'] for x in rows) / len(rows):.2f}", flush=True)
    for x in rows:
        if x["ok"] < 0.5:
            print("   低分句（去聽這句有沒有唱錯）：", x["text"][:16], x["ok"], x["asr"][:20], flush=True)
        if x["end"] - x["start"] < 0.6:
            print(f"   ⚠ 對齊把這句壓成 {x['end'] - x['start']:.2f} 秒：{x['text'][:16]}（看人聲分軌，必要時填 align_from）", flush=True)
    for g in vocal_gaps(info["vocals"], rows):
        print(f"   ⚠ {g[0]}–{g[1]} 秒人聲還在唱，但歌詞沒對到（多唱一遍副歌？）→ 把那幾句補進歌詞，字幕和鏡頭才不會漏", flush=True)
    print("→ 最後一個字唱完的時間不對就在 studio.json 填 last_word_end 秒數再跑 songs；試聽：python tools/listen_video.py <片子資料夾> S", flush=True)


# ------------------------------------------------------------------------------------------------ 全片音軌
@stage("audio")
def audio():
    """片名卡：歌的前奏比 title_card.sec 短，就在前面墊靜音（PRE）。整首歌照原樣用；最後一個字唱完後留 tail 秒（預設 6），
    最後 fade 秒（預設 3）淡出；歌本身比較短就用到歌尾。人聲分軌照同樣的時間軸存一份給 H3 對嘴。"""
    import numpy as np
    import soundfile as sf
    d = OUT / "audio"; d.mkdir(exist_ok=True)
    al = json.loads((OUT / "song" / "align_S.json").read_text(encoding="utf-8"))
    mix, voc = load_audio(al["song"]), load_audio(al["vocals"])
    n = min(len(mix), len(voc)); mix, voc = mix[:n], voc[:n]
    rows = al["rows"]; lw = float(al["last_word_end"])
    tc = CFG.get("title_card", {})
    PRE = round(max(0.0, float(tc.get("sec", 0)) + 0.4 - rows[0]["start"]), 2) if tc.get("text") else 0.0
    end = min(n, int((lw + float(CFG.get("tail", 6.0))) * SR))
    mix, voc = mix[:end].copy(), voc[:end].copy()
    f = min(int(float(CFG.get("fade", 3.0)) * SR), max(0, end - int((lw + 0.5) * SR)))
    if f > 0:
        mix[-f:] *= np.linspace(1, 0, f)[:, None] ** 1.3
    pad = np.zeros((int(PRE * SR), 2), np.float32); tail = np.zeros((int(1.0 * SR), 2), np.float32)
    mix = np.concatenate([pad, mix, tail]); voc = np.concatenate([pad, voc, tail])
    pk = max(1.0, np.abs(mix).max() / 0.97); mix /= pk; voc /= pk
    sf.write(d / "mix.wav", mix, SR, subtype="PCM_16"); sf.write(d / "vocals.wav", voc, SR, subtype="PCM_16")
    lines = []
    for ln, r in zip(lines_all(), rows):
        lines.append({"section": r["section"], "text": r["text"], "show": show_text(ln), "en": ln.get("en", ""),
                      "start": round(r["start"] + PRE, 3), "end": round(min(r["end"], lw) + PRE, 3),
                      "words": [{"w": w["w"], "s": round(w["s"] + PRE, 3), "e": round(min(w["e"], lw) + PRE, 3)} for w in r["words"]]})
    total = round(len(mix) / SR, 3)
    marks = {"first": lines[0]["start"], "last_end": round(lw + PRE, 3), "music_end": round(end / SR + PRE, 3), "total": total}
    (d / "timeline.json").write_text(json.dumps({"lines": lines, "marks": marks, "pre": PRE}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("PRE", PRE, "| first", marks["first"], "| last", marks["last_end"], "| music end", marks["music_end"], "| total", total, flush=True)


# ------------------------------------------------------------------------------------------------ 鏡表
def timeline():
    return json.loads((OUT / "audio" / "timeline.json").read_text(encoding="utf-8"))


def resolve_shots():
    """studio.json 的 shots（at＝開始時間）→ 每鏡 start／end（下一鏡的開始；最後一鏡到片尾）。at 可以是：
    秒數｜["L", i]＝第 i 句（從 0 數）開口前 0.12 秒（i＝-1：第一句前 4 秒、-2：前 2.5 秒）｜["L", i, 偏移秒]
    ｜["mark", "first|last_end|music_end", 偏移秒]。"""
    tl = timeline(); mk = tl["marks"]; ln = tl["lines"]

    def t_of(at):
        if isinstance(at, (int, float)):
            return float(at)
        if at[0] == "L":
            i = at[1]; off = at[2] if len(at) > 2 else -0.12
            if i < 0:
                return round(max(0.0, ln[0]["start"] - (4.0 if i == -1 else 2.5)), 3)
            if i >= len(ln):
                raise SystemExit(f"at {at}：歌詞只有 {len(ln)} 句")
            return round(ln[i]["start"] + off, 3)
        return round(mk[at[1]] + at[2], 3)
    out = []
    for i, s in enumerate(CFG["shots"]):
        st = t_of(s["at"]); en = t_of(CFG["shots"][i + 1]["at"]) if i + 1 < len(CFG["shots"]) else mk["total"]
        out.append(dict(s, start=st, end=en))
    bad = [(a["id"], b["id"], a["start"], b["start"]) for a, b in zip(out, out[1:]) if b["start"] <= a["start"] + 0.8]
    if bad:
        raise SystemExit(f"鏡頭太短（< 0.8 秒）或順序錯：{bad}（改 studio.json 這幾鏡的 at）")
    long_ = [(s["id"], round(s["end"] - s["start"], 1)) for s in out if s["end"] - s["start"] > 12 and not s.get("still")]
    if long_:
        print(f"⚠ 這幾鏡超過 12 秒（H3 單鏡上限）：{long_} → 拆鏡或改 at", flush=True)
    return out


def seed_for(s):
    return int(CFG.get("seed0", 7300)) + zlib.crc32(s["id"].encode()) % 900 + int(s.get("seed_bump", 0))


# ------------------------------------------------------------------------------------------------ 圖
IMG_LOG = OUT / "image_backends.json"
IMG_BACKEND = os.environ.get("IMAGE_BACKEND", "auto")   # auto（Codex CLI 優先、Image 2.5 API 次之，失敗就停）｜codex｜img25｜local；一支片固定一個


def gen_img(cmd):
    """跑一次 gen_image.py，記下實際用的後端（發布資訊的 AI 揭露照實際寫）。"""
    r = run(cmd)
    used = next((b for b in ("img25", "codex") if f"[backend] {b}" in r.stdout), "local")
    log = json.loads(IMG_LOG.read_text(encoding="utf-8")) if IMG_LOG.exists() else {}
    log[used] = log.get(used, 0) + 1
    IMG_LOG.write_text(json.dumps(log), encoding="utf-8")
    return r


@stage("chars")
def chars():
    """從 output/角色/<角色>/（studio.json 的 singer.char_dir）複製三張定妝：<code>_turn／_expr／_face.png → work/chars/S_<…>.png。
    角色資料夾沒有定妝就停：先用 short-film 流程定裝（make_film.py chars），不要在這裡另外生。"""
    src = (HERE / S["char_dir"]).resolve(); dst = OUT / "chars"; dst.mkdir(exist_ok=True)
    miss = []
    for n in SHEETS:
        f = src / f"{S['code']}_{n}.png"
        if not f.exists():
            miss.append(f.name); continue
        if not (dst / f"S_{n}.png").exists():
            shutil.copy2(f, dst / f"S_{n}.png")
    if miss:
        raise SystemExit(f"{src} 缺定妝 {miss}：先照 short-film 流程定裝")
    print(f"→ work/chars/ 三張定妝（來源 {src}）", flush=True)


@stage("studio")
def studio():
    """錄音室母版（空景、橫式）：之後每鏡首幀都附它當場景參考，背景布、麥克風、燈光才會鏡鏡一樣。
    props 裡寫 "in_master": true 的道具（麥克風組）附多角度總覽當參考，母版裡的道具就照 output/道具/ 的參考圖畫，不另外發明。"""
    dst = OUT / "scenes" / "studio.png"
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    refs, keep = [], []
    for pr in CFG.get("props", []):
        f = prop_file(pr, "views")
        if pr.get("in_master") and f:
            refs.append(f); keep.append(pr["keep"].replace("{ref}", f"<image{len(refs)}>"))
            r, k = close_extra(pr, len(refs)); refs += r; keep += k
    prompt = (" ".join(keep) + " New photo: " if keep else "") + CFG["studio"]["master"]
    cmd = [PYH3, T / "gen_image.py", "--prompt", prompt, "--width", "1536", "--height", "1024", "--seed", CFG["studio"].get("seed", 21),
           "--prefix", "studio/master", "--out", OUT / "scenes"]
    if refs:
        cmd[2:2] = ["--model", "qwen-edit"]
        for r in refs:
            cmd += ["--ref", r]
    gen_img(cmd)
    newest(OUT / "scenes").rename(dst)
    print("→ 看 work/scenes/studio.png：背景布顏色、麥克風、沒有人、沒有字和商標", flush=True)


def rig_ref():
    """舊片相容：從母版裁出麥克風架（studio.rig_crop＝[x0, y0, x1, y1]）放大兩倍 → work/scenes/rig.png，每張首幀多附它。
    新片不寫 rig_crop：麥克風組直接用 output/道具/ 的參考圖（props），不從母版另外裁一張。"""
    dst = OUT / "scenes" / "rig.png"
    box = CFG["studio"].get("rig_crop")
    if not box or dst.exists() or not (OUT / "scenes" / "studio.png").exists():
        return dst if dst.exists() else None
    from PIL import Image
    im = Image.open(OUT / "scenes" / "studio.png").convert("RGB").crop(tuple(box))
    im.resize((im.width * 2, im.height * 2), Image.LANCZOS).save(dst)
    print("→ 看 work/scenes/rig.png：只有麥克風、防噴罩、吊桿和線", flush=True)
    return dst


PROP_CLOSE = {"ECU", "CU", "MCU"}


def prop_file(pr, kind):
    """道具參考圖路徑：寫了 "dir" 就直接讀 output/道具/<dir>/（不複製、不在片內另生）；沒寫 dir 的舊片讀 work/props/。"""
    name = pr.get(kind)
    if not name:
        return None
    f = (REPO / "output" / "道具" / pr["dir"] / name) if pr.get("dir") else (OUT / "props" / name)
    if not f.exists():
        raise SystemExit(f"找不到道具參考圖 {f}：道具參考圖放 output/道具/<道具>/（docs/07 §6），不要每支片另外生")
    return f


def prop_refs(s, n0):
    """道具參考圖（studio.json 的 props，每個 {"name", "dir", "views", "detail", "keep"}；dir＝output/道具/ 底下的資料夾，直接讀）。
    近景附 detail（細部），中景、全身附 views（多角度）；那鏡寫 "props": [] 就不附。n0＝前面已經有幾張參考圖。
    回傳 (參考圖清單, 提示詞句子清單)：持續出現的道具只靠文字描述，細部會一鏡一個樣（docs/rules/道具.md）。"""
    refs, keep = [], []
    want = s.get("props")
    for pr in CFG.get("props", []):
        if want is not None and pr["name"] not in want:
            continue
        f = prop_file(pr, "detail" if s.get("dist") in PROP_CLOSE and pr.get("detail") else "views")
        if not f:
            continue
        refs.append(f)
        keep.append(pr["keep"].replace("{ref}", f"<image{n0 + len(refs)}>"))
        if s.get("dist") in PROP_CLOSE:
            r, k = close_extra(pr, n0 + len(refs)); refs += r; keep += k
    return refs, keep


def close_extra(pr, n0):
    """單一部位的近照（props 的 close_extra：[{file, keep}]，例：防噴罩蛇管）：近景首幀與錄音室母版另外附。
    細部表格一格太小，近景、母版的蛇管還是會各畫各的。"""
    refs, keep = [], []
    for x in pr.get("close_extra", []):
        refs.append(prop_file({**pr, "f": x["file"]}, "f"))
        keep.append(x["keep"].replace("{ref}", f"<image{n0 + len(refs)}>"))
    return refs, keep


def shot_sheets(s):
    names = s.get("sheets") or SHEETS_BY_DIST[s["dist"]]
    if any(n not in SHEETS for n in names) or not 1 <= len(names) <= 3:
        raise SystemExit(f"{s['id']} 的 sheets 只能是 turn／expr／face 中 1–3 個：{names}")
    return names


def frame_prompt(s):
    """首幀提示詞＋參考圖：主唱定妝 1–3 張（依景別，可用 shot 的 sheets 指定）＋錄音室母版（最後一張）。每鏡照抄完整外觀描述。"""
    refs, keep = [], []
    if s.get("singer", True):
        names = shot_sheets(s); refs += [OUT / "chars" / f"S_{n}.png" for n in names]
        pics = " and ".join(f"<image{i}> ({SHEETS[n]})" for i, n in enumerate(names, 1))
        keep.append(f"{pics} {('shows', 'both show', 'all show')[len(names) - 1]} the same person ({S['look']}); keep exactly that face, "
                    "hairstyle and clothes. The reference sheets are only for the person's identity: do NOT copy their grid layout, grey "
                    "background, labels or poses; the result is one single photo.")
    refs.append(OUT / "scenes" / "studio.png")
    keep.append(CFG["studio"]["keep"].replace("{ref}", f"<image{len(refs)}>"))
    rig = rig_ref()
    if rig and s.get("rig", True):   # 刻意鏡像的鏡（麥克風在另一邊）設 "rig": false
        refs.append(rig)
        keep.append(CFG["studio"]["rig_keep"].replace("{ref}", f"<image{len(refs)}>"))
    if s.get("singer", True):
        pr, pk = prop_refs(s, len(refs)); refs += pr; keep += pk
    text = s["frame"] + " "
    if s.get("singer", True):
        text += S.get("studio_wear", "") + " "
        if s.get("mic", True):   # 麥克風在嘴巴正前方、嘴巴高度、跟臉一樣長；主唱離開麥克風的鏡設 "mic": false
            text += CFG["studio"].get("mic", "") + " "
    text += f"CAMERA DISTANCE: {DIST[s['dist']]}" + (" - the face is large and sharp, nothing between the subject and the camera. " if s["dist"] in CLOSE else ". ")
    if s.get("singer", True):
        text += BODY.get(s["dist"], "").strip() + " "
    p = (" ".join(keep) + " New photo: " + CFG["film_look"] + " " + text + CFG["studio"]["light"] + " HORIZONTAL 16:9 widescreen frame, the "
         "picture fills the ENTIRE frame edge to edge - NO black bars, NO borders. " + CFG["no_text"])
    return p, refs


def sheet(files, dst, cols=4, label=None):
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, str(REPO / "tools")); from fonts import font   # noqa: E401
    fs = [p for p in files if Path(p).exists()]
    if not fs:
        return
    tw, th = 480, 270; rows = (len(fs) + cols - 1) // cols
    im = Image.new("RGB", (cols * tw, rows * (th + 30)), (30, 30, 30)); f = ImageFont.truetype(font("jhbd"), 22)
    for i, p in enumerate(fs):
        x, y = (i % cols) * tw, (i // cols) * (th + 30)
        im.paste(Image.open(p).convert("RGB").resize((tw, th)), (x, y + 30))
        ImageDraw.Draw(im).text((x + 6, y + 3), label(p) if label else Path(p).stem, font=f, fill=(255, 220, 0))
    Path(dst).parent.mkdir(parents=True, exist_ok=True); im.save(dst, quality=85)


@stage("frames")
def frames():
    """每鏡首幀（still 的鏡也要首幀，cut 會用）。唱歌鏡畫「開口前」的姿勢；母版裡的背景布、麥克風、燈每鏡都一樣。
    首幀跟歌的時間無關：還沒定歌（沒有 timeline.json）也能先生，只是不檢查鏡長。"""
    shots = resolve_shots() if (OUT / "audio" / "timeline.json").exists() else CFG["shots"]
    miss = [p.name for p in [OUT / "chars" / f"S_{n}.png" for n in SHEETS] + [OUT / "scenes" / "studio.png"] if not p.exists()]
    if miss:
        raise SystemExit(f"缺 {miss}：先跑 chars studio")
    only = os.environ.get("ONLY", "").split()
    (OUT / "first").mkdir(exist_ok=True)
    for s in shots:
        dst = OUT / "first" / f"{s['id']}.png"
        if dst.exists() or (only and s["id"] not in only):
            continue
        p, refs = frame_prompt(s)
        (OUT / "first" / f"{s['id']}.prompt.txt").write_text(p, encoding="utf-8")
        cmd = [PYH3, T / "gen_image.py", "--model", "qwen-edit", "--width", "1344", "--height", "768", "--prompt", p,
               "--seed", 5101 + zlib.crc32(s["id"].encode()) % 900 + int(s.get("frame_seed_bump", 0)), "--prefix", f"studio/{s['id']}", "--out", OUT / "first"]
        for r in refs:
            cmd += ["--ref", r]
        gen_img(cmd)
        newest(OUT / "first").rename(dst)
        print("frame", s["id"], flush=True)
    sheet([OUT / "first" / f"{s['id']}.png" for s in shots], OUT / "first" / "_sheet.jpg")
    expect = [f"{s['id']}=1" for s in shots if s.get("singer", True)]
    r = run([PYV, T / "face_count.py", OUT / "first", *expect], check=False)
    print(r.stdout[-1500:] if r.returncode == 0 else f"⚠ 首幀臉數檢查失敗（{r.returncode}），改人工看", flush=True)
    print("→ 人工關卡 1：看 work/first/_sheet.jpg（臉、服裝、耳機、麥克風位置、背景布顏色、多手多腳、背景字）。重畫：刪該鏡 png，"
          "studio.json 那鏡加 frame_seed_bump 或改 frame，再跑 frames", flush=True)


@stage("fix")
def fix():
    """只修首幀的局部（線、桿子、耳機線這類小地方），其他照舊：studio.json 那鏡寫 "fix"（英文，只寫要改什麼）。
    拿現有首幀＋麥克風架參考圖修圖，比整張重生穩（重生會連帶改掉已經對的地方）。舊圖移到 work/first/_old/；
    work/first/_fixed.json 記每鏡修過的 fix 文字，同一句不會重修，要再修就改 fix 的寫法或刪掉那筆紀錄。"""
    shots = CFG["shots"]
    rec_f = OUT / "first" / "_fixed.json"
    rec = json.loads(rec_f.read_text(encoding="utf-8")) if rec_f.exists() else {}
    rig = rig_ref()
    (OUT / "first" / "_old").mkdir(exist_ok=True)
    for s in shots:
        want = s.get("fix")
        src = OUT / "first" / f"{s['id']}.png"
        if not want or rec.get(s["id"]) == want or not src.exists():
            continue
        old = OUT / "first" / "_old" / f"{s['id']}_{time.strftime('%H%M%S')}.png"
        shutil.copy2(src, old)
        refs = [old] + ([rig] if rig and s.get("rig", True) else [])
        note = " <image2> is a close-up of the correct microphone rig, for reference only." if len(refs) > 1 else ""
        pr, pk = prop_refs(s, len(refs)); refs += pr
        p = ("Edit <image1>. Keep EVERYTHING in <image1> exactly the same - the same person, face, expression, pose, hands, clothes, "
             "headphones, microphone, stand, pop filter, background, lighting, camera angle and framing - and change ONLY this: " + want +
             note + (" " + " ".join(pk) if pk else "") + " HORIZONTAL 16:9 frame, same size as <image1>. " + CFG["no_text"])
        (OUT / "first" / f"{s['id']}.fix.txt").write_text(p, encoding="utf-8")
        cmd = [PYH3, T / "gen_image.py", "--model", "qwen-edit", "--width", "1344", "--height", "768", "--prompt", p,
               "--seed", 6101 + zlib.crc32(s["id"].encode()) % 900, "--prefix", f"studio/fix_{s['id']}", "--out", OUT / "first"]
        for r in refs:
            cmd += ["--ref", r]
        gen_img(cmd)
        newest(OUT / "first").replace(src)
        rec[s["id"]] = want
        rec_f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        print("fix", s["id"], flush=True)
    sheet([OUT / "first" / f"{s['id']}.png" for s in shots], OUT / "first" / "_sheet.jpg")
    print("→ 看 work/first/_sheet.jpg；修壞了就從 work/first/_old/ 拿回舊圖", flush=True)


@stage("last")
def last():
    """生自訂尾幀：studio.json 那鏡寫 "last"（英文，只寫鏡頭結束時跟首幀不一樣的地方），拿首幀修成
    work/first/<鏡>_last.png，specs 會把它當 H3 的尾幀。用在動作會改變外觀的鏡（拿下耳機）：只給首幀 H3 不知道結果
    長什麼樣，會溶接、拉近或冒出第二副耳機；尾幀＝首幀又會把動作倒回去。要重生就刪掉那張 _last.png。"""
    for s in CFG["shots"]:
        want = s.get("last")
        src, dst = OUT / "first" / f"{s['id']}.png", OUT / "first" / f"{s['id']}_last.png"
        if not want or dst.exists() or not src.exists():
            continue
        p = ("Edit <image1>. The new picture is the LAST frame of the same continuous shot a few seconds later: keep the same person, "
             "face, body proportions, clothes, microphone, stand, pop filter, cables, background, lighting, camera position, angle and "
             "framing exactly the same as <image1> - and change ONLY this: " + want + " HORIZONTAL 16:9 frame, same size as <image1>. " +
             CFG["no_text"])
        pr, pk = prop_refs(s, 1)
        p += (" " + " ".join(pk)) if pk else ""
        (OUT / "first" / f"{s['id']}_last.txt").write_text(p, encoding="utf-8")
        cmd = [PYH3, T / "gen_image.py", "--model", "qwen-edit", "--width", "1344", "--height", "768", "--prompt", p,
               "--seed", 6301 + zlib.crc32(s["id"].encode()) % 900 + int(s.get("last_seed_bump", 0)), "--prefix", f"studio/last_{s['id']}",
               "--out", OUT / "first", "--ref", src]
        for r in pr:
            cmd += ["--ref", r]
        gen_img(cmd)
        newest(OUT / "first").replace(dst)
        print("last", s["id"], flush=True)


# ------------------------------------------------------------------------------------------------ H3
CLEAN = ("One continuous shot with no cuts and no change of scene. Hands with correct anatomy, no extra people appear, no captions, "
         "no new text appears, no logos.")


def frames_for(sec):
    n = 0
    while 17 * n + 5 < sec * FPS:
        n += 1
    return max(17 * n + 5, 73)


def need_fresh_audio():
    """換了歌卻忘了跑 audio，specs、cut 會默默用舊混音。"""
    mix = OUT / "audio" / "mix.wav"
    if not mix.exists() or song_path().stat().st_mtime > mix.stat().st_mtime:
        sys.exit("歌比 work/audio/mix.wav 新或還沒有混音：先跑 songs audio，再跑 specs、cut")


@stage("specs")
def specs():
    """shots → work/h3/<鏡>/{spec.json, first.png, guide.wav, gen.json}。唱歌鏡：對嘴音軌＝人聲分軌那一段（audio.fixed）；
    無聲鏡：靜音、閉嘴。每鏡生成範圍＝[start−0.25, end+0.25]，17n+5 格、至少 73 格；步數照 tools/h3_steps.py（唱歌鏡全景以外、motion 走路 14 步，其餘 DMAD 4 步）。"""
    need_fresh_audio()
    import librosa
    import numpy as np
    import soundfile as sf
    shots = resolve_shots(); tl = timeline(); lines = tl["lines"]
    locked = set(CFG.get("locked", [])); rows = []
    P = S.get("pronoun", "he").capitalize()
    for s in shots:
        sid, st, en, kind = s["id"], s["start"], s["end"], s["kind"]
        cs = 0.0 if st == 0 else round(st - 0.25, 3)
        nf = frames_for(en + 0.25 - cs)
        rows.append({"id": sid, "start": st, "end": en, "kind": kind, "clip_start": cs, "frames": nf})
        if s.get("still"):
            continue
        if not (OUT / "first" / f"{sid}.png").exists():
            print("skip（沒有首幀）", sid); continue
        d = OUT / "h3" / sid; d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(OUT / "first" / f"{sid}.png", d / "first.png")
        n = int(round(nf / FPS * SR)); g = np.zeros(n, np.float32)
        if kind == "sing":
            f = OUT / "audio" / "vocals.wav"; sr0 = sf.info(str(f)).samplerate
            a, _ = sf.read(str(f), dtype="float32", start=int(cs * sr0), frames=int(nf / FPS * sr0) + 10)
            a = a.mean(1) if a.ndim > 1 else a
            a = librosa.resample(a, orig_sr=sr0, target_sr=SR) if sr0 != SR else a
            a = np.pad(a, (0, max(0, n - len(a))))[:n]
            pre, fd = int((st - cs) * SR), int(0.06 * SR)
            if pre > fd:
                a[:pre - fd] = 0; a[pre - fd:pre] *= np.linspace(0, 1, fd)
            g = a / max(1e-6, np.abs(a).max()) * 0.89
        sf.write(d / "guide.wav", g, SR, subtype="PCM_16")
        singer = s.get("singer", True)
        subs = [{"key": "S", "desc": S["desc"]}] if singer else []
        if not singer:
            more = " The motion stays smooth and natural."
        elif s.get("calm") or kind != "sing":
            more = (f" {P} moves slowly and calmly: breathing, blinking, small natural head movements; the hands move slowly and stay sharp; "
                    "no fast gestures, no motion blur.")
        else:
            more = " " + S["perform"]
        sh = {"camera": s.get("camera", "The camera holds a static shot on a tripod with a very slow, subtle push-in."), "action": s["action"] + more}
        cons = [CLEAN]
        if kind == "sing":
            txt = " ".join(l["text"] for l in lines if min(en, l["end"]) - max(st, l["start"]) >= 0.3) or "（輕聲哼唱）"
            cons.insert(0, f"{P} sings the words heard in <Audio 1>: lips, jaw and breathing follow every syllable and every held note of "
                           "<Audio 1> exactly; when <Audio 1> is silent the mouth is closed.")
            sh["dialogue"] = [{"subject": "S", "line": txt, "lang": "Chinese"}]
        elif singer:
            cons.insert(0, "Nobody speaks or sings; the mouth stays closed for the whole shot.")
        cons.append(CFG["studio"]["keep_h3"])
        if sid in locked:
            sh["camera"] = "The camera is locked on a tripod: no zoom, no push-in, no dolly; the framing stays exactly as in <Picture 1>."
            cons.append("The camera never moves closer: the framing stays exactly as in <Picture 1> from the first to the last frame.")
        cons += s.get("cons", [])
        sys.path.insert(0, str(REPO / "tools")); from h3_steps import draft_for   # noqa: E401  步數規則 docs/rules/H3.md
        spec = {"duration": round(nf / FPS, 3), "size": [1344, 768], "seed": seed_for(s),
                "draft": draft_for(s, kind == "sing" and singer),
                "style": CFG["studio"]["style"], "setting": CFG["studio"]["setting"], "first_frame": "first.png", "subjects": subs,
                "audio": {"fixed": {"file": "guide.wav"}}, "shots": [sh], "constraints": cons,
                "soundscape": "Only the singing voice from <Audio 1>." if kind == "sing" else "Quiet studio room tone only, no speech, no music.",
                "music": "N/A"}
        if s.get("last_first"):
            spec["last_frame"] = "first.png"                   # 尾幀＝首幀：防自己切鏡、冒道具（人會被鎖住不太動）
        elif s.get("last") and (OUT / "first" / f"{sid}_last.png").exists():
            shutil.copy2(OUT / "first" / f"{sid}_last.png", d / "last.png")   # 自訂尾幀（last 階段生）
            spec["last_frame"] = "last.png"
        (d / "gen.json").write_text(json.dumps({"clip_start": cs, "start": st, "end": en}), encoding="utf-8")
        new = json.dumps(spec, ensure_ascii=False, indent=1)
        if not (d / "spec.json").exists() or (d / "spec.json").read_text(encoding="utf-8") != new:   # 內容沒變就不重寫（不然已做好的鏡會被重跑）
            (d / "spec.json").write_text(new, encoding="utf-8")
    (OUT / "h3").mkdir(exist_ok=True)
    (OUT / "h3" / "timeline.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(rows), "shots; H3 frames", sum(r["frames"] for r in rows), flush=True)


def local_h3_ok():
    try:
        vram = int(subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                                  capture_output=True, text=True, timeout=20).stdout.split()[0]) / 1024
        return vram >= 15
    except Exception:
        return False


H3_BACKEND = os.environ.get("H3_BACKEND") or ("local" if local_h3_ok() else "colab")


@stage("h3")
def h3():
    """有 spec、還沒有 clip（或 spec 比 clip 新）的鏡都跑。H3_BACKEND＝local｜colab｜both（同 template_local）。"""
    only = os.environ.get("ONLY", "").split(); todo = []
    for d in sorted((OUT / "h3").iterdir()):
        sp, cl = d / "spec.json", d / "clip.mp4"
        if not sp.exists() or (only and d.name not in only):
            continue
        if not cl.exists() or cl.stat().st_mtime < sp.stat().st_mtime:
            todo.append(d)
    print(f"[h3] {len(todo)} 鏡（{H3_BACKEND}）", flush=True)
    if H3_BACKEND == "both":
        sys.path.insert(0, str(REPO / "cloud")); from hybrid_h3 import run_hybrid   # noqa: E402
        miss = run_hybrid(todo, PYH3, T)
        if miss:
            print("沒做出來：", " ".join(d.name for d in miss), flush=True)
    elif H3_BACKEND == "colab":
        run([sys.executable, REPO / "cloud" / "colab_h3.py", "batch"] + [d / "spec.json" for d in todo])
    else:
        fails = []
        for d in todo:
            t0 = time.time(); r = run([PYH3, T / "h3_shot.py", d / "spec.json", "--out", d], check=False)
            ok = (d / "clip.mp4").exists() and (d / "clip.mp4").stat().st_mtime > t0
            print(time.strftime("[%H:%M:%S]"), d.name, "OK" if ok else "FAIL", f"{time.time() - t0:.0f}s", flush=True)
            if not ok:
                fails.append(d.name); (d / "run_err.txt").write_text((r.stdout + r.stderr)[-6000:], encoding="utf-8")
        if fails:
            print("失敗：", fails, "（看 work/h3/<鏡>/run_err.txt）", flush=True)
    clipsheet()


def used_range(s):
    g = OUT / "h3" / s["id"] / "gen.json"
    cs = json.loads(g.read_text(encoding="utf-8"))["clip_start"] if g.exists() else s["start"] - 0.25
    a = s["start"] - cs
    return a, a + (s["end"] - s["start"])


def clipsheet():
    """每鏡成片用到範圍的開頭／1/3／2/3／結尾 4 格 → work/review/clips_<n>.jpg（人工關卡 2：換臉、多出人、自己切鏡、手糊）。"""
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, str(REPO / "tools")); from fonts import font   # noqa: E401
    shots = resolve_shots(); rv = OUT / "review"; rv.mkdir(exist_ok=True)
    f = ImageFont.truetype(font("jhbd"), 20); rows = []
    for s in shots:
        c = OUT / "h3" / s["id"] / "clip.mp4"
        if not c.exists():
            continue
        a, b = used_range(s); tiles = []
        for t in (a + 0.05, a + (b - a) / 3, a + 2 * (b - a) / 3, b - 0.1):
            p = rv / "_t.jpg"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(c), "-frames:v", "1", "-vf", "scale=384:220", str(p)])
            tiles.append(Image.open(p).convert("RGB"))
        row = Image.new("RGB", (384 * 4 + 160, 220), (25, 25, 25)); ImageDraw.Draw(row).text((6, 90), s["id"] + "\n" + s["kind"], font=f, fill=(255, 220, 0))
        for i, t in enumerate(tiles):
            row.paste(t, (160 + i * 384, 0))
        rows.append(row)
    for k in range(0, len(rows), 8):
        part = rows[k:k + 8]; im = Image.new("RGB", (part[0].width, 224 * len(part)), (0, 0, 0))
        for i, r_ in enumerate(part):
            im.paste(r_, (0, i * 224))
        im.save(rv / f"clips_{k // 8}.jpg", quality=82)
    (rv / "_t.jpg").unlink(missing_ok=True)
    print(f"→ 人工關卡 2：work/review/clips_*.jpg（{len(rows)} 鏡）。重拍：studio.json 那鏡加 seed_bump（會自己切鏡的再加 last_first），跑 specs h3", flush=True)


# ------------------------------------------------------------------------------------------------ 成片
def sh_(cmd, cwd=None):
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, cwd=cwd)


FIT = "scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,crop=1920:1080"


def segment(s, seg_dir, vsr_dir):
    k = s["id"]; out = seg_dir / f"{k}.mp4"
    n = int(round(s["end"] * FPS)) - int(round(s["start"] * FPS))
    clip, first = OUT / "h3" / k / "clip.mp4", OUT / "first" / f"{k}.png"
    if not s.get("still") and clip.exists():
        src, mode = clip, "clip"
    elif first.exists():
        src, mode = first, "still" if s.get("still") else "stand-in"
    else:
        src, mode = None, "slate"
    if src is not None and out.exists() and out.stat().st_mtime > src.stat().st_mtime and abs(dur(out) - n / FPS) < 0.5 / FPS:
        return out, mode
    if mode == "slate":
        sh_(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x303030:s=1920x1080:r=24", "-vf",
             f"drawtext=text='{k}':fontcolor=white:fontsize=120:x=(w-text_w)/2:y=(h-text_h)/2", "-frames:v", str(n), "-c:v", "libx264",
             "-pix_fmt", "yuv420p", out])
    elif mode in ("still", "stand-in"):
        sh_(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", src, "-vf",
             f"{FIT},zoompan=z='1+0.0006*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps=24,format=yuv420p",
             "-frames:v", str(n), "-c:v", "libx264", "-crf", "14", out])
    else:
        v = clip
        if UPSCALE == "rtxvsr":
            v = vsr_dir / f"{k}.mp4"
            if v.exists() and v.stat().st_mtime < clip.stat().st_mtime:
                v.unlink()                                      # 重拍過：重新放大（upscale_vsr.py 不覆寫舊檔）
            if not v.exists():
                run([PYH3, T / "upscale_vsr.py", "--source", clip, "--output", v])
        a, _ = used_range(s)
        sh_(["ffmpeg", "-y", "-v", "error", "-ss", f"{round(a * FPS) / FPS:.4f}", "-i", v, "-an", "-vf", f"{FIT},fps={FPS},setsar=1,tpad=stop_mode=clone:stop=-1",
             "-frames:v", str(n), "-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p", out])
    return out, mode


def ts_ass(t):
    t = max(0.0, t); h, r = divmod(t, 3600); m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"



def title_vertical(tc):
    """片名卡 vertical 版型：左側人物資訊（明體名字、金色細線畫出來、英文襯線大寫、生卒地點）逐行往上浮出；
    右側歌名直排、旁邊一條金色直線往下畫、系列名小字直排。人走進來時 left_start 晚一點，等人走過去再出字。"""
    end = float(tc.get("end", tc.get("sec", 8.0)))
    serif, latin = tc.get("font", "Noto Serif TC"), tc.get("latin_font", "Cambria")
    gold, white, gray = tc.get("gold", "&H0070C0E8&"), "&H00F4F4F4&", "&H00B8B8B8&"
    x, xr = int(tc.get("side_margin", 120)), 1920 - int(tc.get("right_margin", 130))
    look = "\\bord0\\shad2\\4a&H90&"
    ev = []

    def d(a, body, b=None):
        ev.append(f"Dialogue: 1,{ts_ass(a)},{ts_ass(b or end)},Series,,0,0,0,,{body}")

    def rise(a, an, px, py, txt, fs, col, font=serif, sp=0, bold=False, b=None):
        d(a, "{" + f"\\an{an}\\move({px},{py + 16},{px},{py},0,700)\\fad(700,800)\\fn{font}\\fs{fs}\\c{col}\\fsp{sp}"
          + ("\\b1" if bold else "\\b0") + look + "}" + txt, b)

    def bar(a, px, py, w, h, horizontal=True, b=None):
        c0 = f"\\clip({px},{py - 2},{px + 1},{py + h + 2})" if horizontal else f"\\clip({px - 2},{py},{px + w + 2},{py + 1})"
        c1 = f"\\clip({px},{py - 2},{px + w},{py + h + 2})" if horizontal else f"\\clip({px - 2},{py},{px + w + 2},{py + h})"
        d(a, "{" + f"\\an7\\pos({px},{py})\\p1\\c{gold}\\bord0\\shad0\\fad(0,800){c0}\\t(0,1000,{c1})" + "}"
          + f"m 0 0 l {w} 0 {w} {h} 0 {h}" + "{\\p0}", b)

    a = float(tc.get("left_start", tc.get("start", 0.8)))
    le = float(tc["left_end"]) if tc.get("left_end") else None    # 左側可以比右側早收（人走進來前淡出）
    rise(a, 1, x, 500, tc.get("name", ""), 92, white, sp=14, bold=True, b=le)
    bar(a + 0.35, x + 4, 528, 300, 2, b=le)
    rise(a + 0.6, 7, x + 2, 548, tc.get("name_en", "").upper(), 36, gold, font=latin, sp=16, b=le)
    rise(a + 0.85, 7, x + 2, 602, tc.get("info", ""), 34, gray, sp=4, b=le)
    r = float(tc.get("start", 0.8))
    title = tc.get("text", "")
    rise(r, 9, xr, 236, "\\N".join(title), 96, white, bold=True)
    bar(r + 0.4, xr - 120, 240, 2, 120 * len(title), horizontal=False)
    rise(r + 0.7, 9, xr - 140, 236, "\\N".join(tc.get("series", "")), 38, gold)
    return ev

def write_ass(path, tl):
    """字幕：片名卡（左上系列名＋中下歌名與主唱，前奏時出現）＋歌詞（下方置中，選填英文第二行）。顏色、字級在 studio.json 的 subs。"""
    sub = CFG.get("subs", {}); tc = CFG.get("title_card", {})
    col = sub.get("color", "&H00FFFFFF"); en_col = sub.get("en_color", "&H00D8D8D8"); acc = tc.get("color", "&H0080C8FF")
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Lyric,{FONT},{sub.get('size', 58)},{col},{col},&H00202020,&H64000000,1,0,0,0,100,100,2,0,1,3,1,2,80,80,{sub.get('margin', 70)},1
Style: En,{FONT},{int(sub.get('size', 58) * 0.62)},{en_col},{en_col},&H00202020,&H64000000,0,0,0,0,100,100,0,0,1,2,1,2,80,80,{sub.get('margin', 70) - 2},1
Style: Series,{FONT},40,{acc},{acc},&H00202020,&H00000000,1,0,0,0,100,100,6,0,1,2,0,7,70,70,60,1
Style: Title,{FONT},96,&H00FFFFFF,&H00FFFFFF,&H00202020,&H00000000,1,0,0,0,100,100,8,0,1,4,1,1,90,90,170,1
Style: Who,{FONT},48,{acc},{acc},&H00202020,&H00000000,1,0,0,0,100,100,4,0,1,3,0,1,90,90,110,1
Style: SideL,{FONT},60,&H00FFFFFF,&H00FFFFFF,&H00202020,&H00000000,1,0,0,0,100,100,4,0,1,3,1,4,{tc.get('side_margin', 110)},90,0,1
Style: SideR,{FONT},60,&H00FFFFFF,&H00FFFFFF,&H00202020,&H00000000,1,0,0,0,100,100,4,0,1,3,1,6,90,{tc.get('side_margin', 110)},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    if tc.get("layout") == "sides":
        # 兩側版型：人物資訊在左、歌名在右，人走在中間不擋字。每行 [文字, 字級, 顏色(acc／white／gray)]
        a, b = float(tc.get("start", 0.8)), float(tc.get("end", tc.get("sec", 8.0))); fade = "{\\fad(700,700)}"
        cols = {"acc": acc, "white": "&H00FFFFFF", "gray": "&H00C8C8C8"}
        for side, style in (("left", "SideL"), ("right", "SideR")):
            rows = tc.get(side) or []
            if rows:
                txt = "\\N".join(f"{{\\fs{r[1]}\\c{cols.get(r[2], r[2])}}}{r[0]}" for r in rows)
                ev.append(f"Dialogue: 0,{ts_ass(a)},{ts_ass(b)},{style},,0,0,0,,{fade}{txt}")
    elif tc.get("layout") == "vertical":
        ev += title_vertical(tc)
        if tc.get("outro"):                                   # 唱完再放一次：{"start", "left_start", "end"}（成片秒數）
            ev += title_vertical({**tc, **tc["outro"]})
    elif tc.get("text"):
        a, b = 0.3, float(tc.get("sec", 4.0)); fade = "{\\fad(400,500)}"
        ev.append(f"Dialogue: 0,{ts_ass(a)},{ts_ass(b)},Series,,0,0,0,,{fade}{tc.get('series', '')}")
        ev.append(f"Dialogue: 0,{ts_ass(a)},{ts_ass(b)},Title,,0,0,0,,{fade}{tc['text']}")
        ev.append(f"Dialogue: 0,{ts_ass(a)},{ts_ass(b)},Who,,0,0,0,,{fade}{tc.get('sub', '')}")
    lines = tl["lines"]
    for i, l in enumerate(lines):
        a = l["start"] - 0.1
        b = min(l["end"] + 0.6, lines[i + 1]["start"] - 0.15) if i + 1 < len(lines) else l["end"] + 1.2
        en_on = sub.get("english") and l.get("en")
        txt = l["show"] + (f"\\N{{\\rEn}}{l['en']}" if en_on else "")
        ev.append(f"Dialogue: 1,{ts_ass(a)},{ts_ass(b)},Lyric,,0,0,0,,{{\\fad(150,200)}}{txt}")
    Path(path).write_text(head + "\n".join(ev) + "\n", encoding="utf-8-sig")


@stage("cut")
def cut():
    """放大 → 每鏡剪成片段 → 串起來 → 音軌固定增益拉到 −16 LUFS（限幅，AAC 後真峰值 ≤ −1）→ ASS 字幕燒進去 → 成片＋手機版。"""
    need_fresh_audio()
    shots = resolve_shots(); tl = timeline(); total = tl["marks"]["total"]
    post = OUT / "post"; seg_dir = post / "seg"; vsr_dir = post / "vsr"; cutd = OUT / "cut"
    for d in (post, seg_dir, vsr_dir, cutd):
        d.mkdir(parents=True, exist_ok=True)
    segs, modes = [], {}
    for s in shots:
        p, m = segment(s, seg_dir, vsr_dir); segs.append(p); modes[s["id"]] = m
    stand = [k for k, m in modes.items() if m in ("stand-in", "slate")]
    if stand:
        print(f"⚠ 這 {len(stand)} 鏡還沒有 H3，用首幀／鏡號代替：{' '.join(stand)}", flush=True)
    lst = seg_dir / "list.txt"; lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in segs), encoding="utf-8")
    vid = post / "video_raw.mp4"
    sh_(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", vid])
    mix = OUT / "audio" / "mix.wav"; raw = post / "mix_raw.wav"
    # 不用 loudnorm（峰值放不下時會偷偷退回動態壓縮）：量 → 固定增益 → 限幅，迴圈到 −16 LUFS
    sh_(["ffmpeg", "-y", "-v", "error", "-i", mix, "-af", f"apad=whole_dur={total:.3f}", "-t", f"{total:.3f}", "-c:a", "pcm_f32le", raw])
    gain = 0.0
    for _ in range(5):
        r = subprocess.run(["ffmpeg", "-i", str(raw), "-af", f"volume={gain:.2f}dB,alimiter=limit=0.70:level=false:attack=2:release=80,ebur128",
                            "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        got = re.findall(r"I:\s*(-?[\d.]+) LUFS", r.stderr); got = float(got[-1]) if got else -16.0
        if abs(got + 16.0) <= 0.3:
            break
        gain += -16.0 - got
    final_wav = post / "final_audio.wav"
    sh_(["ffmpeg", "-y", "-v", "error", "-i", raw, "-af", f"volume={gain:.2f}dB,alimiter=limit=0.70:level=false:attack=2:release=80",
         "-ar", str(SR), "-c:a", "pcm_s16le", final_wav])
    write_ass(post / "subs.ass", tl)
    out = cutd / f"{CUT_NAME}_1080p.mp4"
    # ffmpeg 的 subtitles 濾鏡吃不了中文路徑：在 post/ 裡跑、只給相對檔名
    sh_(["ffmpeg", "-y", "-v", "error", "-i", "video_raw.mp4", "-i", "final_audio.wav", "-vf", "subtitles=subs.ass", "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart",
         "-t", f"{total:.3f}", "out.mp4"], cwd=post)
    shutil.move(str(post / "out.mp4"), out)
    phone = cutd / f"{CUT_NAME}_phone.mp4"; kbps = int(27e6 * 8 / total / 1000) - 96   # 手機版：兩段式定碼率約 27 MB
    for ps in (1, 2):
        sh_(["ffmpeg", "-y", "-v", "error", "-i", out, "-vf", "scale=1280:720", "-c:v", "libx264", "-b:v", f"{kbps}k", "-pass", str(ps),
             "-passlogfile", str(post / "phone2pass"), "-preset", "slow"] +
            (["-an", "-f", "null", "NUL" if os.name == "nt" else "/dev/null"] if ps == 1 else ["-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", phone]))
    print("成片", out, f"{total:.1f}s", f"手機版 {phone.stat().st_size / 1e6:.1f}MB", flush=True)


# ------------------------------------------------------------------------------------------------ 自審
def audio_checks():
    """濾掉 300 Hz 以下（手機喇叭放不出來）的音量破洞、突然掉音；最後一句之後人聲還在唱；對齊低分句。"""
    import librosa
    import numpy as np
    from scipy.signal import butter, sosfilt
    sr = 16000; m = timeline()["marks"]
    y = sosfilt(butter(4, 300, "hp", fs=sr, output="sos"), librosa.load(str(OUT / "audio" / "mix.wav"), sr=sr, mono=True)[0])
    db = lambda a: 20 * np.log10(np.sqrt(np.mean(a ** 2)) + 1e-7)
    h = int(0.05 * sr); a0, end = int(m["first"] * sr), int(m["last_end"] * sr)
    low = [db(y[i:i + h]) < -42 for i in range(a0, end, h)]; holes = []; i = 0
    while i < len(low):
        j = i
        while j < len(low) and low[j]:
            j += 1
        if (j - i) * 0.05 >= 0.1:
            holes.append((round(m["first"] + i * 0.05, 2), round(m["first"] + j * 0.05, 2)))
        i = max(j, i + 1)
    e = [db(y[int(t * sr):int((t + 0.5) * sr)]) for t in np.arange(m["first"], m["last_end"], 0.5)]
    drops = [(round(m["first"] + k * 0.5, 1), round(float(e[k - 1] - e[k]), 1)) for k in range(1, len(e)) if e[k - 1] - e[k] >= 8]
    al = json.loads((OUT / "song" / "align_S.json").read_text(encoding="utf-8")); rows = al["rows"]
    v = librosa.load(al["vocals"], sr=sr, mono=True)[0]
    sung = np.median([db(v[int(x["start"] * sr):int(x["end"] * sr)]) for x in rows if x["end"] - x["start"] > 0.3])
    t0 = rows[-1]["end"] + 0.3; on = [t for t in np.arange(t0, len(v) / sr - 1, 1.0) if db(v[int(t * sr):int((t + 1) * sr)]) > sung - 8]
    rep = dict(holes=holes, drops=drops, tail=(round(float(on[0]), 1), round(float(on[-1]) + 1, 1)) if len(on) >= 2 else None,
               low_ok=[(round(x["start"], 1), x["text"]) for x in rows if 0 <= x.get("ok", 1) < 0.3])
    (OUT / "review").mkdir(parents=True, exist_ok=True)
    (OUT / "review" / "audio_check.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("⚠ 音量／人聲檢查（每一條都要交代）：", flush=True)
    print("  音量破洞（唱歌段內、300 Hz 以上，秒）：", holes, flush=True)
    print("  突然掉音（秒，掉幾 dB）：", drops, flush=True)
    print("  最後一句之後人聲還在唱（歌曲時間）：", rep["tail"], flush=True)
    print("  對齊低分句（一定要查）：", rep["low_ok"], flush=True)


@stage("review")
def review():
    """每秒一格接觸表（時間碼・鏡號・當下歌詞）＋H3 自己切鏡偵測（用到的範圍內）＋響度。最後一定要人看完整成片。"""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, str(REPO / "tools")); from fonts import font   # noqa: E401
    audio_checks()
    shots = resolve_shots(); tl = timeline()
    video = OUT / "cut" / f"{CUT_NAME}_1080p.mp4"
    rv = OUT / "review" / f"fc_v{VER}"; rv.mkdir(parents=True, exist_ok=True)
    F = ImageFont.truetype(font("jhbd"), 22); tiles = []
    for i in range(int(dur(video))):
        t = i + 0.5; p = rv / f"f_{i:03d}.jpg"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=640:360", str(p)])
        sid = next((s["id"] for s in shots if s["start"] <= t < s["end"]), "END")
        lyr = next((l["show"][:22] for l in tl["lines"] if l["start"] - 0.05 <= t <= l["end"] + 0.25), "")
        im = Image.open(p).convert("RGB"); tile = Image.new("RGB", (640, 394)); tile.paste(im, (0, 34))
        ImageDraw.Draw(tile).text((6, 4), f"{int(t // 60)}:{t % 60:04.1f}  {sid}  {lyr}", font=F, fill=(255, 230, 0))
        tiles.append(tile)
    for k in range(0, len(tiles), 12):
        im = Image.new("RGB", (640 * 4 + 12, 394 * 3 + 8), (40, 40, 40))
        for j, tile in enumerate(tiles[k:k + 12]):
            im.paste(tile, ((j % 4) * 644, (j // 4) * 398))
        im.save(rv / f"sheet_{k // 12:02d}.jpg", quality=86)
    cc = {}                                                   # 自己切鏡：相鄰格平均差 > max(18, 6×中位數)；構圖漂走：跟第一格相關係數 < 0.7
    for s in shots:
        v = OUT / "h3" / s["id"] / "clip.mp4"
        if not v.exists() or s.get("still"):
            continue
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(v), "-vf", "scale=168:96,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        f = np.frombuffer(raw, np.uint8).reshape(-1, 96, 168).astype(np.float32)
        d = np.abs(np.diff(f, axis=0)).mean(axis=(1, 2)); thr = max(18.0, 6 * float(np.median(d)))
        a0 = f[0] - f[0].mean()
        corr = [float((a0 * (g - g.mean())).sum() / (np.linalg.norm(a0) * np.linalg.norm(g - g.mean()) + 1e-6)) for g in f]
        u0, u1 = used_range(s)
        bad = [round((i + 1) / FPS, 2) for i, x in enumerate(d) if x > thr and u0 <= (i + 1) / FPS <= u1]
        drift = next((round(i / FPS, 2) for i, c in enumerate(corr) if c < 0.7 and u0 <= i / FPS <= u1), None)
        if bad or drift is not None:
            cc[s["id"]] = dict(cuts=bad, drift=drift, used=[round(u0, 2), round(u1, 2)])
    (OUT / "review" / "cutcheck.json").write_text(json.dumps(cc, ensure_ascii=False, indent=1), encoding="utf-8")
    r = subprocess.run(["ffmpeg", "-i", str(video), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace").stderr
    lufs = re.findall(r"I:\s*(-?[\d.]+) LUFS", r); tp = re.findall(r"Peak:\s*(-?[\d.]+) dBFS", r)
    print(f"接觸表 {(len(tiles) + 11) // 12} 張 → {rv}", flush=True)
    print(f"響度 {lufs[-1] if lufs else '?'} LUFS、真峰值 {tp[-1] if tp else '?'} dBTP（目標 −16、≤ −1）", flush=True)
    print("可能自己切鏡／構圖漂走（走位多的鏡會誤報，要人看）：", cc or "無", flush=True)
    print("→ 人工關卡 3：一張張看接觸表（臉、耳機、麥克風、字幕位置、背景布顏色），最後一定要人看完整成片", flush=True)


@stage("srt")
def srt():
    tl = timeline()

    def ts(t):
        t = max(0.0, t); h, r = divmod(t, 3600); m, s = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"
    rows = [(l["start"] - 0.1, l["end"] + 0.4, l["show"].replace("　", " ") + (f"\n{l['en']}" if CFG.get("subs", {}).get("english") and l.get("en") else ""))
            for l in tl["lines"]]
    p = OUT / "cut" / f"{CUT_NAME}.srt"; p.parent.mkdir(exist_ok=True)
    p.write_text("\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(rows, 1)), encoding="utf-8")
    print(p, len(rows), flush=True)


ORDER = [songs, audio, chars, studio, frames, specs, h3, cut, review, srt]
ALL = {f.__name__: f for f in ORDER + [lyrics, music3, yue, pick, fix, last]}

if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    want = [a for a in ARGS if a in ALL]
    bad = [a for a in ARGS if not a.startswith("--") and a not in ALL and not (ARGS.index(a) > 0 and ARGS[ARGS.index(a) - 1] in ("--studio", "--ver"))]
    if bad:
        sys.exit(f"不認得的 stage：{bad}；可用：{' '.join(ALL)}")
    for f in ([ALL[w] for w in want] or ORDER):
        f()
