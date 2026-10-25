# 來源標註

本技能的流程骨架（八階段編劇流程、劇本格式規範、審閱清單結構）改寫自：

**[POUND0423/AI-drama-pound](https://github.com/POUND0423/AI-drama-pound)** — `ai-short-drama-screenwriter`，MIT License，v0.1.0（2026-08-26）。

## 本專案的改動

| 項目 | 原版 | 本版 |
|:---|:---|:---|
| 平台 | OpenAI Codex（`~/.agents/skills/`） | Claude Code（專案內 `.claude/skills/`） |
| 畫面比例 | 豎屏 9:16 | **16:9 橫式** |
| 篇幅結構 | 8–12 集連續短劇 | **單支 1–2 分鐘，獨立成篇** |
| 角色 | 每次從零設計 | **上游頻道的固定主角**（本分支已改為佔位），引用專案 Character Bible |
| 技術限制 | 無 | **Seedance 2.5 可行性檢查**（避開快動作、單一說話者） |
| 階段數 | 8 | **9**（新增〈片段切分與素材備料〉） |
| 新增檔案 | — | `references/segmentation.md` |

原專案的 `agents/openai.yaml` 未沿用（Claude Code 不使用該格式）。

## 原作授權全文

見同資料夾 `LICENSE-AI-drama-pound.txt`（MIT，Copyright (c) 2026 POUND0423）。

## 本分支（fork）的再修改（2026-10-11，changyiwu）

上表為上游 mathruffian-dot 版本對 AI-drama-pound 的改動。本分支另外：技能資料夾由 `shanshiba-drama` 改名為 `ai-drama`；references 中原頻道固定主角的名稱改為佔位的「主角」／「阿凱」，主角人設改為引用使用者自己的角色設定檔。2026-10-14：影片模型改為本機 MiniMax H3，`references/workflow.md` 全文改寫為白話，`references/segmentation.md` 由「≤30 秒片段＋LoRA caption」改寫為「每鏡 ≤12 秒的鏡表」，`checklists.md`、`format.md` 的 Seedance 相關段落同步改寫（上表「技術限制」一列為上游當時的版本）。

2026-10-15：`ai-drama`、`blender-previs`、`new-film` 三個技能合併為 `ai-film`（本資料夾；2026-10-20 技能改名 `short-film`）。原 `ai-drama` 的 `references/` 移到 `references/script/`，`SKILL.md` 改寫為全片流程；本表與上段提到的檔案路徑為當時的位置。
