# <頻道名稱>：做片規則

> 做片入口範本：`tools/new_film.py` 在 `output/AGENTS.md` 不存在時把本檔複製過去（並建一行 `@AGENTS.md` 的 `CLAUDE.md` 橋接），再改成自己的頻道規則。各類型資料夾的 `<類型>/AGENTS.md` 由 `new_film.py` 第一次建該類型時產生，只放那類影片的規則。Codex、opencode 直接讀 `AGENTS.md`；Claude Code 讀 `output/` 底下的檔案時透過 `CLAUDE.md` 自動載入。
> 本資料夾已列入 repo 的 `.gitignore`：只走雲端硬碟同步，**沒有 GitHub 備份**。
> 本檔只放長期有效的規則；每支片的進度與教訓寫在 `<類型>/<片名>/製作紀錄.md`；退件理由整理成規則，所有片都適用的寫進本檔、只屬於某類影片的寫進 `<類型>/AGENTS.md`（不要只寫 agent 記憶：記憶每台電腦各一份、不會同步，見 `docs/05`）。

## 專案簡介

<頻道名稱、主角、每月產量、片長、風格>

## 資料夾

```
output/
  AGENTS.md、CLAUDE.md   本檔＋橋接
  角色/<角色>/            轉面圖、表情表、臉部近照、README.md（鎖定的外觀描述）、參考音；各類型共用
  <類型>/                 影片類型（例：數學故事、換角重製、原創短劇、測試）
    AGENTS.md、CLAUDE.md  這個類型專屬的規則＋橋接（new_film.py 第一次建這個類型時自動建立）
    <片名>/               用 tools/new_film.py 從 ../pipeline/template_local/ 建立；film.json 的 repo_dir 是 "../../.."
      <片名>.mp4（定案成片）  發布資訊.md  劇本.md  製作紀錄.md  film.json  work/（工作檔、log/）
```

開新片：說「開新片 <類型> <片名>」（`short-film` 技能），或在 repo 根目錄跑 `python tools/new_film.py <類型> <片名>`；再改 `film.json`，照 `pipeline/template_local/README.md` 跑 `make_film.py`。

## 影片規格

| 項目 | 設定 |
|---|---|
| 畫面比例 | 16:9 橫式（Shorts 用 9:16 重新生成，不裁切） |
| 解析度 | H3 1344×768 → 放大到 1920×1080 |
| 幀率 | 24 fps |
| 單鏡長度 | ≤12 秒 |

## 必讀（開工前）

- 生角色圖前：讀 `角色/<角色>/README.md`，照抄鎖定的外觀描述，不要自己重寫。
- 做片流程（訪談、劇本、預演、`film.json`、製作、自審）：照 `short-film` 技能（`.agents/skills/short-film/`）。
- H3：一律寫分鏡 JSON，用 `<repo>\tools\h3_shot.py`（官方格式＋格式檢查），不手寫提示詞；用 `make_film.py` 時由它產生。
- 做片前讀：`../docs/03_規則與踩坑.md`、`../docs/04_自審清單.md`。

## 預設做法

- 定妝：預設 OpenAI 生圖（Image 2.5 API 優先、Codex CLI 次之）一次生轉面圖＋表情表＋臉部近照三張，首幀依景別每個角色附 1–3 張（每鏡 `sheets`）；失敗就停下，不自動改用千問。千問備選要整支片設 `IMAGE_BACKEND=local`，改用單張半身照。
- 首幀：`gen_image.py --model qwen-edit --ref <定妝>`。預設送 OpenAI 生圖（Image 2.5 或 Codex，`--model` 這時不作用）；`IMAGE_BACKEND=local` 時 `--model qwen-edit` 讓它用 Qwen-Image-Edit 2511，而不是會把參考圖照抄成正面姿勢的 Qwen-Image 2.1。**每一鏡提示詞都照抄角色完整外觀描述**；做法見 `../docs/07_角色與首幀.md`。
- 影片：本機 H3，只給首幀；需要時加尾幀。`"draft": true`（DMAD 4 步）是定稿。
- 片尾：預設不加（`ending.enabled: false`）；使用者要才打開。沒片尾時，AI 生成標示寫在貼文。
- 照參考影片換主角：照 `../docs/08_換角重製.md`。
- 配音：角色參考音在定裝時（`make_film.py chars`）做好，定案存進 `角色/<角色>/ref_<代號>.wav`，之後每支片複製沿用、不重新設計（防聲音漂移）。畫面內的角色台詞預設由 H3 拿角色參考音自己念（`film.json` 的 `voice_mode: "h3_ref"`；跑完 `h3` 看 `work/voice_picks.json` 的 `heard` 跟原文對一遍，念錯換 seed，抽 2–3 次還錯那句改 `"voice_mode": "fixed"`）。旁白與 `fixed` 的台詞用 `<repo>\tools\make_voxcpm.cmd jobs.json`（VoxCPM2，每句 8 候選自動挑；`make_film.py` 內建），念錯的多音字、英文詞加進 `<repo>\tts-lexicon.md`（讀音替換表，只對 VoxCPM2 有效，字幕照原文），只有某句的就改同音字，`needs_review` 的句子請人聽。
- 配樂：MiniMax Music 3 純器樂。
- 放大：近景 RTX VSR、全景 FlashVSR（RTX Spark 筆電見 `../docs/hardware_rtxspark.md`）。
- 雲端影片服務（Seedance 等）：使用者明說才用。

## 工作習慣

- 多步驟工作開跑前，先報每一步的時間與費用。
- 啟動背景工作後，自己確認真的在跑（log、ComfyUI `/queue`、GPU 使用率）。計時看 `/history`。
- 交片前自己跑 `review.py` 五遍＋常退件清單，不合格就重拍。
- 使用者說「我去睡了」＝授權自動做完並自審；早上交成片＋自審報告。
- 一幕一幕做，做完先給人看；認可過的鏡頭不重拍。
- 收工前：在該片 `製作紀錄.md` 補一段；退件理由整理成一條規則寫進本檔（`output/AGENTS.md`）；只屬於某類影片的寫進 `output/<類型>/AGENTS.md`。
- 金鑰不印出、不寫進專案。

## 已否決的做法（不要再提）

| 做法 | 原因 |
|---|---|
| <例：EasyCache 當定稿> | <近景糊、靜止鏡雜訊> |
