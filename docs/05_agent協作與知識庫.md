# 05 AI agent 協作與知識庫

這個專案的腳本幾乎都是 AI agent 寫、也由它執行（主要用 Claude Code，Codex、OpenCode、Antigravity 也能接手）。真正讓品質穩定的，是**讓下一個 agent 知道上一個學到什麼**——不管它是哪一家、在哪一台電腦。

> 本篇是本分支的實際做法（2026-10-15 改寫）。上游原專案用單一 `CLAUDE.md`＋`資源索引/`＋Claude 記憶的做法，本分支沒有沿用，理由見各節。

## 入口檔：AGENTS.md（跨 agent）

| 檔案 | 位置 | 放什麼 | 進 git？ |
|---|---|---|---|
| `AGENTS.md` | repo 根目錄 | 專案藍圖：目標、路線圖、常設規則、資料夾結構 | ✅ |
| `CLAUDE.md` | repo 根目錄 | 只有一行 `@AGENTS.md`（Claude Code 有 `CLAUDE.md` 才不讀 `AGENTS.md`，靠它橋接） | ✅ |
| `handoff.md` | repo 根目錄 | 交接：做到哪、下一步、這次的暫時 workaround；每次收工整份重寫 | ❌（含電腦名與本機路徑，只走雲端硬碟） |
| `films/AGENTS.md` | `films/` | 做片與頻道規則、已否決的做法（範本：[templates/AGENTS_TEMPLATE.md](../templates/AGENTS_TEMPLATE.md)） | ❌（`films/` 只走雲端硬碟） |
| `films/CLAUDE.md` | `films/` | 一行 `@AGENTS.md` 橋接 | ❌ |
| `films/<類型>/AGENTS.md`（＋`CLAUDE.md`） | `films/<類型>/` | 只屬於某類影片的規則（例：數學家故事要照史料）；`new_film.py` 第一次建該類型時產生 | ❌ |

- `AGENTS.md` 是開放標準，Codex、OpenCode 直接讀；Claude Code 透過 `CLAUDE.md` 的 import 讀；**規則只寫一份**，不要在 `CLAUDE.md` 另寫。
- 三個檔案依「時效」分家：`handoff.md` 只對下一個 session 有效、`AGENTS.md` 長期有效、歷史（決策、逐次進度）放 Obsidian 或 `git log`。驗收標準：`handoff.md` 整份刪掉不應損失長期資訊。
- `AGENTS.md` 不寫逐次進度或「最新決策在最上面」那種日誌（會無限膨脹、每次開工都要重讀），只留結論式的規則。

## 知識庫分層

| 層 | 放什麼 | 本專案的位置 |
|---|---|---|
| 入口 | 專案現況、常設規則 | `AGENTS.md`、`handoff.md`、`films/AGENTS.md` |
| 答案與規則 | 使用者已接受的做法：參數、踩坑結論、重現指令 | `docs/`（規則與踩坑在 [03](03_規則與踩坑.md)、自審在 [04](04_自審清單.md)、安裝在 [06](06_安裝.md)） |
| 決策與歷史 | 為什麼這樣決定、踩坑經過的完整版、逐次進度 | Obsidian vault 的 `media-short-film/專案工作流程.md`（選用，有需要才讀）；沒有 Obsidian 就看 `git log`（commit 訊息寫「做什麼＋為什麼」） |
| 實測 | 本機 A/B 結果、數字 | 結論寫進 `docs/`（例：`docs/07` §0 多格定妝實測、`docs/hardware.md` 耗時）；大檔案（並排影片、測試圖）留在 `films/` 或本機，不進 repo |
| 每片紀錄 | 劇本、需求確認、製作紀錄 | `films/<類型>/<片名>/`（`劇本.md`、`需求確認.md`、`製作紀錄.md`） |
| 角色資產 | 定妝照、外觀描述、聲音 | `films/角色/<角色>/`（`README.md`、轉面圖、表情表、臉部近照） |

原則：
- 同一件事只有一個詳細來源，其他地方只放連結。
- 「查閱過」≠「裝了」≠「實測過」≠「使用者驗收過」，四種狀態分開寫。
- 網路來源記原始網址、發布日、查閱日、驗證狀態。
- repo 是公開的：真實電腦名、本機絕對路徑、個資、金鑰只放 `handoff.md`、`films/` 或本機。

