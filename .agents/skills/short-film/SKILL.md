---
name: short-film
description: 用 media-short-film repo（本機 MiniMax H3）做 16:9、1–3 分鐘 AI 短片的全流程：開新片、需求訪談、寫劇本與鏡表、（選用）Blender 預演、填 film.json、跑 make_film.py 與三個人工關卡、自審交付。當使用者說「開新片」「做一支新片」「寫短劇劇本」「想個劇情」「改台詞」「加個反轉」「審劇本」「拆鏡頭／鏡表」「做預演」「布置圖」「排鏡位」「填 film.json」「跑 make_film」「自審成片」時使用。本技能是 media-short-film 的專案層級技能（`.agents/skills/`），只在這個 repo 裡用。
---

# AI 短片（media-short-film）

> 本技能合併自 `ai-drama`（編劇，改寫自 AI-drama-pound，MIT，見 `NOTICE.md`）、`blender-previs`（預演）與 `new-film`（開新片），2026-10-15。

## 先找到 repo

本技能放在 media-short-film repo 的 `.agents/skills/short-film/`（專案層級技能，不裝全域），腳本與文件也都在這個 repo（以下寫 `<repo>`）。從目前資料夾往上找，同時有 `.agents/skills/short-film/SKILL.md` 和 `tools/new_film.py` 的那一層就是；找不到代表不在 repo 裡，請使用者到 repo 資料夾再做。

## 固定規格

| 項目 | 值 |
|:---|:---|
| 畫面 | **16:9 橫式**、24 fps；H3 1344×768 → 放大到 1920×1080 |
| 長度 | 單支 1–3 分鐘，**獨立成篇**，沒有連續劇集數 |
| 鏡頭 | **每鏡 4–12 秒**（超過 12 秒 H3 容易自己切鏡、漂移）；一鏡最多一句台詞、一個人說話 |
| 影片 | 本機 MiniMax H3，只給首幀；顯卡跑不動時 `make_film.py` 自動送 Colab |
| 生圖 | OpenAI 生圖（`gen_image.py` 預設：Image 2.5 API 優先、Codex CLI 次之，失敗就停、不自動改用千問）；本機 Qwen 為備選（整支片 `IMAGE_BACKEND=local`） |
| 定妝 | 轉面圖＋表情表＋臉部近照三張（Image 2.5），首幀依景別每個角色附 1–3 張；千問備選用單張半身 |
| 配音 | 畫面內台詞**預設 H3 拿角色參考音自己念**（`voice_mode: "h3_ref"`，念錯換 seed，抽不出來那句改 `fixed`）；角色參考音、旁白、`fixed` 的台詞用 VoxCPM2，念錯的詞加進 repo 根目錄的 `tts-lexicon.md`（只對 VoxCPM2 有效） |

## 全片流程

| # | 階段 | 讀 | 產出（都在 `films/<類型>/<片名>/`） | 人工 |
|---|---|---|---|---|
| 0 | 角色（只做一次，各片共用） | `<repo>/docs/07_角色與首幀.md`、`films/角色/README.md` | `films/角色/<角色>/` 轉面圖、表情表、臉部近照、`README.md`、參考音 | ✅ 定裝 |
| 1 | 開新片 | 本檔〈開新片〉 | 資料夾、`film.json`、`劇本.md`、`製作紀錄.md` | |
| 2 | 需求訪談 | `references/interview.md` | `需求確認.md` | ✅ 確認 |
| 3 | 劇本＋鏡表 | `references/script/workflow.md`（格式 `format.md`、拆鏡 `segmentation.md`） | `劇本.md`（含鏡表） | ✅ 確認劇本 |
| 4 | 預演（選用） | `references/previs/README.md` | 布置圖、`camera_plan_v<N>.json` | 看布置圖 |
| 5 | 填 `film.json` | `references/film-json.md` | `film.json` | |
| 5.5 | 生成前試映（文字讀本，選用草圖） | `references/table-read.md` | `output/preview/讀本試映.mp4`、`讀本_timeline.json` | ✅ 看完說「通過」才生成 |
| 6 | 生成 | `references/production.md` | `output/` | ✅ 關卡 1、2 |
| 7 | 自審與交付 | `references/review.md` | `output/cut/film_1080p.mp4`、自審報告 | ✅ 關卡 3：完整看成片 |
| 8 | 定案 | `references/review.md`〈交付與歸檔〉 | `output/<片名>.mp4`、`發布資訊.md` | ✅ 問「可以成片嗎？」，說可以才做 |

**什麼時候要做預演（第 4 步）**：多人同框、座位或左右位置容易跑掉、要運鏡、同一場景很多機位。單人、固定鏡頭的短片可以跳過。

**做第 5 步之後的任何事之前**，先讀 `films/AGENTS.md`（頻道規則）、`films/<類型>/AGENTS.md`（類型規則）、`<repo>/docs/03_規則與踩坑.md`。

## 判斷任務 → 只讀需要的檔

