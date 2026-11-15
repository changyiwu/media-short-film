# -*- coding: utf-8 -*-
"""讀音自審：盯「找不到同音字可換、只能事後抓」的字（Voice venv）。改寫自上游 tools/pron_guard.py（上游 121f435，2026-11-14）。

本分支只移植上游的第 ③ 項：
  - 上游 ① 檢查配音輸入有沒有換字：本分支所有配音工具都經 tts_lexicon.py 自動換字，不會漏，不移植。
  - 上游 ② 量規則字的音高：本分支 pron_check.py 已逐字量聲調（voice_pick、h3_line_harvest、vc_swap 都接了），不移植。
  - ③ 不帶提示詞逐句聽寫：提示詞會把念錯的字拉回正確字（上游「抓」念成「多」就這樣漏掉），
       這裡聽寫一律不帶 initial_prompt，逐音節比拼音（不比聲調，同音字不算錯）；
       規則字另外看聽寫的把握度，< 0.85 標出來（只有 faster-whisper 有逐字把握度，其他後端只比拼音）。

規則在 tools/pron_guard_rules.json（人聽出念錯、又沒有同音字可換的字，就加一條；有同音字可換的照舊加進 tts-lexicon.md）。

用法：
  "%PY_VOICE%" tools\\pron_guard.py <片子資料夾 或 work\\voice_picks.json 或 lines.json> [--ids 3,7] [--all] [-v]
    片子資料夾／voice_picks.json：讀 make_film.py 的 work/voice_picks.json（每句的 text 與 file）。
    lines.json：[{"id", "text", "file"}]（file 可以是相對 lines.json 的路徑）。
    --all：每一句都聽寫比對（預設只查有規則字的句子）。
回傳碼 1＝有標出來的。報告印在畫面，另存在輸入檔同資料夾的 pron_guard_report.txt。
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

T = Path(__file__).resolve().parent
sys.path.insert(0, str(T))
RULES = json.loads((T / "pron_guard_rules.json").read_text(encoding="utf-8"))["rules"]
PROB_MIN = 0.85
NUM = set("零一二三四五六七八九十百千萬兩")
SAY = {"＋": "加", "+": "加", "＝": "等於", "=": "等於", "²": "平方", "³": "立方", "×": "乘", "÷": "除以", "％": "趴", "%": "趴"}
SYM = re.compile("|".join(map(re.escape, SAY)))


def han(s):
    return re.sub(r"[^一-鿿]", "", s or "")


def hits(text):
    """[(規則, 要盯的字, 符合的那段)]；char 為「*」＝符合那段的最後一個字（例：英文 AI 後面接的第一個中文字）。"""
    out = []
    for r in RULES:
        for m in re.finditer(r["match"], text):
            c = m.group(0)[-1] if r["char"] == "*" else r["char"]
            if c in m.group(0):
                out.append((r, c, m.group(0)))
    return out


def load_lines(src):
    p = Path(src)
    if p.is_dir():
        p = next((q for q in (p / "work" / "voice_picks.json", p / "voice_picks.json") if q.exists()), None)
        if p is None:
            sys.exit(f"找不到 voice_picks.json：{src}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):                            # make_film.py 的 voice_picks.json
        lines = [dict(id=k, text=v["text"], file=v["file"], shot=v.get("shot", "")) for k, v in data.items()]
    else:
        lines = [dict(id=str(x["id"]), text=x.get("text") or x.get("sub"), file=x["file"], shot=x.get("shot", "")) for x in data]
    for ln in lines:
        f = Path(ln["file"])
        ln["file"] = f if f.is_absolute() else p.parent / f
    return p, lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--ids"); ap.add_argument("--all", action="store_true"); ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    path, lines = load_lines(a.src)
    if a.ids:
        want = set(a.ids.split(","))
        lines = [ln for ln in lines if ln["id"] in want]
    todo = [(ln, hits(ln["text"])) for ln in lines]
    todo = [(ln, H) for ln, H in todo if H or a.all]
    rep, nflag = [], 0
    if not todo:
        rep.append("沒有句子含規則字（要每句都查加 --all）")
    else:
        import opencc
        from pypinyin import lazy_pinyin
        from stt import load_asr
        asr = load_asr("large-v3")
        s2t = opencc.OpenCC("s2t")                        # 只轉字；s2twp 會連詞一起換（局部→區域性）
        if not getattr(asr, "backend", "") == "faster":
            rep.append(f"（聽寫後端 {getattr(asr, 'backend', '?')} 沒有逐字把握度，只比拼音）")
        for ln, H in todo:
            wav, text = Path(ln["file"]), ln["text"]
            tag = f"{ln['shot']} line{ln['id']}".strip()
            if not wav.exists():
                rep.append(f"{tag}　找不到聲音檔 {wav}"); nflag += 1; continue
            segs, _ = asr.transcribe(str(wav), language="zh", beam_size=5, word_timestamps=True, condition_on_previous_text=False)
            segs = list(segs)
            words = [w for s in segs for w in (getattr(s, "words", None) or [])]
            got = han(s2t.convert("".join(s.text for s in segs))).replace("着", "著")   # s2t 不轉「着」，拼音會被當成不同字
            exp = han(SYM.sub(lambda m: SAY[m.group(0)], text))
            latin = bool(re.search(r"[A-Za-z0-9]", text))   # 英文字母、阿拉伯數字念出來的音不在 exp 裡：只多出來的字不算
            msgs, notes = [], []
            sm = difflib.SequenceMatcher(a=lazy_pinyin(exp), b=lazy_pinyin(got), autojunk=False)
            for op, i1, i2, j1, j2 in sm.get_opcodes():
                if op == "equal":
                    continue
                es, gs = exp[i1:i2], got[j1:j2]
                if es and set(es) <= NUM and not gs:      # 聽寫寫成阿拉伯數字
                    continue
                if not es and latin:
                    continue
                msgs.append(f"聽寫：「{exp[max(0, i1 - 3):i2 + 3]}」裡的「{es}」聽成「{gs}」")
            for r, c, word in H:
                ps = [w.probability for w in words if getattr(w, "probability", None) is not None and c in s2t.convert(w.word)]
                if words and getattr(words[0], "probability", None) is not None:
                    if not ps:
                        msgs.append(f"「{word}」的「{c}」聽寫沒出現")
                    elif min(ps) < PROB_MIN:
                        msgs.append(f"「{word}」的「{c}」聽寫把握度 {min(ps):.2f} < {PROB_MIN}（{r['src'][:40]}…）")
                    elif a.verbose:
                        notes.append(f"「{c}」把握度 {min(ps):.2f}")
            if msgs:
                nflag += 1
                rep.append(f"{tag}　{text}")
                rep += ["    " + m for m in msgs + notes]
            elif a.verbose:
                rep.append(f"（過）{tag}　{text}" + (("；" + "；".join(notes)) if notes else ""))
    rep.append(f"\n共 {nflag} 句要人聽" if nflag else "\n讀音自審：全部通過")
    txt = "\n".join(rep)
    print(txt)
    path.with_name("pron_guard_report.txt").write_text(txt, encoding="utf-8")
    sys.exit(1 if nflag else 0)


if __name__ == "__main__":
    main()
