"""局部重唱候選逐句比對：窗內每句人聲、混音各聽寫一次（不給提示，拼音比），量窗前、窗後跟定稿的時間差，和整窗有沒有多唱。
挑好了再用 splice_resing.py 接回定稿，接完重跑 songs、lyric_audit.py、gap_check.py。
改寫自上游 pipeline/template_battle/resing_lines.py（上游 88a1b6c）。與上游不同：候選直接給檔案（上游寫死 Suno 送件標籤與歌名），
聽寫走 tools/stt.py 的 load_song_asr()（Qwen3-ASR），檔案在 work/song/resing/。
⚠ 候選要是「同一首歌、同一個編曲」的重唱（Suno 局部重唱之類）；YuE2 換 seed 是另一首歌，拍子、旋律都對不上，不能拿來接。

用法（Voice venv，片子資料夾，先跑過 make_battle.py songs）：
  "%PY_VOICE%" resing_lines.py <A|B> <窗開始秒> <窗結束秒> 候選1.wav [候選2.wav …]   → work/song/resing/lines_<第一個候選檔名>.md"""
import json
import subprocess
import sys
from pathlib import Path

import librosa
import numpy as np
import opencc

import make_battle as mb
from lyric_audit import NOTCH, load_hear, miss

sys.stdout.reconfigure(encoding="utf-8")
if len(sys.argv) < 5:
    sys.exit(__doc__)
who = sys.argv[1]; w0, w1 = float(sys.argv[2]), float(sys.argv[3]); cands = [Path(p).resolve() for p in sys.argv[4:]]
D = mb.OUT / "song" / "resing"; D.mkdir(parents=True, exist_ok=True)
AL = json.loads((mb.OUT / "song" / f"align_{who}.json").read_text(encoding="utf-8"))
SR = 16000
cc = opencc.OpenCC("s2twp"); hear = load_hear(mb.HERE)


def lag_ms(y, ref, a, b):
    a, b = max(0, int(a * SR)), int(b * SR)
    if b - a < SR:
        return float("nan")
    return (int(np.argmax(np.correlate(y[a:b][::8], ref[a:b][::8], "full"))) - (b - a) // 8 + 1) * 8 / SR * 1000


ref, _ = librosa.load(AL["song"], sr=SR, mono=True)
rows = [r for r in AL["rows"] if r["start"] >= w0 - 0.3 and r["end"] <= w1 + 0.3]
out = [f"# {who} 窗 {w0}–{w1}（定稿 {Path(AL['song']).name}）"]
for p in cands:
    y, _ = librosa.load(str(p), sr=SR, mono=True)
    lag, lag2 = lag_ms(y, ref, w0 - 12, w0 - 2), lag_ms(y, ref, w1 + 2, w1 + 12)
    clip = D / f"{p.stem}_clip.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0, w0 - 2)}", "-to", f"{w1 + 2}", "-i", str(p), "-ar", "44100", str(clip)], check=True)
    voc, _inst = mb.sep_stems(clip, D / "sep")
    v, _ = librosa.load(str(voc), sr=SR, mono=True)
    off = min(2.0, w0)                                         # clip 從 w0－2 秒開始（窗太靠前就從 0）
    out.append(f"\n## {p.name}  長度 {len(y) / SR:.1f} 秒  窗前差 {lag:.0f} ms  窗後差 {lag2:.0f} ms（候選比定稿晚為正）")
    out.append("整窗人聲：" + hear(v))
    out.append("整窗混音：" + hear(y[int(max(0, w0 - .2) * SR):int((w1 + .2) * SR)]))
    for r in rows:
        want = NOTCH.sub("", cc.convert(r["text"]))
        s0, s1 = r["start"] - 0.3, r["end"] + 0.35
        hv = hear(v[int(max(0, s0 - w0 + off) * SR):int((s1 - w0 + off) * SR)]); hm = hear(y[int(max(0, s0) * SR):int(s1 * SR)])
        mm = miss(want, hm)
        out.append(f"- {r['start']:.1f} {want} ｜人聲 {hv} ｜混音 {hm} ｜都缺 {''.join(c for c in miss(want, hv) if c in mm)}")
    print("\n".join(out[-len(rows) - 3:]), flush=True)
dst = D / f"lines_{cands[0].stem}.md"
dst.write_text("\n".join(out) + "\n", encoding="utf-8")
print("→", dst, flush=True)
