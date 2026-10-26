"""讀音替換表（tts-lexicon.md）：送進 TTS 前把念錯的詞換成念得對的寫法，字幕照原文。2026-10-20 從 media-video-specs 移植。
表在 repo 根目錄的 tts-lexicon.md，格式與規則寫在表的開頭。這份表有四份、內容完全相同（media-video-specs、本 repo、
media-voice-clone、agent-speak/speak/；四個 repo 都公開，各自單獨下載就能用），放在同一層時合併讀取。

找表的順序（近的覆蓋遠的，同一個原文以近的為準）：
  同層其他三個 repo 的 tts-lexicon.md（有就合併）
  → 本 repo 的表：TTS_LEXICON（有設就用它）或 repo 根目錄的 tts-lexicon.md
  → 從起點資料夾（例如 output/<類型>/<片名>/work/）往上每一層的 tts-lexicon.md（片子資料夾放一份只對該片生效）。
本專案套用的地方：voxcpm_batch.py（念台詞前）、gen_voice.py（edge-tts 答案卷、單句生成）、voice_pick.py（聽寫比對的標準）、
recast.py voice。每段文字只套一次；film.json 的 "tts" 照樣可用，表會再套在它上面。

試表（Voice venv 或任何 Python）：python tools/tts_lexicon.py [起點資料夾] "要念的句子"
四份是否一致：python tools/tts_lexicon.py --check　　合併各份的條目寫回四份：python tools/tts_lexicon.py --sync
（只在四個 repo 放在同一層時有用；--sync 遇到同一個原文改寫不同、或表頭說明不一樣時不寫入，先手動統一） """
import os
import re
import sys
from pathlib import Path

NAME = "tts-lexicon.md"
REPO = Path(__file__).resolve().parents[1]
# 四份同內容的表（repo 名稱, 表在 repo 裡的位置）；本 repo 以外的三份放在同一層時一起讀
COPIES = [("media-video-specs", NAME), ("media-short-film", NAME),
          ("media-voice-clone", NAME), ("agent-speak", f"speak/{NAME}")]
SIBLINGS = [REPO.parent / r / rel for r, rel in COPIES if r != REPO.name]
HEAD = ("原文", "改寫")


def master():
    p = os.environ.get("TTS_LEXICON")
    return Path(p).expanduser() if p else REPO / NAME


def lexicon_files(start=None):
    """回傳要讀的表，遠的在前、近的在後"""
    files = [*SIBLINGS, master()]
    if start:
        s = Path(start).resolve()
        s = s.parent if s.is_file() else s
        files += reversed([d / NAME for d in (s, *s.parents)])
    seen, out = set(), []
    for f in files:
        if f.is_file() and f.resolve() not in seen:
            seen.add(f.resolve()); out.append(f)
    return out


def cells(line):
    s = line.strip()[1:]                                 # 去掉開頭的 |
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    out = []
    for c in re.split(r"(?<!\\)\|", s):
        c = c.strip().replace("\\|", "|")
        if len(c) >= 2 and c[0] == c[-1] == "`":         # `GPT four` 這種用反引號標出空白的寫法
            c = c[1:-1]
        out.append(c)
    return out


def parse(path):
    """只讀表頭是「原文｜改寫」的 Markdown 表格；其他段落、表格都當說明"""
    table, inside = {}, False
    for n, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.lstrip().startswith("|"):
            inside = False
            continue
        c = cells(line)
        if tuple(c[:2]) == HEAD:
            inside = True
            continue
        if not inside or all(re.fullmatch(r":?-+:?", x) for x in c if x):
            continue
        if len(c) < 2 or not c[0] or not c[1]:
            raise SystemExit(f"{path}:{n} 格式不對（| 原文 | 改寫 | 說明 |，原文、改寫都不能空）：{line}")
        table[c[0]] = c[1]
    return table


