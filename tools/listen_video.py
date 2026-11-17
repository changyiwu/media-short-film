"""饒舌對決試聽影片：讓使用者「看著歌詞聽歌」，挑版、找唱錯的句子用。

改寫自 media-math-rap 的 scripts/listen_video.py（同作者；本 repo 依 MIT 授權，見 NOTICE.md），
資料來源改成本專案 make_battle.py songs 階段的 work/song/align_<A|B>.json。

畫面是黑底：
  - 中間大字：現在唱的這句，唱到哪個字就由白轉色（卡拉 OK 掃色，用 align 的逐字時間 words；A 黃、B 青）
  - 下方：該句逐句聽寫（rows[].asr）與分數（rows[].ok，低於 0.5 用紅字）；
    歌詞有、聽寫沒有的字標「缺「…」」也用紅字（短字漏唱常常只有這樣抓得到）
  - 上下淡字：前一句、後一句；左上角「A 第幾句」、右上角秒數，方便使用者說「A 第 7 句」「0:21」

用法：python tools/listen_video.py <片子資料夾> [A] [B]      不寫就兩首都做
輸出：<片子資料夾>/work/試聽/試聽_<A|B>.mp4（和 .ass）
要先跑過 make_battle.py songs。ffmpeg 的 subtitles 濾鏡吃不了中文路徑，所以在輸出資料夾裡跑、只給相對檔名。
"""
import difflib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

FONT = os.environ.get("SUB_FONT_NAME", "Microsoft JhengHei" if os.name == "nt" else "Noto Sans CJK TC")
LOW = 0.5  # 和 make_battle.py songs 的低分句門檻一致
COLOR = {"A": "&H0000E5FF", "B": "&H00FFE000"}  # ASS 是 BGR：A 黃、B 青
KEEP = re.compile(r"[一-鿿A-Za-z0-9]")


def ts(t):
    t = max(0.0, t)
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def char_times(row):
    """歌詞每個有字的字元對到 words 的開唱時間（英文詞拆成字母）；對不上就回傳 None（整句不掃色）"""
    text = row["text"]
    flat = [(ch, w["s"]) for w in row.get("words") or [] for ch in w["w"] if KEEP.match(ch)]
    idx = [i for i, ch in enumerate(text) if KEEP.match(ch)]
    if not flat or len(flat) != len(idx):
        return None
    ct, it = [None] * len(text), iter(flat)
    for i in idx:
        ct[i] = next(it)[1]
    for j in range(len(ct)):  # 空白、標點沿用前一個字的時間
        if ct[j] is None:
            ct[j] = ct[j - 1] if j else flat[0][1]
    return ct


def karaoke(row):
    text, s, e = row["text"], row["start"], row["end"]
    ct = char_times(row)
    if not ct:
        return text
    rel = [c - s for c in ct] + [e - s]
    parts, prev = [], 0.0
    for ch, c0, c1 in zip(text, rel, rel[1:]):
        if c0 > prev:
            parts.append(f"{{\\k{int(round((c0 - prev) * 100))}}}")
        parts.append(f"{{\\kf{max(1, int(round((c1 - c0) * 100)))}}}{ch}")
        prev = max(prev, c1)
    return "".join(parts)


def missing(text, heard):
    a, b = "".join(KEEP.findall(text)).upper(), "".join(KEEP.findall(heard or "")).upper()
    got = set()
    for x, _, n in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        got.update(range(x, x + n))
    return "".join(ch for i, ch in enumerate(a) if i not in got)


def head(k):
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cur,{FONT},88,{COLOR.get(k, COLOR['A'])},&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,4,0,5,60,60,0,1
Style: Dim,{FONT},54,&H00808080,&H00808080,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,5,60,60,0,1
Style: Num,{FONT},48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,7,60,60,40,1
Style: Heard,{FONT},44,&H00F0D060,&H00F0D060,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,5,60,60,0,1
Style: HeardLow,{FONT},44,&H006070FF,&H006070FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,0,5,60,60,0,1
Style: Clock,{FONT},40,&H00B0B0B0,&H00B0B0B0,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,9,60,60,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def duration(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def make(film, k):
    af = film / "work" / "song" / f"align_{k}.json"
    if not af.exists():
        raise SystemExit(f"錯誤：沒有 {af}（先跑 make_battle.py songs）")
    info = json.loads(af.read_text(encoding="utf-8"))
    rows = info["rows"]
    song = Path(info["song"])
    if not song.exists():
        song = film / "song" / f"{k}.mp3"
    dur = duration(song) or rows[-1]["end"] + 3
    ev, nosweep = [], 0
    for n, row in enumerate(rows):
        s = row["start"]
        e2 = max(row["end"], rows[n + 1]["start"] if n + 1 < len(rows) else row["end"] + 2)
        span = f"{ts(s)},{ts(e2)}"
        if char_times(row) is None:
            nosweep += 1
        ev.append(f"Dialogue: 1,{span},Cur,,0,0,0,,{{\\pos(960,540)}}{karaoke(row)}")
        ev.append(f"Dialogue: 0,{span},Num,,0,0,0,,{k} 第 {n + 1} 句")
        heard, sc = (row.get("asr") or "").strip(), row.get("ok")
        ms = missing(row["text"], heard)
        st = "HeardLow" if (sc is not None and sc < LOW) or ms else "Heard"
        lack = f"　缺「{ms}」" if ms else ""
        ev.append(f"Dialogue: 0,{span},{st},,0,0,0,,{{\\pos(960,650)}}聽寫：{heard or '（沒聽到）'}　（{sc}）{lack}")
        if n > 0:
            ev.append(f"Dialogue: 0,{span},Dim,,0,0,0,,{{\\pos(960,380)}}{rows[n - 1]['text']}")
        if n + 1 < len(rows):
            ev.append(f"Dialogue: 0,{span},Dim,,0,0,0,,{{\\pos(960,780)}}{rows[n + 1]['text']}")
    if rows[0]["start"] > 0.3:
        span = f"{ts(0)},{ts(rows[0]['start'])}"
        ev.append(f"Dialogue: 0,{span},Dim,,0,0,0,,{{\\pos(960,540)}}（前奏）")
        ev.append(f"Dialogue: 0,{span},Dim,,0,0,0,,{{\\pos(960,780)}}{rows[0]['text']}")
    for sec in range(int(dur) + 1):
        ev.append(f"Dialogue: 0,{ts(sec)},{ts(sec + 1)},Clock,,0,0,0,,{sec // 60}:{sec % 60:02d}")
    if nosweep:
        print(f"  ⚠ {k} 有 {nosweep} 句逐字時間和歌詞字數對不上，那幾句不掃色", flush=True)

    out_dir = film / "work" / "試聽"
    out_dir.mkdir(parents=True, exist_ok=True)
    ass = out_dir / f"試聽_{k}.ass"
    ass.write_text(head(k) + "\n".join(ev) + "\n", encoding="utf-8-sig")
    out = f"試聽_{k}.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0x101418:s=1920x1080:r=30:d={dur:.2f}",
                    "-i", str(song.resolve()), "-vf", f"subtitles={ass.name}", "-map", "0:v", "-map", "1:a",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "160k",
                    "-shortest", out], cwd=out_dir, check=True)
    return out_dir / out


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    film = Path(sys.argv[1]).resolve()
    for k in (sys.argv[2:] or ["A", "B"]):
        print(f"  試聽影片：{make(film, k.upper())}", flush=True)


if __name__ == "__main__":
    main()