## 記憶：只放這台電腦專屬的事

Claude Code 的自動記憶在 `~/.claude/projects/<專案路徑>/memory/`（`<專案路徑>` 是 repo 絕對路徑把分隔符換成 `-`），索引是同資料夾的 `MEMORY.md`，一事一檔，分 feedback／project／reference／user 四類。

**它存在使用者家目錄、每台電腦各一份，不會跟著雲端硬碟同步**；Codex、OpenCode、Antigravity 也讀不到。本專案在多台電腦、多家 agent 之間輪流做，所以：

| 要記的事 | 寫在哪 |
|---|---|
| 退件理由、會長期適用的做片規則（例：「主角腰上以上」「某角色不碰觸其他人」） | `films/AGENTS.md`（會同步、每家 agent 都讀得到）；只屬於某類影片的寫進 `films/<類型>/AGENTS.md` |
| 專案常設規則（工具用法、授權、路徑慣例） | `AGENTS.md` |
| 下一個 session 要知道的暫時狀況 | `handoff.md` |
| 只跟這台電腦有關的事（這台的特殊路徑、這台裝不起來的套件） | 這台的記憶，或 `handoff.md` 的注意事項 |

**退件一次就寫一條規則進 `films/AGENTS.md`（或該類型的 `films/<類型>/AGENTS.md`）**，這是品質累積最快的方式；不要只寫進記憶，換一台電腦就不見了。

## 技能（Skills）

- `.agents/skills/short-film/`：做片全流程——開新片（`tools/new_film.py`）→ 需求訪談 → 編劇與鏡表 →（選用）Blender 預演 → 填 `film.json` → `make_film.py` 三個人工關卡 → 自審交付。

技能放在專案層級的 `.agents/skills/`，**不裝到任何 agent 的全域目錄**：做片都在本 repo 裡做，改完直接生效，也不用每台電腦各同步一次。Codex、OpenCode、Antigravity 在本專案內會自動載入；Claude Code 不讀 `.agents/skills/`，靠 `CLAUDE.md` → `AGENTS.md` 的〈技能路由〉表去讀對應的 `SKILL.md`。細節見 [.agents/skills/README.md](../.agents/skills/README.md)。

## 工作習慣

- **開工說「開工」、收工說「收工」**（全域技能 `project-startup`／`project-shutdown`）：開工讀 `AGENTS.md`＋`handoff.md`、檢查 git 與遠端、提醒是否在另一台電腦收工；收工重寫 `handoff.md`、commit＋push、寫 Obsidian 紀錄。
- 多步驟工作開跑前**先報每一步的時間與費用**。
- 啟動背景工作後**自己確認真的在跑**（log、佇列、GPU 使用率）。
- 「我去睡了」＝授權自動做完並自審，GPU 不要閒著；早上交成片＋自審報告。
- 一幕一幕做，做完先給人看；認可過的鏡頭不重拍。
- 使用者說「不要用 A 方法避開」時，不要擅自換別的繞路。
- 金鑰不印出、不寫進專案。

## 多台電腦協作

本專案在多台電腦之間輪流做，靠**雲端硬碟同步整個 repo 資料夾＋GitHub**：

- 硬體分工：GPU 工作（ComfyUI、H3、本機生圖、配音）在桌機做（`configs\profile.cmd`）；RTX Spark 筆電用 `configs\profile_rtxspark.cmd`，相容性見 [hardware_rtxspark.md](hardware_rtxspark.md)。沒有 profile 的電腦先跑 `setup/detect_hardware.py`，適合做不吃顯存的工作：劇本、研究、文件、自審。
- `handoff.md` **全專案一份**，誰收工誰整份重寫，「最後更新」欄寫電腦名；開工時若上次是別台收工，先確認雲端硬碟同步完再動工。
- git 每台都可以 commit／push，開工先 fetch、落後就先 pull；`films/` 與 `handoff.md` 不在 git 裡，只靠雲端硬碟。
- 模型權重、venv、ComfyUI 每台各自安裝（不進雲端硬碟），技能每台各自同步。
