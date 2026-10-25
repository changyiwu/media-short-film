"""開新片：把 pipeline/template_local/ 複製成 films/<類型>/<片名>/。

用法：python tools/new_film.py <類型> <片名>     例：python tools/new_film.py 數學家故事 埃拉托賽尼的篩子

- 類型是影片類型的資料夾（例：數學家故事、換角重製、原創短劇、測試），各類型專屬的規則寫在 films/<類型>/AGENTS.md。
- 只複製 film.json、make_film.py、review.py（跳過 output/、__pycache__、README.md；說明請看範本的 README.md）。
- film.json 的 title 換成片名，repo_dir 改成 "../../.."（片子在 repo 下三層）。
- 另外建空的 需求確認.md、劇本.md、製作紀錄.md（需求確認表的欄位見 .agents/skills/short-film/references/interview.md）。
- films/AGENTS.md 不存在時（新電腦、新頻道），從 templates/AGENTS_TEMPLATE.md 建一份，並加 CLAUDE.md 橋接。
- films/<類型>/ 是新的時，建 films/<類型>/AGENTS.md（類型規則的空白範本）＋CLAUDE.md 橋接，並列出既有類型方便核對有沒有打錯字。
- films/<類型>/<片名>/ 已存在就停下來，不覆蓋。
"""
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "pipeline" / "template_local"
FILMS = REPO / "films"
COPY = ["film.json", "make_film.py", "review.py"]
REQ_TEMPLATE = """# {name} 需求確認（{today}）

## 創作簡報

## 人物

| 角色 | 識別特徵 | 參考來源 | 備註（單人鏡／必須同框） |
|---|---|---|---|

## 場景

## 台詞與停頓

| 段落 | 說話者 | 台詞 | 預估秒數 | 停頓位置 |
|---|---|---|---|---|

## 風格

## 聲音

## 禁則

## 假設（未經使用者確認者，逐條列出）
"""
KIND_TEMPLATE = """# {kind}：類型規則

> 本類型的片放在 `films/{kind}/<片名>/`。這裡只放**這個類型**的規則；所有片共用的規則在上一層 `../AGENTS.md`，兩份都要讀。
> Claude Code 讀本資料夾的檔案時，會透過同資料夾的 `CLAUDE.md`（`@AGENTS.md`）自動載入本檔。

## 這類片是什麼

<一兩句話：內容、觀眾、用途>

## 規則

- （還沒有本類型專屬的規則；退件理由屬於這類片的，整理成一條寫在這裡。）
"""
BAD_CHARS = '<>:"/\\|?*'
REPO_DIR = "../../.."


def check_name(label, v):
    if not v or any(c in v for c in BAD_CHARS) or v in (".", "..") or v == "角色":
        sys.exit(f"{label}不能用：{v!r}（不能空白、不能含 {BAD_CHARS}，也不能叫「角色」）")


def main():
    if len(sys.argv) != 3:
        sys.exit("用法：python tools/new_film.py <類型> <片名>（例：python tools/new_film.py 數學家故事 埃拉托賽尼的篩子）")
    kind, name = sys.argv[1].strip(), sys.argv[2].strip()
    check_name("類型", kind)
    check_name("片名", name)

    kind_dir = FILMS / kind
    dst = kind_dir / name
    if dst.exists():
        sys.exit(f"已經有這支片了，不覆蓋：{dst}")

    created = []
    if not (FILMS / "AGENTS.md").exists():
        FILMS.mkdir(exist_ok=True)
        shutil.copyfile(REPO / "templates" / "AGENTS_TEMPLATE.md", FILMS / "AGENTS.md")
        (FILMS / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
        created += ["films/AGENTS.md（從 templates/AGENTS_TEMPLATE.md 建立，請改成自己的頻道規則）", "films/CLAUDE.md"]

    if not (kind_dir / "AGENTS.md").exists():
        others = sorted(p.name for p in FILMS.iterdir() if p.is_dir() and p.name != "角色" and p.name != kind)
        print(f"新類型「{kind}」；既有類型：{'、'.join(others) or '（無）'}。打錯字的話刪掉 films/{kind}/ 重跑。")
        kind_dir.mkdir(parents=True, exist_ok=True)
        (kind_dir / "AGENTS.md").write_text(KIND_TEMPLATE.format(kind=kind), encoding="utf-8")
        (kind_dir / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
        created += [f"films/{kind}/AGENTS.md（類型規則，請寫上這類片的規則）", f"films/{kind}/CLAUDE.md"]

    dst.mkdir(parents=True)
    for f in COPY:
        shutil.copy2(TEMPLATE / f, dst / f)

    # 只換 title、repo_dir 那兩行，保留 film.json 原本的排版
    fj = dst / "film.json"
    text = fj.read_text(encoding="utf-8")
    for key, val in (("title", name), ("repo_dir", REPO_DIR)):
        text, n = re.subn(rf'^(\s*"{key}":\s*)".*?"', lambda m: m.group(1) + json.dumps(val, ensure_ascii=False),
                          text, count=1, flags=re.M)
        if n != 1:
            sys.exit(f"film.json 找不到 {key} 欄位，範本格式可能改了")
    cfg = json.loads(text)  # 確認仍是合法 JSON
    if not (dst / cfg["repo_dir"] / "tools" / "new_film.py").exists():
        sys.exit(f"film.json 的 repo_dir {cfg['repo_dir']!r} 指不到 repo 根目錄")
    fj.write_text(text, encoding="utf-8")

    today = date.today().isoformat()
    (dst / "需求確認.md").write_text(REQ_TEMPLATE.format(name=name, today=today), encoding="utf-8")
    (dst / "劇本.md").write_text(f"# {name}：劇本\n\n> 用 short-film 技能寫；定稿後把鏡表填進 film.json 的 shots。\n", encoding="utf-8")
    (dst / "製作紀錄.md").write_text(f"# {name}：製作紀錄\n\n## {today} 開新片\n\n- 從 pipeline/template_local/ 建立。\n", encoding="utf-8")

    for c in created:
        print("建立", c)
    print(f"建立 films/{kind}/{name}/：{'、'.join(COPY)}、需求確認.md、劇本.md、製作紀錄.md")
    print("film.json 目前還是範例片〈被狗吃掉的作業〉的角色、場景與鏡表，要換成自己的。")
    print("下一步：需求訪談（需求確認.md）→ 寫劇本與鏡表 → 填 film.json → 跑 make_film.py（流程見 short-film 技能）")


if __name__ == "__main__":
    main()
