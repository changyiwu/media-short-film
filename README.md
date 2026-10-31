# AI 短片製作工作流（16GB 顯卡版：16GB VRAM＋64GB RAM）

> **來源**：本專案改作自 [mathruffian-dot/shanshiba-workflow-16gvram-64gram](https://github.com/mathruffian-dot/shanshiba-workflow-16gvram-64gram)，原作者「山獅霸的多重宇宙」（<https://github.com/mathruffian-dot>）。文件以 CC BY-NC 4.0、程式碼以 MIT 授權，修改內容與完整來源標示見 [NOTICE.md](NOTICE.md)。

製作 1–3 分鐘、16:9、24fps 原創短片的完整工作流：劇本由 AI agent（Claude Code）協作；**角色與首幀預設用 OpenAI 生圖（Image 2.5 API 優先、Codex CLI 次之），本機 Qwen-Image 為備選**（失敗就停下，要用本機得整支片指定 `IMAGE_BACKEND=local`）；影片、配音、配樂用本機模型生成，挑音、後製、自審全部腳本化；人只在劇本、首幀、成片三個關卡驗收。

> 本 repo 不含任何人物照片、克隆聲音、API 金鑰、角色定妝照與模型權重。

## 1. 這份是給誰的

| 項目 | 內容 |
|---|---|
| 顯卡 | 16GB：RTX 4080／5070 Ti／5080 |
| 記憶體 | 64GB |
| 硬碟 | NVMe SSD，模型約 145GB＋工作空間 |
| 狀態 | **2026-10-07 在 RTX 5090 上模擬 16GB 驗證**：同 seed 跟 32GB 顯卡**逐格相同**、顯存峰值約 14.4GB、10.8 秒長鏡頭可跑；真實 16GB 卡速度未實測 |
| 跟完整版的差別 | 模型、流程都一樣；只多一個啟動參數 `--reserve-vram 1.5`，且一次只跑一件 GPU 工作 |
| 一支 40 鏡的片 | H3 部分推估約 1.5–2 小時（32GB 顯卡約 41 分鐘） |

詳細：[docs/hardware.md](docs/hardware.md)

## RTX Spark 筆電

Windows on Arm＋64GB 統一記憶體的 RTX Spark 筆電另有設定（`configs/profile_rtxspark.cmd`），**尚未實機驗證**；安裝步驟、套件相容性與建議分工見 [docs/hardware_rtxspark.md](docs/hardware_rtxspark.md)。

## 其他硬體版本

32GB 顯卡、16GB＋32GB RAM、Google Colab 的版本由上游原作者維護，連結見 [NOTICE.md](NOTICE.md)。每一版都有 `cloud/`，本機跑不動時可以把 H3 送到 Colab。

> ⚠️ **本 repo 預設給非商業用途**（教學、研究、個人創作）。用到的 **Qwen-Image 2.1 只能非商業使用**；要營利請照 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 處理（生圖預設已是雲端 Image 2.5，商用時關掉本機備選 `IMAGE_FALLBACK=0`）。配音引擎 VoxCPM2 是 Apache-2.0，可商用。另外**MiniMax H3 的授權排除美國、歐盟、英國、南韓**；MiniMax H3／Music 3 要求公開內容標示 AI 生成。本 repo 不含任何模型權重。

## 2. 流程一覽

```
選題 → 劇本 ─✅─→ 角色定妝：轉面圖＋表情表＋臉部近照（Image 2.5）→ 首幀（Image 2.5）─✅─→ 配音候選 → 自動挑音
     → H3 生成（DMAD 4 步）→ RTX VSR 放大 → 後製（名片、字卡、音效、配樂、字幕）
     → 組裝 →（選用）片尾 → 自審五遍 ─✅─→ 上架資訊（`發布資訊.md`，附 AI 生成標示）─✅─→ 發 YouTube＋社群
                                           ✅ = 人工驗收關卡
```

除了生圖預設走雲端 Image 2.5，其餘全部在本機生成（另外只有挑音用的「台灣國語答案卷」edge-tts 需要連網，沒網路時改用 VoxCPM2 設計的播報聲音）。
每一步用哪支腳本、輸入輸出是什麼：[docs/02_端到端流程.md](docs/02_端到端流程.md)；角色與首幀做法（預設 OpenAI 生圖、本機千問備選）：[docs/07_角色與首幀.md](docs/07_角色與首幀.md)。

**裝好之後先跑全本地示範片** `pipeline/demo_local/run_demo.py`：從零做兩個角色、4 鏡、配音、配樂，約 17 秒成片，證明整條工作流在你的電腦上能跑通。

## 3. 目錄

```
README.md
docs/
  01_總覽與架構.md          三層架構、為什麼這樣分
  02_端到端流程.md          逐步驟：工具、產出、耗時、人工關卡
  03_規則與踩坑.md          所有規則（附理由）＋踩坑對策
  04_自審清單.md            review.py 五遍＋常退件清單
  05_agent協作與知識庫.md   讓 AI agent 長期接手的做法
  06_安裝.md                環境、模型、資料夾慣例
  07_角色與首幀.md          角色定妝與首幀：預設 OpenAI 生圖、本機 Qwen 備選（兩種做法）
  08_換角重製.md            照參考影片換主角：骨架控制、仿原聲換詞、字卡後製（不走 make_film.py 的 h3）
  hardware.md               ⭐ 你這個硬體版本：模型組合、啟動參數、實測數據、風險
tools/                      全域工具（各腳本直接用，不用複製）
  h3_shot.py ⭐             分鏡 JSON → 官方格式提示詞 → 格式檢查 → H3 生成
  table_read.py             生成前試映：照 film.json 估片長、做文字讀本試映影片（選用 16 宮格草圖）
  make_voxcpm.cmd          配音備選與參考音設計：VoxCPM2 每句 8 候選 → 聽寫＋腔調自動挑
  make_ming.cmd ⭐          預設配音引擎 Ming-3.0-TTS：每句 8 候選 → 同一套自動挑音
  h3_line_harvest.py        台詞預設由 H3 自己念：從成片抓出台詞、拼音比對原文
  tts_lexicon.py            讀音替換表：送進 TTS 前照根目錄 tts-lexicon.md 把念錯的詞改字
  gen_image.py              生圖入口：預設 OpenAI Image 2.5，備選本機 Qwen-Image 2.1／Edit（--backend local）
  start_comfy.cmd           啟動 ComfyUI
  img25.py                  OpenAI Image 2.5 生圖／編輯（gen_image.py 預設呼叫它）
  pron_check.py／pron_compare.py  中文配音聲調審核
  ...（完整清單見 docs/06_安裝.md）
pipeline/template_local/    ⭐ 做新片的範本：tools/new_film.py <類型> <片名> 複製成 output/<類型>/<片名>/ → 改 film.json → make_film.py 從角色做到成片＋自審
pipeline/demo_local/        全本地示範片（4 鏡，安裝驗證用，不需要任何素材）
setup/                      安裝：模型下載清單（鎖定版本＋逐檔雜湊）、套件清單、smoke_test、硬體偵測
cloud/                      ⭐ 本機跑不動時：H3（或整套流程）送到 Google Colab G4 跑（colab_h3.py；見 cloud/README.md）
sfx/                        58 個 Freesound CC0 音效（腳步、翻頁、門、球、歡呼…）
templates/                  片尾範本、咒印法陣素材、AGENTS_TEMPLATE.md 做片入口範本、發布資訊範本.md
.agents/skills/             專案層級 agent 技能：short-film 做片全流程（不用安裝，見 .agents/skills/README.md）
configs/profile.cmd         這個硬體版本的環境變數
```

## 4. 最快上手

0. **AI agent 請先讀 [AGENT_SETUP.md](AGENT_SETUP.md)**，它會一步步帶你檢查硬體、安裝、下載、驗證。`python setup/detect_hardware.py` 會列出每個元件建議在本機還是雲端跑；**本機跑不動 H3 → [cloud/README.md](cloud/README.md)**（用 Google AI 方案的 Colab 運算單元跑）。
1. 照 [AGENT_SETUP.md](AGENT_SETUP.md) 裝好 ComfyUI＋H3、Voice 環境（含 VoxCPM2）。`tools/` 不用複製，腳本直接用 repo 裡的。
2. 先讀 [docs/hardware.md](docs/hardware.md)，再在同一個 cmd 視窗 `call configs\profile.cmd` 套用這個硬體版本的設定，然後執行 `<repo>\tools\start_comfy.cmd`。
3. 跑 `setup\smoke_test.py` 與 `pipeline\demo_local\run_demo.py` 確認全部正常。
4. 開始做自己的片，照下面的檢查表一步一步來（2026-10-07 實測：一個沒看過本專案的 agent 照這個 repo，約 45 分鐘做出 7 鏡、28 秒的片）。

| # | 步驟 | 工具 | 看哪份文件 | 產出 | 要人工看嗎 |
|---|---|---|---|---|---|
| 1 | 劇本＋鏡表（每鏡 ≤12 秒） | `.agents/skills/short-film` | `SKILL.md`、`docs/03` | `劇本.md` | ✅ 確認劇本 |
| 2 | 角色定妝：轉面圖＋表情表＋臉部近照（備選千問：單張、灰底、半身） | `gen_image.py`（預設 Image 2.5；備選 Qwen-Image 2.1） | `docs/07` §0（備選 §1） | `chars/<角色>_turn.png`、`_expr.png`、`_face.png`（備選 `chars/<角色>.png`） | ✅ 定案 |
| 3 | 場景母版（空景，之後裁成各鏡景別） | `gen_image.py` | `docs/07` §4 | `masters/*.png` | |
| 4 | 首幀（附定妝＋母版裁切，**每鏡照抄角色完整外觀描述**） | `gen_image.py --model qwen-edit --ref`（預設 OpenAI 生圖（Image 2.5 或 Codex）依每鏡 `sheets` 附 1–3 張定妝，`--model` 這時不作用；`IMAGE_BACKEND=local` 時才用 Qwen-Image-Edit 附單張半身，不加會用到不適合附參考圖的 Qwen-Image 2.1） | `docs/07` §2–3 | `first/<鏡>.png` | ✅ 逐張看：臉、服裝、多手多腳、背景有沒有字 |
| 5 | 角色參考音（定裝時跟定妝圖一起做一次，存進 `output/角色/` 各片沿用，防聲音漂移）；旁白與 `fixed` 台詞的配音 | `voxcpm_batch.py`（設計參考音）→ `make_voxcpm.cmd`；念錯的詞加進 `tts-lexicon.md` | `docs/03` §5 | `voice/ref_<角色>.wav`、`bv/<句>.wav`（已去頭尾靜音） | `needs_review` 的句子聽一次 |
| 6 | H3 每鏡（DMAD 4 步、只給首幀；台詞預設由 H3 拿角色參考音自己念（`voice_mode: "h3_ref"`），`fixed` 的句子當固定音軌；看得到臉又沒台詞的鏡給靜音） | `h3_shot.py`（spec 加 `"draft": true`） | `docs/03` §4、`tools/examples/` | `h3/<鏡>/clip.mp4` | ✅ 抽格看：換臉、多人、鏡頭漂移 |
| 7 | 配樂（純器樂、多抽幾個 seed，挑人聲殘留最少的） | `gen_music3.py` → `audio-separator` | `docs/02` §8 | `music/*.flac` | |
| 8 | 放大、剪接（台詞提前 0.2 秒）、配樂壓低（台詞期間 15–30%）、響度、字幕 | `upscale_vsr.py`、ffmpeg | `docs/02` §9、§10（**`alimiter` 要 `level=false`**） | `cut/<片名>_1080p.mp4` | |
| 9 | （選用，預設不加）片尾（工具名單＋AI 生成標示；要加就把 `film.json` 的 `ending.enabled` 改成 true 或設 `ENDING=1`；沒片尾時在貼文標示） | `templates/ending/render_ending.py` | `templates/ending/README.md`、`docs/02` §12 | `ending.mp4` | |
| 10 | 自審五遍（抽格、ASR、雜訊、黑畫面與響度、切點） | `pipeline/template_local/review.py`（呼叫 `noise_scan.py`、`stt.py`） | `docs/04_自審清單.md` | `review/` | ✅ 最後一定給人看成片 |

**最快的做法：`python tools/new_film.py <類型> <片名>` 從 [`pipeline/template_local/`](pipeline/template_local/README.md) 建好 `output/<類型>/<片名>/`，只改 `film.json`**，`make_film.py` 會把上面 2–10 步全部做完（已附一支 7 鏡範例片的設定，從零重跑驗證過）。`pipeline/demo_local/` 是 4 鏡的最小安裝驗證。

建議讓 AI agent 來跑：第一次跑 `python tools/new_film.py <類型> <片名>` 時，會把 [templates/AGENTS_TEMPLATE.md](templates/AGENTS_TEMPLATE.md) 複製成 `output/AGENTS.md`（做片規則入口），改成自己的頻道規則後，agent 會照規則做、自審、寫紀錄。

## 5. 最重要的十條經驗

1. **H3 提示詞一律用官方六段格式**，用 `h3_shot.py` 從 JSON 組，不手寫。
2. **預設只給首幀**；多人鏡加身份參考圖會多長出一個人。
3. **DMAD 4 步就是定稿**：抽到滿意的直接用，同 seed 換 14 步畫面會不同。
4. **單鏡 ≤12 秒**；15 秒會漂移、自己切鏡。
5. **不說話的鏡頭給靜音引導音軌**，否則角色會自己嘟囔。
6. **畫面上的中文一律後製疊字**，H3 會把字寫成亂碼。
7. **台灣腔配音**：VoxCPM2 設計角色聲音（一次）→ Ming-3.0-TTS 用它念每句台詞（每句 8 候選）→ 聽寫全對＋跟台灣國語參考音比聲調自動挑；念錯的多音字、英文詞加進讀音替換表 `tts-lexicon.md`（送進 TTS 前自動改字，字幕照原文；四個 TTS 相關 repo 各帶一份、內容相同，各自單獨可用），只有某句的就改同音字。
8. **低頭、轉身後臉會換人** → 再生一張「動作結束時」的畫面當尾幀鎖住（預設 Image 2.5；本地可用 Qwen-Image-Edit 附定妝照）。
9. **先做最難的一鏡再批次**，不要整片生完才發現共通問題。
10. **不合格就重拍到合格**，不靠剪掉躲；給人看並排影片，數字只當備註。

## 6. 這個 repo 沒有放的東西

| 東西 | 原因 | 你要自己準備 |
|---|---|---|
| 上游原頻道的角色定妝照、轉面圖、表情表 | 原作者的角色資產 | 用 Image 2.5 為自己的角色做轉面圖＋表情表＋臉部近照；備選用本機 Qwen-Image 2.1 做單張半身定妝照（見 [07_角色與首幀.md](docs/07_角色與首幀.md)） |
| 配音參考音 | 屬於個人聲音，不散布 | 自己錄或用 VoxCPM2 設計 |
| 模型權重 | 檔案大、各有授權、可照清單重現（詳見 [docs/06 §1](docs/06_安裝.md)） | 照 [AGENT_SETUP.md](AGENT_SETUP.md) 第 3 節下載（約 150GB） |
| 成片影片 | 檔案大 | — |
| OpenAI 金鑰 | **生圖預設用 Image 2.5 API**（要金鑰）；沒有金鑰時改走已用 ChatGPT 登入的 Codex CLI（扣訂閱額度），兩者都不行就停下，要用本機 Qwen 得設 `IMAGE_BACKEND=local` | 自己設環境變數 `OPENAI_API_KEY`（或 `OPENAI_KEY_FILE`、`~/.openai.env`），見 `docs/06_安裝.md` §6 |
| Google AI 方案／Colab 運算單元（選用） | 本機跑不動 H3 時才需要 | 見 [cloud/README.md](cloud/README.md) |

（音效有附：`sfx/` 裡 58 個 Freesound CC0 音效。）

## 7. 授權

| 內容 | 授權 | 檔案 |
|---|---|---|
| 本 repo 的程式碼（`*.py`、`*.ps1`、`*.cmd`、`*.sh`、設定檔） | **MIT** | [LICENSE](LICENSE) |
| 本 repo 的文件與素材（`*.md`、技能文字、範例圖） | **CC BY-NC 4.0**（姓名標示、非商業） | [LICENSE-docs.md](LICENSE-docs.md) |
| 用到的模型與第三方工具 | 各自的授權（**不隨本 repo 散布，自行下載**） | [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) |

fork 或轉載時請保留這三個檔案與 [NOTICE.md](NOTICE.md)（來源與作者標示）。用這套工作流做出來的影片要遵守各模型的條款，特別是：MiniMax H3 的使用地區限制、MiniMax Music 3 的標示與 AI 揭露、Qwen-Image 2.1 的非商用限制（細節見 THIRD_PARTY_NOTICES.md）。