def load_lexicon(start=None, quiet=False):
    table = {}
    files = lexicon_files(start)
    for f in files:
        table.update(parse(f))
    if not quiet:
        print(f"[lexicon] 讀音替換表 {len(table)} 條：" + ("、".join(str(f) for f in files) if files else f"找不到 {NAME}，不做替換"), flush=True)
    return table


def speakable(text, table):
    """長的原文先比對，一次掃完：換過的結果不會再被其他條目換"""
    if not table:
        return text
    pat = re.compile("|".join(re.escape(k) for k in sorted(table, key=len, reverse=True)))
    return pat.sub(lambda m: table[m.group(0)], text)


def split(path):
    """拆成（表格前的說明, [(原文, 改寫, 原始那一列)], 表格後的內容），給 --check／--sync 用"""
    lines = Path(path).read_bytes().decode("utf-8-sig").replace("\r\n", "\n").split("\n")
    start = next((i for i, l in enumerate(lines) if l.lstrip().startswith("|") and tuple(cells(l)[:2]) == HEAD), None)
    if start is None:
        raise SystemExit(f"{path} 找不到「| 原文 | 改寫 |」表格")
    i = start + 2                                        # 跳過表頭與分隔線
    rows = []
    while i < len(lines) and lines[i].lstrip().startswith("|"):
        c = cells(lines[i]); rows.append((c[0], c[1], lines[i])); i += 1
    return "\n".join(lines[:start + 2]), rows, "\n".join(lines[i:])


def copies():
    return [(r, REPO.parent / r / rel) for r, rel in COPIES]


def sync(write):
    found = [(r, f) for r, f in copies() if f.is_file()]
    for r, f in copies():
        if not f.is_file():
            print(f"缺：{r}（{f}）")
    parts = {r: split(f) for r, f in found}
    union, owner, conflicts = {}, {}, []
    for r, (_, rows, _) in parts.items():
        for k, v, raw in rows:
            if k not in union:
                union[k], owner[k] = (v, raw), r
            elif union[k][0] != v:
                conflicts.append(f"「{k}」：{owner[k]} 寫「{union[k][0]}」，{r} 寫「{v}」")
    heads = {(h, tail) for h, _, tail in parts.values()}
    missing = {r: [k for k in union if k not in {x[0] for x in rows}] for r, (_, rows, _) in parts.items()}
    same = len({f.read_bytes() for _, f in found}) == 1 and len(found) == len(COPIES)
    for r, ks in missing.items():
        if ks:
            print(f"{r} 缺 {len(ks)} 條：{'、'.join(ks)}")
    for c in conflicts:
        print("改寫不同：" + c)
    if len(heads) > 1:
        groups = ["、".join(r for r, (h, _, t) in parts.items() if (h, t) == x) for x in heads]
        print(f"表格以外的說明有 {len(heads)} 種版本：" + "／".join(groups) + "，先手動統一")
    if same:
        print(f"四份完全相同（{len(union)} 條）")
        return 0
    if not write:
        print("不一致：python tools/tts_lexicon.py --sync 合併寫回" if not conflicts and len(heads) == 1 else "不一致")
        return 1
    if conflicts or len(heads) > 1:
        print("沒有寫入：先解決上面的衝突")
        return 1
    head, tail = next(iter(heads))
    body = head + "\n" + "".join(raw + "\n" for _, raw in union.values()) + tail
    # repo 在、只是缺表的也補上一份；repo 不在這台就略過
    targets = [(r, f) for r, f in copies() if f.is_file() or (REPO.parent / r).is_dir()]
    for r, f in targets:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(body.encode("utf-8"))
    print(f"已把 {len(union)} 條寫回 {len(targets)} 份：" + "、".join(r for r, _ in targets))
    return 0


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] in ("--check", "--sync"):
        sys.exit(sync(a[0] == "--sync"))
    start, text = (a[0], a[1]) if len(a) > 1 else (None, a[0])
    print(speakable(text, load_lexicon(start)))
