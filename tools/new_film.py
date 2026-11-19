"""開新片：照 kinds/kinds.json 把該類型的範本複製成 output/<類型>/<片名>/。

用法：python tools/new_film.py <類型> <片名>     例：python tools/new_film.py 數學故事 埃拉托賽尼的篩子
      python tools/new_film.py --list            列出可用的類型

- 類型要先在 kinds/kinds.json 登記（範本、設定檔、要複製的檔），規則寫在 kinds/<類型>/rules.md；沒登記的類型會停下並說明怎麼加。
- 複製 kinds.json 的 copy 清單（`*.py`＝範本資料夾裡全部 Python 檔），設定檔的 title 換成片名；film.json 另把 repo_dir 改成 "../../.."。
- 另外建空的 需求確認.md、<劇本|歌詞>.md（kinds.json 的 script）、製作紀錄.md。
- output/AGENTS.md 不存在時（新電腦、新頻道），從 templates/AGENTS_TEMPLATE.md 建一份，並加 CLAUDE.md 橋接。
- output/<類型>/ 是新的時，建 AGENTS.md（指向 kinds/<類型>/rules.md）與 CLAUDE.md（直接載入 rules.md）。
- output/<類型>/<片名>/ 已存在就停下來，不覆蓋。
"""
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KINDS = REPO / "kinds"
FILMS = REPO / "output"
REPO_DIR = "../../.."
BAD_CHARS = '<>:"/\\|?*'
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
KIND_AGENTS = """# {kind}：類型規則（指標）

> 這個類型的規則在 repo 的 `kinds/{kind}/rules.md`（進 git、所有人共用），做片前讀那份；通用做片規則在 `docs/rules/`。
> Claude Code 讀本資料夾的檔案時，會透過同資料夾的 `CLAUDE.md` 自動載入那份 rules.md。
> 本檔只放這個頻道對這類影片額外的、不公開的規則（通常沒有）；做法上的經驗一律寫回 `kinds/{kind}/rules.md` 或 `docs/rules/`。
"""


def load_kinds():
    return {k: v for k, v in json.loads((KINDS / "kinds.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}


def check_name(label, v):
    if not v or any(c in v for c in BAD_CHARS) or v in (".", "..", "角色", "道具"):
        sys.exit(f"{label}不能用：{v!r}（不能空白、不能含 {BAD_CHARS}，也不能叫「角色」「道具」）")


def set_field(text, key, val, fname):
    """只換 "key": "..." 那一行，保留設定檔原本的排版。"""
    text, n = re.subn(rf'^(\s*"{key}":\s*)".*?"', lambda m: m.group(1) + json.dumps(val, ensure_ascii=False), text, count=1, flags=re.M)
    if n != 1:
        sys.exit(f"{fname} 找不到 {key} 欄位，範本格式可能改了")
    return text


def main():
    kinds = load_kinds()
    if len(sys.argv) == 2 and sys.argv[1] == "--list":
        for k, v in kinds.items():
            print(f"{k}\t{v['template']}\t{v['desc']}")
        return
    if len(sys.argv) != 3:
        sys.exit("用法：python tools/new_film.py <類型> <片名>（例：python tools/new_film.py 數學故事 埃拉托賽尼的篩子）；--list 列出類型")
    kind, name = sys.argv[1].strip(), sys.argv[2].strip()
    check_name("類型", kind)
    check_name("片名", name)
    if kind not in kinds:
        sys.exit(f"沒有登記的類型「{kind}」。可用：{'、'.join(kinds)}。\n"
                 f"要加新類型：建 kinds/{kind}/rules.md，並在 kinds/kinds.json 加一行（格式見 kinds/README.md）。")
    spec = kinds[kind]
    if not (KINDS / kind / "rules.md").exists():
        sys.exit(f"kinds/{kind}/rules.md 不存在，先建好（格式見 kinds/README.md）")

    kind_dir = FILMS / kind
    dst = kind_dir / name
    if dst.exists():
        sys.exit(f"已經有這支片了，不覆蓋：{dst}")

    created = []
    if not (FILMS / "AGENTS.md").exists():
        FILMS.mkdir(exist_ok=True)
        shutil.copyfile(REPO / "templates" / "AGENTS_TEMPLATE.md", FILMS / "AGENTS.md")
        (FILMS / "CLAUDE.md").write_text("@AGENTS.md\n", encoding="utf-8")
        created += ["output/AGENTS.md（從 templates/AGENTS_TEMPLATE.md 建立，請改成自己的頻道規則）", "output/CLAUDE.md"]
    if not (kind_dir / "AGENTS.md").exists():
        kind_dir.mkdir(parents=True, exist_ok=True)
        (kind_dir / "AGENTS.md").write_text(KIND_AGENTS.format(kind=kind), encoding="utf-8")
        (kind_dir / "CLAUDE.md").write_text(f"@../../kinds/{kind}/rules.md\n@AGENTS.md\n", encoding="utf-8")
        created += [f"output/{kind}/AGENTS.md、CLAUDE.md（指向 kinds/{kind}/rules.md）"]

    src = REPO / "pipeline" / spec["template"]
    files = []
    for pat in spec["copy"]:
        files += sorted(p.name for p in src.glob(pat)) if "*" in pat else [pat]
    dst.mkdir(parents=True)
    for f in files:
        shutil.copy2(src / f, dst / f)

    cfg = dst / spec["config"]
    text = set_field(cfg.read_text(encoding="utf-8"), "title", name, spec["config"])
    if re.search(r'^\s*"repo_dir":', text, flags=re.M):
        text = set_field(text, "repo_dir", REPO_DIR, spec["config"])
    conf = json.loads(text)  # 確認仍是合法 JSON
    if not (dst / conf.get("repo_dir", REPO_DIR) / "tools" / "new_film.py").exists():
        sys.exit(f"{spec['config']} 的 repo_dir 指不到 repo 根目錄")
    cfg.write_text(text, encoding="utf-8")

    today = date.today().isoformat()
    extra = ["製作紀錄.md"]
    (dst / "製作紀錄.md").write_text(f"# {name}：製作紀錄\n\n## {today} 開新片\n\n- 從 pipeline/{spec['template']}/ 建立（類型：{kind}）。\n", encoding="utf-8")
    if spec.get("script"):
        (dst / "需求確認.md").write_text(REQ_TEMPLATE.format(name=name, today=today), encoding="utf-8")
        (dst / f"{spec['script']}.md").write_text(f"# {name}：{spec['script']}\n\n> 定稿後填進 {spec['config']}。\n", encoding="utf-8")
        extra = ["需求確認.md", f"{spec['script']}.md"] + extra

    for c in created:
        print("建立", c)
    print(f"建立 output/{kind}/{name}/：{'、'.join(files + extra)}")
    print(f"類型規則：kinds/{kind}/rules.md；通用規則：docs/rules/。")
    if spec.get("next"):
        print(spec["next"])
    elif spec["template"] == "template_local":
        print("film.json 目前還是範例片的角色、場景與鏡表，要換成自己的。")
    if spec.get("skill"):
        print(f"下一步照 {spec['skill']} 技能（.agents/skills/{spec['skill']}/SKILL.md）。")
    if spec.get("sandbox"):
        print("這是測試類型（沙盒）：不做發布資訊與封面。")


if __name__ == "__main__":
    main()
