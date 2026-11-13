"""破音字檢查：台詞、旁白、歌詞裡「一個字有兩種以上念法」的字，逐字查教育部辭典，用前後文找出這裡該念哪個音。
改寫自上游 pipeline/template_battle/poly_check.py（上游 7e6bcbd，2026-11-07）：本分支改成通用工具，
讀 make_film.py 的 film.json、make_battle.py 的 battle.json 或純文字檔；送去念的文字照 make_film.py 的做法
（該句的 "tts"，再過讀音替換表 tts-lexicon.md）。上游的 DJ 錄音比對（--audio，要 dj_align.py）沒有移植。

用法（Voice venv）：
  "%PY_VOICE%" <repo>\\tools\\poly_check.py film.json            # 片子資料夾 → work/review/poly_check.md
  "%PY_VOICE%" <repo>\\tools\\poly_check.py battle.json          # 饒舌對決（歌詞＋DJ 口白）
  "%PY_VOICE%" <repo>\\tools\\poly_check.py 劇本.txt --out 資料夾  # 純文字：每行一句
  加 --all 連「的了著得地一不個」也列。

判讀：
  - 「照詞典」：詞典有剛好含這個字的 2–4 字詞，用詞條的音當答案；★ 表示跟 pypinyin 的大陸預設念法不同，
    TTS 多半照大陸預設念，要確認詞條的意思跟句子一樣（「一毛沒收」≠ 詞條「沒收＝充公 ㄇㄛˋ」）。
  - 「同音字對／⚠ 同音字的音跟詞典不同」：送去念的文字換了字（"tts" 或讀音替換表）時，檢查換的字音對不對。
  - 「台灣只有一個音、但和大陸預設不同」：簡編本只收一個音、pypinyin 卻猜成別的音（松柏的「柏」），TTS 多半照大陸音念，
    要改同音字（上游 a61f4bf）。
  - 「要人看上下文」：詞典沒有剛好的詞，要自己判斷，必要時查 https://dict.revised.moe.edu.tw/ 例句。工具只列出來，不替你決定。
  - 聽寫只驗字、驗不出聲調：表上判定要念對的關鍵字，成片仍要用耳朵聽。
查詢結果快取在報告旁的 moe_cache.json（重跑不再上網）。查詢只送詞語，不送其他資料。"""
import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tts_lexicon import load_lexicon, speakable  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
UA = {"User-Agent": "Mozilla/5.0 (poly-check script)"}
LIGHT = set("的了著得地一不個們嗎呢吧啊")          # 虛字、變調字：念法跟著句子走，預設不列（--all 才列）
CJK = re.compile(r"[一-鿿]")
SITES = {"concised": "https://dict.concised.moe.edu.tw/search.jsp",   # 簡編本：只收常用音，判斷「是不是破音字」用這本
         "revised": "https://dict.revised.moe.edu.tw/search.jsp"}     # 修訂本：詞條多，找前後文的詞用這本補
CACHE = None
_cache = None


def moe(word, site="revised"):
    """回傳 [(詞條, [每字注音…]), …]；查無資料回傳 []。"""
    global _cache
    if _cache is None:
        _cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    key = word if site == "revised" else f"{site}:{word}"
    if key in _cache:
        return _cache[key]
    import requests
    for k in range(3):
        try:
            r = requests.get(SITES[site], params=dict(md=1, word=word, qMd=0, qCol=1), headers=UA, timeout=30)
            break
        except Exception:
            time.sleep(2 + 3 * k)
    else:
        raise SystemExit(f"教育部辭典連不上（查「{word}」）")
    t = r.text
    res = []

    def syl(block):
        return [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<(?:code|phon)>(.*?)</(?:code|phon)>", block)]
    if "id=searchL" in t:
        for row in re.findall(r"<tr data-link=.*?</tr>", t, flags=re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)
            if len(tds) < 3:
                continue
            ent = re.sub(r"<sub>.*?</sub>", "", tds[1], flags=re.S)
            ent = re.sub(r"<[^>]+>", "", ent).strip()
            res.append([ent + ("（又音）" if "又音" in row else ""), syl(tds[2])])
    else:
        m = re.search(r"<h3>(.*?)</h3>", t, flags=re.S)
        if m and re.search(r"<(code|phon)>", m.group(1)):
            ent = re.sub(r"<[^>]+>", "", m.group(1).split(":")[0]).strip()
            res.append([ent, syl(m.group(1))])
    _cache[key] = res
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(_cache, ensure_ascii=False, indent=0), encoding="utf-8")
    time.sleep(0.25)
    return res


