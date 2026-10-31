"""旁白併塊切回各鏡（Voice venv）：make_film.py 的 voices 階段自動呼叫（film.json 的 vo_chunk，用 Ming 時預設開）。
連續幾鏡的旁白併成一塊念（語氣才連貫），再切回每鏡一個檔：用聽寫逐字時間估切點，吸附到附近最安靜處，切好的每段再聽寫一次驗證句頭句尾。
做法改寫自上游 tools/make_narration.py（2026-10-11），上游只算字幕時間、不切檔；2026-10-31〈測試_旁白併塊〉10 句實測切點都落在靜音。
用法："%PY_VOICE%" <repo>\\tools\\vo_split.py blocks.json
blocks.json：{"dir": "voice/bv", "blocks": [{"name": "K1", "lines": [{"name": "line0", "text": "這句實際念的字"}, ...]}]}
讀 <dir>/<塊>.wav，寫 <dir>/<句>.wav 與 <dir>/vo_split.json（每句的 heard、dur、head_ok、tail_ok）。每次重切，人工改挑塊之後重跑 voices 就會更新。"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stt import load_asr  # noqa: E402
from tts_lexicon import load_lexicon, speakable  # noqa: E402
from voice_pick import int_zh  # noqa: E402
from pypinyin import Style, lazy_pinyin  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LEAD, TAIL, FADE = 0.05, 0.12, 0.015   # 每段頭尾留白與淡入淡出（秒）
BACK, AHEAD = 0.15, 0.6                # 切點從「估計的句尾」往前、往後找最安靜處的範圍（秒）
cn = lambda t: re.sub(r"[^\w]", "", t)
py = lambda s: lazy_pinyin(re.sub(r"[^一-鿿]", "", re.sub(r"\d+", lambda m: int_zh(int(m.group())), s)), style=Style.TONE3)


def cut_points(x, sr, words, lens):
    """words：[(字數, 結束秒)]；lens：每句字數。回傳句與句之間的切點（樣本）。"""
    hop = int(0.01 * sr); e = np.sqrt(np.convolve(x ** 2, np.ones(hop) / hop, "same"))
    heard, want, acc, cuts = sum(c for c, _ in words) or 1, sum(lens), 0, []
    for n in lens[:-1]:
        acc += n; target = acc / want * heard; cum = 0; t = 0.0
        for c, end in words:
            cum += c; t = end
            if cum >= target - 1e-6:
                break
        a, z = max(0, int((t - BACK) * sr)), min(len(x), int((t + AHEAD) * sr))
        cuts.append(a + int(np.argmin(e[a:z])))
    return cuts


def clip(seg, sr):
    nz = np.where(np.abs(seg) > 0.002)[0]
    if not len(nz):
        return seg
    seg = seg[max(0, nz[0] - int(LEAD * sr)): min(len(seg), nz[-1] + int(TAIL * sr))].copy()
    n = int(FADE * sr); seg[:n] *= np.linspace(0, 1, n); seg[-n:] *= np.linspace(1, 0, n)
    return seg


def main():
    spec_path = Path(sys.argv[1]).resolve(); spec = json.loads(spec_path.read_text(encoding="utf-8-sig")); d = spec_path.parent / spec["dir"]
    asr = load_asr("large-v3"); lex = load_lexicon(spec_path.parent); out = {}
    ask = lambda f, **k: asr.transcribe(str(f), language="zh", beam_size=5, initial_prompt="以下是繁體中文的普通話。", condition_on_previous_text=False, **k)[0]
    for b in spec["blocks"]:
        f = d / f"{b['name']}.wav"; x, sr = sf.read(f, dtype="float32"); x = x if x.ndim == 1 else x.mean(1)
        words = [(len(cn(w.word)), float(w.end)) for s in ask(f, word_timestamps=True) for w in s.words]
        said = [speakable(l["text"], lex) for l in b["lines"]]
        pts = [0] + cut_points(x, sr, words, [len(cn(t)) for t in said]) + [len(x)]
        for j, l in enumerate(b["lines"]):
            o = d / f"{l['name']}.wav"; seg = clip(x[pts[j]:pts[j + 1]], sr); sf.write(o, seg, sr, subtype="PCM_16")
            heard = "".join(s.text for s in ask(o)); want, got = py(said[j]), py(heard)
            r = dict(block=b["name"], heard=heard, dur=round(len(seg) / sr, 2), head_ok=want[:2] == got[:2], tail_ok=want[-2:] == got[-2:])
            out[l["name"]] = r
            print(f"[split] {b['name']} {l['name']} {r['dur']}s {heard}" + ("" if r["head_ok"] and r["tail_ok"] else "  ⚠ 句頭或句尾跟原文不同，要人聽（數字、同音字可能只是聽寫差異）"), flush=True)
    (d / "vo_split.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