| 使用者要什麼 | 讀 |
|:---|:---|
| 開新片 | 本檔〈開新片〉，接著做第 2 步 |
| 完整一支短片（從點子開始） | 照全片流程，一步一步做，每個人工關卡停下來給使用者看；寫劇本時照 `references/script/workflow.md` 開頭的**階段關卡**，每階段列自我檢查、等使用者說「通過」 |
| 單點創作（只要題材、結構、某一場、台詞、反轉） | `references/script/workflow.md` 的對應階段，**只交付指定的成果**，不重做整支 |
| 想梗、加反轉、原創短劇的題材階段 | `references/script/drama-hooks.md`（四種差、20 個模式、節奏公式；**講史實的片不要套**） |
| 寫劇本或要格式 | `references/script/format.md` |
| 拆鏡頭（劇本已存在） | `references/script/segmentation.md` |
| 審劇本、改劇本 | `references/script/checklists.md`；要判斷格式再讀 `format.md` |
| 預演、布置圖、鏡位、運鏡、交付包 | `references/previs/README.md` |
| 把鏡表填進 `film.json`、寫 `frame`／`action` | `references/film-json.md` |
| 試映、估片長、分鏡草圖 | `references/table-read.md` |
| 跑 `make_film.py`、重拍某幾鏡、換配樂 | `references/production.md` |
| 自審、選鏡、交片 | `references/review.md` |
| 照參考影片換主角（保留動作、背景、聲音，只換人或換台詞的詞） | `<repo>/docs/08_換角重製.md`（不寫劇本；片子資料夾寫 `recast.json`，用 `tools/recast.py`） |

## 開新片

1. 確認類型和片名（使用者沒給就問；類型先看 `films/` 底下已有哪些，例如數學家故事、換角重製、原創短劇、測試）。兩者都是資料夾名稱，可用中文，不能含 `< > : " / \ | ? *`，也不能叫「角色」。
2. 在 `<repo>` 執行（Windows 先 `set PYTHONUTF8=1`，或用 `<repo>\tools\new_film.cmd <類型> <片名>`）：
   ```
   python <repo>/tools/new_film.py <類型> <片名>
   ```
   - 同名的片已存在會直接停下來，不覆蓋：換片名，或問使用者要不要接著做那支。
   - `films/AGENTS.md` 不存在時腳本會從 `templates/AGENTS_TEMPLATE.md` 建一份；提醒使用者把頻道名稱、主角等佔位改掉。
   - 類型資料夾是新的時，腳本會建好 `films/<類型>/AGENTS.md`＋`CLAUDE.md`；提醒使用者寫上這類片的規則（類型打錯字也會被建成新類型，看腳本列出的既有類型核對）。
3. 回報建立了哪些檔，提醒 `film.json` 裡還是範例片〈被狗吃掉的作業〉的角色、場景、鏡表。然後進第 2 步需求訪談。
- 不要手動複製 `pipeline/template_local/`（會帶到 `output/`、`__pycache__`）；自己的片一律放 `films/`（不進公開 repo）。

## 共同規則

**創作**
- 只問會實質改變結果的缺漏，一次問完；其餘採合理假設並**清楚標示「假設」**。已有答案的事（角色設定、場景）先查再問。
- 保留使用者指定的長度、類型、觀眾、場景與交付形式。
- 優先寫現在正在發生的**可見行動**，不用說明性對白代替戲劇事件；每場至少改變資訊、關係、目標、風險或情緒之一。
- 反轉要能由前文線索回看成立，**原因要在畫面上交代**；結尾留餘味或一個問題，不是單純中斷。
- **技術約束就是寫作約束**：避開快動作、打鬥、追逐；一鏡一個說話者；天馬行空放在設定與情境；畫面裡不靠可讀的文字傳達資訊（要的話後製疊字）。
- 角色外觀一律引用 `films/角色/<角色>/README.md`，不要在劇本裡每次重寫不同版本。
- 使用者只要劇本時，不輸出景別、運鏡或 H3 提示詞——那是第 5 步以後的事。

**製作**
- **需求先問齊再動工**：最大的浪費是批次生成完才發現共通缺陷。最難的一鏡先測，再批次。
- **一幕一幕做，人工關卡一定停下來給人看**；認可過的鏡頭不重拍。
- 多步驟工作開跑前，先報每一步的時間與費用；啟動背景工作後自己確認真的在跑。
- **運鏡與描述不可矛盾**：標了靜止就不寫推進；要推進就必須真的做出來。
- **不用局部貼片救表演**（禁止嘴／眼 XY 平移貼片）；表演問題回生成端重做。
- **技術通過 ≠ 使用者認可**，分開記錄；沒量的東西（例如逐音素對嘴）照實寫「沒量」。
- 不覆寫已交付或別人正在用的檔案，每次修正另存新版本。
- 金鑰不印出、不寫進專案。

## 輸出契約

- **創作任務**：必要假設 → 指定的創作成果 →（完整一支才附）鏡表。
- **審閱任務**：依影響程度排序的診斷、對應段落的證據、可執行的修改方向；只有能說明修正或使用者要求時才給改寫。
- **製作任務**：每個階段做完回報產出與下一步；到人工關卡就停，等使用者說再往下。
- 收工前在該片 `製作紀錄.md` 補一段；退件理由整理成一條規則寫進 `films/AGENTS.md`（只屬於某類影片的寫進 `films/<類型>/AGENTS.md`；agent 記憶每台電腦各一份、不會同步，不能只寫那裡）。
