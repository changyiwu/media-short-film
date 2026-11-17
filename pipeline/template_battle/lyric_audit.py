"""全曲逐句聽寫稽核：對齊分數只代表時間對得上，不代表字唱對（上游〈向日葵之戰〉2026-11-04：「吵到你」唱成「好當你」，對齊分數還有 0.85）。
每句人聲、混音各聽寫一次（不給提示），用拼音比（同音字不算錯），列出兩邊都對不上的字。
改寫自上游 pipeline/template_battle/lyric_audit.py（上游 e634cce）。與上游不同：聽寫走 tools/stt.py 的 load_song_asr()（Qwen3-ASR，
同 songs 階段；上游用 faster-whisper），檔案在 work/（上游 out/）。

用法（Voice venv，片子資料夾，先跑過 make_battle.py songs）："%PY_VOICE%" lyric_audit.py [A B]
輸出 work/song/lyric_audit_<A|B>.md。「兩邊都沒聽到的字」逐一單獨聽，同一個詞在另一首也要查。"""
import json
import re
import sys
from pathlib import Path

import numpy as np

NOTCH = re.compile(r"[^一-鿿0-9]")


def miss(want, got):
    """逐字拼音做最長共同子序列：回傳 want 裡沒聽到的字（同音字算對）。"""
    from pypinyin import lazy_pinyin
    a, b = lazy_pinyin(want), lazy_pinyin(got)
    d = np.zeros((len(a) + 1, len(b) + 1), int)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            d[i + 1, j + 1] = d[i, j] + 1 if x == y else max(d[i, j + 1], d[i + 1, j])
    i, j = len(a), len(b); out = []
    while i and j:
        if a[i - 1] == b[j - 1]:
            i -= 1; j -= 1
        elif d[i - 1, j] >= d[i, j - 1]:
            i -= 1; out.append(want[i])
        else:
            j -= 1
    out += list(want[:i])[::-1]
    return out[::-1]


def load_hear(here):
    """回傳 hear(audio_16k) → 只留中文與數字的繁體聽寫。"""
    import opencc
    cfg = json.loads((here / "battle.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str((here / cfg.get("repo_dir", "../../..") / "tools").resolve()))
    import stt
    cc = opencc.OpenCC("s2twp"); h = stt.load_song_asr()
    return lambda x: NOTCH.sub("", cc.convert(h(np.ascontiguousarray(x, dtype=np.float32), 16000)))


def main():
    import librosa
    import opencc
    sys.stdout.reconfigure(encoding="utf-8")
    here = Path(__file__).resolve().parent
    cc = opencc.OpenCC("s2twp"); hear = load_hear(here)
    for who in sys.argv[1:] or ["A", "B"]:
        d = here / "work" / "song"
        al = json.loads((d / f"align_{who}.json").read_text(encoding="utf-8"))
        mix, _ = librosa.load(al["song"], sr=16000, mono=True)
        voc, _ = librosa.load(al["vocals"], sr=16000, mono=True)
        out = [f"# {who} 逐句聽寫稽核", "", "| 句 | 秒 | 歌詞 | 人聲聽寫 | 混音聽寫 | 兩邊都沒聽到的字 |", "|:--|:--|:--|:--|:--|:--|"]
        bad = 0
        for i, r in enumerate(al["rows"]):
            want = NOTCH.sub("", cc.convert(r["text"]))
            t0, t1 = max(0, r["start"] - 0.25), r["end"] + 0.3
            hv, hm = hear(voc[int(t0 * 16000):int(t1 * 16000)]), hear(mix[int(t0 * 16000):int(t1 * 16000)])
            mm = miss(want, hm); both = [c for c in miss(want, hv) if c in mm]
            bad += bool(both)
            out.append(f"| {i} | {r['start']:.1f} | {want} | {hv} | {hm} | {'**' + ''.join(both) + '**' if both else ''} |")
            print(i, round(r["start"], 1), want, "|", hv, "|", hm, "|", "".join(both), flush=True)
        (d / f"lyric_audit_{who}.md").write_text("\n".join(out) + f"\n\n有疑問 {bad} 句。\n", encoding="utf-8")
        print(f"→ {d / f'lyric_audit_{who}.md'}（有疑問 {bad} 句）", flush=True)


if __name__ == "__main__":
    main()