def char_readings(c, site="concised"):
    """這個字的常用念法（簡編本；簡編本沒收就用修訂本）。"""
    seen = []
    for ent, ph in moe(c, site):
        if ent.replace("（又音）", "") == c and ph and ph[0] not in seen:
            seen.append(ph[0] + ("（又音）" if "又音" in ent else ""))
    if not seen and site == "concised":
        return char_readings(c, "revised")
    return seen


def word_hits(phrase, i):
    """phrase 裡第 i 個字：找詞典裡剛好等於「含這個字的 2–4 字片段」的詞條 → [(詞, 這個字的注音)]，長的在前。"""
    hits = []
    for n in (4, 3, 2):
        for a in range(max(0, i - n + 1), min(i, len(phrase) - n) + 1):
            w = phrase[a:a + n]
            if not all(CJK.match(x) for x in w):
                continue
            for ent, ph in moe(w, "concised") + moe(w):
                if ent.replace("（又音）", "") == w and len(ph) == len(w):
                    hits.append((w + ("（又音）" if "又音" in ent else ""), ph[i - a]))
    out = []
    for h in hits:
        if h not in out:
            out.append(h)
    return out


def phrases(text):
    return [p for p in re.split(r"[^一-鿿]+", text) if p]


def collect(path, table):
    """[(來源, 字幕文字, 送去念的文字)]"""
    if path.suffix.lower() != ".json":
        lines = [x.strip() for x in path.read_text(encoding="utf-8").splitlines()]
        return [(f"第 {i} 行", x, speakable(x, table)) for i, x in enumerate(lines, 1) if CJK.search(x)]
    B = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    if "shots" in B:                                   # make_film.py：每鏡 line（角色台詞）、vo（旁白）
        for s in B["shots"]:
            for kind, who in (("line", None), ("vo", "旁白")):
                ln = s.get(kind)
                if ln and ln.get("text"):
                    rows.append((f"{s['id']} {who or ln.get('who', '')}", ln["text"], speakable(ln.get("tts", ln["text"]), table)))
    if "rappers" in B:                                 # make_battle.py：歌詞（show／sing）＋DJ 口白
        for r in B["rappers"].values():
            for sec in r["lyrics"]:
                for ln in sec["lines"]:
                    rows.append((f"{r['short']}歌詞", ln["show"].replace("　", " "), speakable(ln["sing"], table)))
        dj = B.get("dj") or {}
        for k, t in (dj.get("lines") or {}).items():
            rows.append((f"DJ {k}", t, speakable(dj.get("tts", {}).get(k, t), table)))
    if not rows:
        raise SystemExit(f"{path.name} 裡沒找到台詞（支援 film.json 的 shots、battle.json 的 rappers／dj，或純文字檔）")
    return rows


def align_sub(show, sing):
    """字幕與送去念的文字逐字對應（只比漢字；數字寫法不同的段落跳過，只對等長的替換段）。"""
    from difflib import SequenceMatcher
    a, b = "".join(CJK.findall(show)), "".join(CJK.findall(sing))
    m = {}
    for op, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal" or (op == "replace" and i2 - i1 == j2 - j1):
            m.update({i1 + k: b[j1 + k] for k in range(i2 - i1)})
    return m


def guess(text):
    """pypinyin 依詞組猜的念法（大陸預設，TTS 前端多半照這個念）→ 注音，給人對照。"""
    from pypinyin import pinyin, Style
    return [p[0] for p in pinyin("".join(CJK.findall(text)), style=Style.BOPOMOFO)]


