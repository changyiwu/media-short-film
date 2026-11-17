"""全片音量掃描（上游使用者 2026-11-02 的標準）：濾掉 300 Hz 以下（手機喇叭放不出來）、單聲道，
抓 50 毫秒低於 −42 dB 持續 0.1 秒以上的破洞、相鄰半秒掉 8 dB 以上的地方。成片和手機版都要量。
移植自上游 pipeline/template_battle/level_scan.py（上游 e634cce）；預設檔改 work/audio/mix.wav，也可以直接給 mp4。
make_battle.py review 的音量檢查只看混音到音樂結束為止，要看成片（含片尾、觀眾聲）就用這支。

用法（片子資料夾）：python level_scan.py [mix.wav 或 成片.mp4] [開始秒 結束秒 每段秒]"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import scipy.signal as ss
import soundfile as sf

sys.stdout.reconfigure(encoding="utf-8")
f = Path(sys.argv[1] if len(sys.argv) > 1 else "work/audio/mix.wav")
if f.suffix.lower() not in (".wav", ".flac"):
    tmp = Path(tempfile.mkdtemp()) / "a.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", f.name, "-vn", "-ac", "2", "-ar", "48000", str(tmp)], check=True, cwd=f.parent)
    f = tmp
x, sr = sf.read(str(f), dtype="float32", always_2d=True)
x = ss.sosfilt(ss.butter(4, 300, "hp", fs=sr, output="sos"), x.mean(1))
db = lambda z: 20 * np.log10(np.sqrt(np.mean(z ** 2)) + 1e-6)
h = int(0.05 * sr)
e = np.array([db(x[i:i + h]) for i in range(0, len(x) - h, h)])
low = e < -42
holes, i = [], 0
while i < len(low):
    if low[i]:
        j = i
        while j < len(low) and low[j]:
            j += 1
        if (j - i) * 0.05 >= 0.1:
            holes.append((round(i * 0.05, 2), round(j * 0.05, 2)))
        i = j
    else:
        i += 1
print("長", round(len(x) / sr, 1), "破洞", holes)
q = int(0.5 * sr)
s = np.array([db(x[i:i + q]) for i in range(0, len(x) - q, q)])
print("掉 8 dB", [(round(k * 0.5, 1), round(float(s[k]), 1), round(float(s[k + 1]), 1)) for k in range(len(s) - 1) if s[k] - s[k + 1] >= 8])
if len(sys.argv) > 4:
    a, b, st = map(float, sys.argv[2:5])
    print([(round(t, 1), round(float(db(x[int(t * sr):int((t + st) * sr)])))) for t in np.arange(a, b, st)])
