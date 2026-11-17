"""人聲破洞檢查：接過重唱、蓋過句子之後，人聲有沒有被接出空洞（上游〈向日葵之戰〉2026-11-04「3:01 有跳拍」：
蓋句子時在「沒」跟「電」中間留了 0.33 秒空洞，對齊分數、聽寫都沒抓到）。
列出現在這首人聲在「句子裡」與「相鄰兩句之間」的無聲段，和原版人聲比對：原版這裡也沒聲音的是換氣，原版有聲、現在沒有的就是接壞了（⚠）。
改寫自上游 pipeline/template_battle/gap_check.py（上游 e634cce）。與上游不同：現在的人聲＝songs 階段分好的那份（work/song/align_<A|B>.json 的 vocals），
原版要自己指定（例如 splice_resing.py plan.json 的 base），分人聲用 make_battle.sep_stems（放 work/song/sep_orig/）。

用法（Voice venv，片子資料夾；接完先重跑 make_battle.py songs）："%PY_VOICE%" gap_check.py <A|B> <原版歌檔> [最短秒數=0.18]"""
import json
import sys
from pathlib import Path

import librosa
import numpy as np

import make_battle as mb

sys.stdout.reconfigure(encoding="utf-8")
if len(sys.argv) < 3:
    sys.exit(__doc__)
who, orig_song = sys.argv[1], Path(sys.argv[2]).resolve()
MIN = float(sys.argv[3]) if len(sys.argv) > 3 else 0.18
SR, HOP = 22050, 220
AL = json.loads((mb.OUT / "song" / f"align_{who}.json").read_text(encoding="utf-8"))
FINAL = Path(AL["vocals"])
ORIG, _ = mb.sep_stems(orig_song, mb.OUT / "song" / "sep_orig")


def voiced(p):
    y = librosa.load(str(p), sr=SR, mono=True)[0]
    db = 20 * np.log10(librosa.feature.rms(y=y, frame_length=HOP * 2, hop_length=HOP)[0] + 1e-6)
    return db > max(db.max() - 42, -48)


fin, org = voiced(FINAL), voiced(ORIG)
t0, t1 = AL["rows"][0]["start"], AL.get("last_word_end", AL["rows"][-1]["end"])
fr = lambda t: int(t * SR / HOP)
bad = []
i = fr(t0)
while i < min(fr(t1), len(fin)):
    if fin[i]:
        i += 1
        continue
    j = i
    while j < len(fin) and not fin[j]:
        j += 1
    sec = (j - i) * HOP / SR
    if sec >= MIN:
        bad.append((i * HOP / SR, sec, float(org[i:min(j, len(org))].mean()) if i < len(org) else 0.0))
    i = j
for t, sec, o in bad:
    print(f"{'⚠' if o > 0.5 else ' '} 歌曲 {t:7.2f}  無聲 {sec:.2f} 秒  原版此處有聲比例 {o:.0%}")
print(f"{FINAL.name}：{len(bad)} 段；⚠ {sum(o > 0.5 for *_, o in bad)} 段（原版有聲、現在沒有，一定要回頭修）")