def main():
    global CACHE
    ap = argparse.ArgumentParser(description="破音字檢查（教育部辭典）")
    ap.add_argument("src", help="film.json、battle.json 或純文字檔")
    ap.add_argument("--out", help="報告資料夾（預設：film.json 旁的 work/review；battle.json 旁的 out/review；純文字檔旁）")
    ap.add_argument("--all", action="store_true", help="連「的了著得地一不」也列")
    a = ap.parse_args()
    src = Path(a.src).resolve()
    if a.out:
        rdir = Path(a.out)
    elif src.suffix.lower() == ".json":
        rdir = src.parent / ("out" if src.name == "battle.json" and (src.parent / "out").is_dir() else "work") / "review"
    else:
        rdir = src.parent
    CACHE = rdir / "moe_cache.json"
    table = load_lexicon(src.parent)
    md = ["# 破音字檢查（教育部《國語辭典簡編本》＋《重編國語辭典修訂本》）", "",
          "| 來源 | 字 | 前後文 | 這個字的念法 | 詞典裡的詞 → 這裡的音 | pypinyin 猜 | 送去念的字 | 判斷 |", "|:--|:--|:--|:--|:--|:--|:--|:--|"]
    bad, ok_dict, ctxq, tw = [], [], [], []
    for name, show, sing in collect(src, table):
        sub = align_sub(show, sing)
        gs = guess(show)
        pos = 0
        for ph in phrases(show):
            for i, c in enumerate(ph):
                gi = pos + i
                if c in LIGHT and not a.all:
                    continue
                rd = char_readings(c)
                if len(rd) < 2:
                    # 台灣只有一個音、但大陸預設念別的（上游 a61f4bf：松柏的「柏」台灣ㄅㄛˊ，生成器照大陸念 bǎi）
                    g0 = gs[gi] if gi < len(gs) else ""
                    if len(rd) == 1 and g0 and rd[0].replace("˙", "") != g0.replace("˙", ""):
                        sc0 = sub.get(gi)
                        srd0 = [x.replace("（又音）", "") for x in char_readings(sc0)] if sc0 and sc0 != c else []
                        done = rd[0] in srd0
                        tw.append(f"| {name} | {c} | {ph[max(0, i - 3):i]}【{c}】{ph[i + 1:i + 4]} | {rd[0]} | {g0} | "
                                  f"{'寫成「' + sc0 + '」' if srd0 else ''} | {'同音字對' if done else '⚠ 要改同音字，TTS 多半照大陸音'} |")
                    continue
                hits = word_hits(ph, i)
                ans = sorted({h[1] for h in hits if "又音" not in h[0]})
                sc = sub.get(gi)
                gen = ""
                verdict = "要人看上下文" if len(ans) != 1 else "照詞典"
                if sc and sc != c:
                    srd = [x.replace("（又音）", "") for x in char_readings(sc)] or ["?"]
                    gen = f"寫成「{sc}」（{'／'.join(srd)}）"
                    if len(ans) == 1:
                        verdict = "同音字對" if ans[0] in srd else "⚠ 同音字的音跟詞典不同"
                g = gs[gi] if gi < len(gs) else ""
                if verdict == "照詞典" and g and ans[0].replace("˙", "") != g.replace("˙", ""):
                    verdict = "照詞典 ★和大陸預設不同，確認意思"
                ctx = ph[max(0, i - 3):i] + f"【{c}】" + ph[i + 1:i + 4]
                hs = "、".join(f"{w} {p}" for w, p in hits[:4]) or "—"
                line = f"| {name} | {c} | {ctx} | {'／'.join(rd)} | {hs} | {g} | {gen} | {verdict} |"
                md.append(line)
                (bad if verdict.startswith("⚠") else ok_dict if verdict.startswith(("照詞典", "同音字對")) else ctxq).append(line)
            pos += len(ph)
    H = [md[2], md[3]]
    star = [x for x in ok_dict if "★" in x]
    md += ["", f"共 {len(md) - 4} 個破音字。", "",
           f"## ⚠ 送去念的字跟詞典的音不同（{len(bad)}）", "", *H, *(bad or ["（無）"]), "",
           f"## ★ 詞典的音跟大陸預設不同（{len(star)}）— TTS 可能念錯，確認詞條意思後考慮加進 tts-lexicon.md", "", *H, *(star or ["（無）"]), "",
           f"## 詞典詞條定的音（{len(ok_dict)}）— 要確認詞條的意思跟句子一樣", "", *H, *(ok_dict or ["（無）"]), "",
           f"## 詞典沒有剛好的詞（{len(ctxq)}）— 看前後文自己定", "", *H, *(ctxq or ["（無）"])]
    tw_bad = [x for x in tw if "⚠" in x]
    TH = ["| 來源 | 字 | 前後文 | 台灣音 | pypinyin（大陸預設） | 送去念的字 | 判斷 |", "|:--|:--|:--|:--|:--|:--|:--|"]
    md += ["", f"## 台灣只有一個音、但和大陸預設不同（{len(tw)}）— 字幕照原字，送去念的字要寫同音字（加進 tts-lexicon.md 或該句 \"tts\"）",
           "", *TH, *(tw or ["（無）"])]
    rdir.mkdir(parents=True, exist_ok=True)
    rep = rdir / "poly_check.md"
    rep.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(bad + star + tw_bad) or "沒有要處理的破音字")
    print(f"⚠ {len(bad)}、★ {len(star)}、台灣單一音 ⚠ {len(tw_bad)}、要看上下文 {len(ctxq)} →", rep)


if __name__ == "__main__":
    main()
