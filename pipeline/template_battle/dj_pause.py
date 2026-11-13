"""DJ 口白加停頓：Ming 念得一口氣到底，重點句（「這題，我不答」）後面要留白才有重量。
在指定字後面插靜音，改寫 work/voice/ming/dj_<key>.wav；原檔留 dj_<key>_orig.wav（之後重跑都從原檔算）。
改寫自上游 pipeline/template_battle/dj_pause.py（上游 b7189aa，2026-11-08）。與上游不同：本分支沒有 dj_align.json（make_battle.py
整句放 DJ 口白），字的時間當場用 Qwen3-ForcedAligner（tools/stt.py 的 load_song_aligner）對齊原檔。

用法（Voice venv，片子資料夾）："%PY_VOICE%" dj_pause.py verdict 下毒=0.3 是誰=0.55 你贏=1.2
  片語要照 battle.json 的 dj.tts（沒寫就 dj.lines）那句的寫法；同一片語出現多次取第一個。
插完重跑 make_battle.py audio（之後的 specs、h3、cut 跟著重跑）：插停頓會改變後面每個字的時間，DJ 有對嘴的鏡要在生成影片之前插。
⚠ 切點一律用 dj_tail_check.tail_end（句尾真正結束的地方）：〈Bravo 之戰〉v5 以前照對齊器的字尾切，字尾報早 0.1–0.3 秒，
每句最後一個字被砍、尾巴被推到停頓後面，使用者聽出「DJ 講話的尾句都斷掉」（2026-11-08）。插完會自動跑句尾檢查。"""
import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
from dj_tail_check import hard_cuts, tail_end  # noqa: E402

if len(sys.argv) < 3:
    sys.exit(__doc__)
CFG = json.loads((HERE / "battle.json").read_text(encoding="utf-8"))
sys.path.insert(0, str((HERE / CFG.get("repo_dir", "../../..") / "tools").resolve()))
import stt  # noqa: E402

KEY = sys.argv[1]
AFTER = {a.split("=")[0]: float(a.split("=")[1]) for a in sys.argv[2:]}
DJ = CFG["dj"]
text = DJ.get("tts", {}).get(KEY) or DJ["lines"][KEY]
M = HERE / "work" / "voice" / "ming"
src, orig = M / f"dj_{KEY}.wav", M / f"dj_{KEY}_orig.wav"
if not orig.exists():
    shutil.copy(src, orig)
x, sr = sf.read(str(orig), dtype="float32", always_2d=True)
clean = re.sub(r"[^一-鿿A-Za-z0-9]", "", text)
words = stt.load_song_aligner()(x.mean(1), sr, [clean])[0]["words"]
txt = "".join(w["w"] for w in words)
cuts = []
for phrase, sec in AFTER.items():
    i = txt.find(phrase)
    if i < 0:
        raise SystemExit(f"「{phrase}」不在 DJ {KEY} 的對齊文字「{txt}」裡")
    pos = i + len(phrase); n = 0
    for w in words:
        n += len(w["w"])
        if n >= pos:
            cuts.append((w["e"], sec, w["w"])); break
cuts.sort()
parts, last = [], 0
for t, sec, w in cuts:
    # 切在句尾真正結束的地方（對齊器的字尾常早 0.1–0.3 秒，照它切會砍掉最後一個字、尾巴被推到停頓後面）
    c = int(tail_end(x, sr, t, limit=min(.5, sec - .08)) * sr)
    parts += [x[last:c], np.zeros((int(sec * sr), x.shape[1]), "float32")]; last = c
    print(w, round(t, 2), "→ 切在", round(c / sr, 2), "+", sec)
parts.append(x[last:])
y = np.concatenate(parts)
sf.write(str(src), y, sr, subtype="PCM_16")
print("長度", round(len(x) / sr, 2), "→", round(len(y) / sr, 2), "；接著重跑 make_battle.py audio")
r = hard_cuts(y.mean(1), sr)
print("句尾檢查：", "OK" if not r else r)
