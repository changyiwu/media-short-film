# .agents/skills：做片用的 agent 技能

| 資料夾 | 用途 |
|---|---|
| `short-film/` | 做片全流程：開新片（`tools/new_film.py`）→ 需求訪談 → 編劇與鏡表 →（選用）Blender 預演 → 填 `film.json` → `make_film.py` 三個人工關卡 → 自審交付。編劇部分改寫自 AI-drama-pound（MIT，見 `short-film/NOTICE.md`） |

`short-film/` 的結構：`SKILL.md` 是全片流程與「現在該讀哪份」的對照，細節依階段放在 `references/`（`interview.md`、`script/`、`previs/`、`film-json.md`、`production.md`、`review.md`）。2026-10-15 由 `ai-drama`、`blender-previs`、`new-film` 三個技能合併而成。

## 怎麼載入（不用安裝）

本資料夾是**專案層級技能目錄**，在 repo 裡啟動 agent 就能用，不要複製到全域技能目錄（2026-10-25 起；原本放 `skills/`、用 `skill-sync` 裝成全域）：

| Agent | 載入方式 |
|---|---|
| Codex／OpenCode／Antigravity | 自動載入專案的 `.agents/skills/` |
| Claude Code | 不讀 `.agents/skills/`；`CLAUDE.md` → `AGENTS.md` 的〈技能路由〉表指到對應的 `SKILL.md` |

不要另建 `.claude/skills/` 副本或符號連結（雲端硬碟不同步符號連結，副本又會跟正本分叉）。技能要用的腳本放在 `tools/`，不要放進技能資料夾；`SKILL.md` 從當前目錄往上找 repo 根。

做片入口範本在 [`templates/AGENTS_TEMPLATE.md`](../../templates/AGENTS_TEMPLATE.md)：`new_film.py` 在 `output/AGENTS.md` 不存在時會自動複製過去並加 `CLAUDE.md` 橋接，不用手動建。

> 編劇與預演的 references 原寫於上游早期（2026-08～09，雲端 Seedance、每段 30 秒、`角色資產/`、voice-clone 技能），2026-10-15 併入 `ai-film` 時已改成本 repo 的做法（本機 H3 單鏡 ≤12 秒、`output/角色/<角色>/README.md`、VoxCPM2、首幀預設 Image 2.5、定稿 DMAD 4 步不開 EasyCache）。若還看到跟 `docs/` 衝突的說法，以 `docs/` 為準並回頭修技能。

協作方法（知識庫分層、記憶、工作習慣）見 [docs/05_agent協作與知識庫.md](../../docs/05_agent協作與知識庫.md)。
