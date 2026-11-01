"""挑歌（YuE2 唱詞歌）：量每首拍速，只留目標 BPM（YuE2 約一半會掉到 89 或跳 152），
再用 BS-RoFormer 分人聲 → 歌詞強制對齊（Qwen3-ForcedAligner）→ 逐句聽寫（Qwen3-ASR），依字對到的比例排序。
聽寫只是初篩，最後一定要人聽。
用法：<Voice venv>/python pick_song.py <輸出資料夾> <歌詞.txt> [--bpm 143.6]（歌詞可含 [Verse] 等段落標籤）→ <資料夾>/pick.json
需要：Voice venv 的 transformers、opencc、librosa、audio-separator（模型 model_bs_roformer_ep_317_sdr_12.9755.ckpt）、Qwen3-ASR 與 Qwen3-ForcedAligner 權重（setup/downloads_qwen_asr.json）。"""
import re, os, sys, difflib, json
from pathlib import Path
import numpy as np, soundfile as sf, librosa
from audio_separator.separator import Separator
AI =Path(os.environ.get("AI_ROOT", r"C:\AI"))  # AI_ROOT = install root (default C:\AI)
sys.path.insert(0, str(Path(__file__).resolve().parent)); import stt
import opencc
d, lyr = Path(sys.argv[1]), Path(sys.argv[2])
TARGET = float(sys.argv[sys.argv.index("--bpm") + 1]) if "--bpm" in sys.argv else 143.6
lines = [l.strip() for l in lyr.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("[")]
cc = opencc.OpenCC("s2twp"); norm = lambda s: re.sub(r"[^\u4e00-\u9fff]", "", cc.convert(s))
align = stt.load_song_aligner()
hear = stt.load_song_asr()
sep = d / "sep"; sep.mkdir(exist_ok=True); rep = {}; separator = None
for f in sorted(d.glob("*.flac")):
    y, sr = librosa.load(str(f), sr=22050, mono=True)
    bpm = float(np.atleast_1d(librosa.beat.beat_track(y=y, sr=sr)[0])[0])
    if abs(bpm - TARGET) > 1:
        print(f.name, "BPM", round(bpm, 1), "→ 不要"); continue
    voc = next(sep.glob(f"{f.stem}_(Vocals)*"), None)
    if voc is None:
        if separator is None:
            separator = Separator(model_file_dir=str(AI / "Voice" / "models" / "separator"), output_dir=str(sep), output_format="FLAC", log_level=40)
            separator.load_model(model_filename="model_bs_roformer_ep_317_sdr_12.9755.ckpt")
        separator.separate(str(f))
        voc = next(sep.glob(f"{f.stem}_(Vocals)*"))
    a, vsr = sf.read(str(voc), dtype="float32", always_2d=True); a = a.mean(1)
    oks = []
    for l, s in zip(lines, align(a, vsr, lines)):
        t = cc.convert(hear(a[max(0, int((s["start"] - .3) * vsr)):int((s["end"] + .3) * vsr)], vsr))
        oks.append(sum(b.size for b in difflib.SequenceMatcher(None, norm(l), norm(t), autojunk=False).get_matching_blocks()) / max(1, len(norm(l))))
    rep[f.name] = {"bpm": round(bpm, 1), "char_ok": round(float(np.mean(oks)), 2), "lines_ok": int(sum(o >= .7 for o in oks)), "lines": len(oks)}
    print(f.name, rep[f.name], flush=True)
(d / "pick.json").write_text(json.dumps(dict(sorted(rep.items(), key=lambda kv: -kv[1]["char_ok"])), ensure_ascii=False, indent=1), encoding="utf-8")
print("排序結果寫在", d / "pick.json")
