# AI 影片工作流（專案藍圖）

> 本檔為跨 Agent 通用的專案藍圖（AGENTS.md 開放標準）。任何 Agent 的每個 session 都應先讀本檔＋`handoff.md`。
> Claude Code 預設只在沒有 `CLAUDE.md` 時才讀 `AGENTS.md`，故由 `CLAUDE.md` 的 `@AGENTS.md` import 本檔（`CLAUDE.md` 只有這一行）；Claude 專屬規範寫在本檔〈Claude Code 專屬〉一節。

## 專案簡介
在 16GB VRAM＋64GB RAM 的本機，用開源模型（MiniMax H3、Qwen-Image 2.1／Edit、VoxCPM2、MiniMax Music 3）製作 1–3 分鐘、16:9、24fps 的原創 AI 短片。改作自 [mathruffian-dot/shanshiba-workflow-16gvram-64gram](https://github.com/mathruffian-dot/shanshiba-workflow-16gvram-64gram)，來源與修改內容見 `NOTICE.md`。

## 關鍵時程

- 2026-10-25：從 `media-music-video`（原 `media-comfyui-studio`）搬入古裝庭院惡搞短片《臭豆腐》（`films/原創短劇/臭豆腐/`）與 H3 灰模動作參考測試（`films/測試/測試_H3灰模動作參考/`，瘦身後只留筆記、參考片產生腳本與對照圖）

## 目標與路線圖
- [x] 階段一：複製上游 repo、移除原作者個人資訊、加上來源標示、專案初始化
- [ ] 階段二：照 `AGENT_SETUP.md` 檢查硬體（`python setup/detect_hardware.py`）、安裝環境與下載模型
  - [x] 桌機 Comfy Desktop 補齊（`AGENT_SETUP.md` §2a）：補裝 7 個套件、FlashVSR 節點、下載 DMAD／FlashVSR
  - [x] 建 `%AI_ROOT%\Voice` 語音環境並下載 VoxCPM2
  - [x] 設定 OpenAI 金鑰，生一張圖驗證 Image 2.5 模型 ID
  - [x] 實測多格定妝（`make_film.py chars frames`）：轉面圖四格同一人、首幀不照抄格子版面、臉夠像（不像先試 `IMG25_REF_SCALE=1`），結果寫進 `docs/07` §0
- [ ] 階段三：跑 `setup/smoke_test.py` 與 `pipeline/demo_local/run_demo.py` 驗證
  - [x] 桌機 `smoke_test.py` 12 步全部 OK（秒數見 `docs/hardware.md`）
  - [x] 桌機 `run_demo.py`（約 27 分鐘，成片待人工看過）
  - [ ] VoxCPM2 預設配音流程（`voxcpm_batch.py`＋挑音）實機驗證：台灣腔、聽寫通過率、速度
- [ ] 階段三之二：RTX Spark 筆電上機驗證（照 `docs/hardware_rtxspark.md`「第一次上機」，結果回填該文件）
- [x] 階段四：建立第一個角色（`films/角色/`），用 `short-film` 技能（`tools/new_film.py`）做第一支片
  - [x] 角色「狗狗」（`films/角色/狗狗/`）＋第一支片〈狗熊哆嗦毛_狗狗版〉（換角重製，`docs/08`）
- [ ] 階段五：換角重製工具化與其他版本
  - [x] 把首幀換角、各鏡 spec／骨架切段、剪接收尾的一次性腳本整理成 `tools/recast.py`（片子資料夾放 `recast.json`）
  - [x] 舞蹈鏡嘴型：聽寫寫台詞＋閉嘴首幀＋換 seed（`docs/08`〈有發聲的骨架鏡〉）
  - [ ] 〈狗熊哆嗦毛〉台灣黑熊、貓貓版（「台灣黑熊」比「狗熊」多兩字，開頭鏡要拉長）
- [ ] 階段六：劇本導向教學片（`films/數學家故事/`）
  - [x] `films/` 依影片類型分資料夾（`films/<類型>/<片名>/`，類型規則在 `films/<類型>/AGENTS.md`）
  - [x] `make_film.py` 範本支援旁白（`narrator`＋`vo`）、後製插入鏡（`insert`）、疊字（`overlay`）、每鏡 `setting`／`soundscape`、統一人聲響度（`mix.voice_lufs`）
  - [x] 角色「埃拉托賽尼」＋〈埃拉托賽尼的篩子〉（1.5 分鐘課堂引起動機）成片 99 秒
  - [x] 〈埃拉托賽尼的篩子〉人聲音量確認，存為範本 `film.json` 的預設混音
  - [x] 〈埃拉托賽尼的篩子〉發布資訊（YouTube＋Facebook，`films/數學家故事/埃拉托賽尼的篩子/發布資訊.md`）
  - [x] `pron_check.py` 的「不」「一」一律記本調、變調交給 `sur`（「不是」「不適」不再判成不同聲調）
  - [x] 配樂維持 14 段，乾淨的都不夠長時交叉淡入自動接長（多寫段數會讓 Music 3 唱歌）
  - [x] `.gitattributes` 讓 `*.cmd`／`*.bat` 簽出成 CRLF
  - [x] 角色「歐幾里得」＋〈歐幾里得的完美數〉（課本 88 頁〈完美數〉，依史料改主角為歐幾里得）成片 100 秒＋發布資訊
  - [x] 挑音加響度與嘶聲篩選、配音混音前濾波與真峰值把關；`breezyvoice_pick.py` 改名 `voice_pick.py`
  - [x] 每鏡配樂倍數（`music_gain`）併進範本
  - [x] 移除選用配音引擎 BreezyVoice／Breeze TTS 2；讀音替換表從 media-video-specs 移植成兩專案共用的 `tts-lexicon.md`

## 資料夾結構
```
README.md / AGENT_SETUP.md     專案說明、給 agent 的安裝手冊
NOTICE.md                      來源與作者、本分支修改清單（必須保留）
LICENSE / LICENSE-docs.md      MIT（程式）／CC BY-NC 4.0（文件素材）
THIRD_PARTY_NOTICES.md         第三方模型與工具授權
tts-lexicon.md                 讀音替換表（多音字、英文詞 → TTS 念得對的寫法；四個 repo 各一份、內容相同，同層時合併讀取）
docs/                          總覽、端到端流程、規則與踩坑、自審清單、安裝、角色與首幀、換角重製、硬體說明
tools/                         全域工具（各腳本直接用這裡，不再複製到 C:\AI\tools）
films/                         自己的片與角色資產（.gitignore，不進 repo；規則見 films/AGENTS.md）
pipeline/                      template_local（新片範本）、demo_local（安裝驗證）
setup/                         模型下載清單、套件清單、smoke_test、硬體偵測、16GB 模擬測試
cloud/                         H3 送 Google Colab 跑
sfx/                           Freesound CC0 音效
templates/                     片尾範本、法陣素材、AGENTS_TEMPLATE.md（做片入口範本）、發布資訊範本.md（YouTube／FB／IG／Threads；五個媒體專案各一份、內容逐位元組相同，正本在 media-youtube-publish 的 `skills/youtube-video-workflow/references/`，改正本再整份覆蓋，不在本專案就地改）
skills/                        技能原始檔：short-film（做片全流程：開新片、訪談、編劇、預演、製作、自審；說「同步技能」裝成全域）
configs/profile.cmd            桌機（16GB VRAM＋64GB RAM）環境變數
configs/profile_rtxspark.cmd   RTX Spark 筆電（Windows on Arm＋64GB 統一記憶體）環境變數
setup/spark_check.py、setup/env/arm64/   RTX Spark 相容性檢查與 ARM64 套件清單
```

## 專案專屬規則

### 授權與來源
- **僅限非商業用途**：文件素材為 CC BY-NC 4.0；Qwen-Image 2.1 只能非商用。要營利前先照 `THIRD_PARTY_NOTICES.md` 替換模型。
- **必須保留來源標示**：`LICENSE`、`LICENSE-docs.md`、`THIRD_PARTY_NOTICES.md`、`NOTICE.md`、`skills/short-film/NOTICE.md`、`skills/short-film/LICENSE-AI-drama-pound.txt` 不可刪除或移除原作者署名；修改上游文件時在 `NOTICE.md` 的修改清單補一筆。

### 生圖
- 預設 OpenAI 生圖（`gen_image.py` 的 `IMAGE_BACKEND=auto`）：第一優先 Image 2.5 API（金鑰，確定是 Image 2.5），找不到金鑰才走 Codex CLI（`tools/codex_image.py`，扣 ChatGPT 訂閱，模型版本無法確認），兩者都不行、或選定後生成失敗就停下，不改試另一個、不自動改用千問；本機 Qwen-Image 為備選，要用就整支片設 `IMAGE_BACKEND=local`。金鑰由使用者自己設定（`OPENAI_API_KEY`／`OPENAI_KEY_FILE`／`~/.openai.env`），agent 不經手、不讀出內容、不寫進 repo。
- `run_demo.py`、`smoke_test.py` 固定 `--backend local`（驗證本機安裝用）。
- 角色定妝一次生三張多格圖：轉面圖（全身正、3/4、側、背）＋表情表（六格）＋臉部近照（正面＋3/4 兩格），首幀依景別每個角色附 1–3 張（每鏡 `sheets`，沒寫＝轉面圖＋表情表）；千問備選才用單張半身照（Qwen 會把多格版面照抄成拼貼）。
- 走 Codex 的圖由 `make_film.py` 記成 `codex`，片尾寫「OpenAI 生圖（Codex）」；不要再手動用 `draw` 代 `make_film.py` 生圖（不會記到 `output/image_backends.json`，片尾名稱會錯）。

### 配音
- 畫面內的角色台詞預設由 H3 拿角色參考音自己念（`film.json` 的 `voice_mode: "h3_ref"`，2026-10-24 起；`h3` 結尾 `tools/h3_line_harvest.py` 聽寫比對）；要一字不差的片或句子設 `"fixed"` 改用 VoxCPM2 固定音軌。
- 角色參考音在定裝時（`make_film.py chars`）跟定妝圖一起做，定案後連同 `voice_sample` 存進 `films/角色/<角色>/ref_<代號>.wav`，之後每支片複製沿用、不重新設計：H3 每鏡拿同一個檔當音色參考，聲音才不會在片與片、鏡與鏡之間漂移。
- TTS 引擎只有 VoxCPM2（角色參考音、旁白、`fixed` 的台詞，`tools/voxcpm_batch.py`），挑音 `voice_pick.py`；VoxCPM2 不支援注音標記。
- 多音字、英文詞念錯：加進 repo 根目錄的讀音替換表 `tts-lexicon.md`（Markdown 表格，格式寫在檔頭）；只對某支片的放片子資料夾的同名檔，只有某句的寫 `film.json` 該句的 `"tts"`（同音字）。不要改字幕或劇本原文。
- 送進 TTS 的文字一律經 `tools/tts_lexicon.py`（`voxcpm_batch`、`gen_voice`、`voice_pick`、`recast` 已接），新寫的配音工具也要接；改 `tts-lexicon.md` 的格式時，media-video-specs 各範本的 `generate_narration.py` 要一起改。
- 讀音替換表**四個 repo 各一份、內容逐位元組相同**（media-video-specs、media-short-film、media-voice-clone、agent-speak/speak/；四個都公開，不能假設使用者每個都下載，各自要單獨可用）：**改表時四份一起改**，用 `tools/tts_lexicon.py --check` 檢查、`--sync` 把各份條目合併寫回四份（遇到同一個原文改寫不同、或表頭說明不一樣時不寫入）；同層時 `tts_lexicon.py` 會合併讀取，本 repo 的優先。只有某個引擎會念錯的條目四份照樣都加，說明欄註明引擎。
- 語音環境照 `AGENT_SETUP.md` §2b 自建（位置用 `AI_ROOT`／`PY_VOICE` 設定），不要拿其他專案的 venv 共用（例如 `media-voice-clone`）。
- 聽寫（ASR）一律經 `tools/stt.py` 的 `load_asr()`，不要直接 import `faster_whisper`：Windows on Arm 沒有 ctranslate2，靠它自動改用 openai-whisper。
- 工具要呼叫 venv 裡套件的命令列（例如 edge-tts）時，一律用 `[sys.executable, "-m", <模組>]`，不要靠 PATH 找執行檔：PATH 上可能是系統 Python 的舊版。
- 工具一律直接跑 repo 的 `tools/`（入口腳本預設就找它，`make_*.cmd` 用自己所在的資料夾），不要再複製到 `C:\AI\tools`；要改位置才設 `AI_TOOLS`。新寫的腳本找工具也要用相對 repo 的路徑，不要寫死 `C:\AI\tools`。

### ComfyUI
- 桌機用 Comfy Desktop 的 ComfyUI（`configs\profile.cmd` 自動偵測），連接、背景啟動、模型位置照全域技能 `comfyui`；不要另外在 `%AI_ROOT%\H3` 裝一份。
- 工具讀寫 ComfyUI 的 input／output 一律經 `tools/comfy_paths.py`，不要寫死 `COMFY_DIR\input`／`output`（Desktop 放在 `ComfyUI-Shared`）。
- 跑本專案前先關掉 Desktop 視窗，由 `tools\start_comfy.cmd` 在背景啟動，才會帶上 `--reserve-vram 1.5`。Desktop 自動更新後先跑 `smoke_test.py`，補裝的套件或 FlashVSR 節點不見了就照 `AGENT_SETUP.md` §2a 重裝。

### 兩台硬體
- 桌機：RTX 5060 Ti 16GB＋64GB RAM，用 `configs\profile.cmd`。筆電：RTX Spark（Windows on Arm、64GB 統一記憶體），用 `configs\profile_rtxspark.cmd`。
- 第二台桌機 PC-YI-FY 與桌機同規格（RTX 5060 Ti 16GB＋64GB RAM、Comfy Desktop），也用 `configs\profile.cmd`。
- 第三台 NB-YI（Ryzen 9 8940HX＋RTX 5060 Laptop，x64）沒有 profile：要在那台跑本機模型，先跑 `setup/detect_hardware.py` 再決定用哪份設定。
- 改 `setup/env/requirements_*.txt` 後要跑 `python setup/spark_check.py --wheels --emit` 重產 ARM64 清單，並看 diff 有沒有不合理的版本跳動。
- 判斷套件有沒有 ARM64 版不要只看 PyPI：NVIDIA 的套件（如 `nvidia-vfx`）在 PyPI 只放 wheel-stub 空殼，真正的 wheel 在 pypi.nvidia.com；也要核對 wheel 的 Python 版本（cpXY／abi3）。

### 做片
- 自己的片一律放 `films/<類型>/<片名>/`（類型例：數學家故事、換角重製、原創短劇、測試），用 `tools/new_film.py <類型> <片名>`（`short-film` 技能）從 `pipeline/template_local/` 建立，不要手動複製；`repo_dir` 是 `../../..`（`new_film.py` 會填）；`films/` 已列入 `.gitignore`，只走雲端硬碟、沒有 GitHub 備份。
- 《臭豆腐》與〈測試_H3灰模動作參考〉是搬來的舊作，不是用 `make_film.py`／`h3_shot.py` 做的，結構不照範本（成品在 `media/`）；重現《臭豆腐》用它自己的 `build_seg.py`，舊產生器 `ref2va.py` 封存在該片的 `legacy/`，不要搬進 `tools/`，新片一律用 `tools/h3_shot.py`。
- 頻道與角色的做片規則在 `films/AGENTS.md`（`films/CLAUDE.md` 橋接），只屬於某類影片的規則在 `films/<類型>/AGENTS.md`，角色資產在 `films/角色/`（各類型共用）；不要把這些寫進本檔或 `pipeline/`。
- 照參考影片換主角（保留動作、背景、聲音）照 `docs/08_換角重製.md`：片子資料夾寫 `recast.json`，用 `tools/recast.py`（首幀、配音、各鏡 spec、H3、剪接）；不要走 `make_film.py` 的 h3 階段（它不會把 `control` 傳給 H3）。
- 成片定案：自審完問使用者「可以成片嗎？」，說可以才把 `output/cut/film_1080p.mp4` 移到該片 `output/` 最上層、改名 `<片名>.mp4`（手機版 `<片名>_手機版.mp4`）並生成 `發布資訊.md`；之前都維持 `film_1080p.mp4`（細節見 `skills/short-film/references/review.md`）。
- 片尾是選用、預設不加：`film.json` 的 `ending.enabled` 為 true（或設 `ENDING=1`）才做片尾、接進成片。
- `films/AGENTS.md` 是從 `templates/AGENTS_TEMPLATE.md` 改寫的獨立檔：改了範本裡的通用規則，要手動同步過去。
- `skills/` 是技能原始檔，agent 不會直接從這裡載入；改完要說「同步技能」重裝全域副本。技能腳本要找 repo 的東西時放在 `tools/`，不要放進技能資料夾（全域副本不在 repo 裡）。

### 安全與隱私
- **不放個資與金鑰**：不 commit 真人照片、克隆聲音／參考音、API 金鑰（`.env`）、模型權重、成片影片。本 repo 為**公開** repo。
- **模型權重與 venv 只留本機**：照 `setup/downloads_*.json` 下載到 `AI_ROOT`（預設 `C:\AI`）／Comfy Desktop，不搬進 repo 或雲端硬碟；新增權重格式時加進 `.gitignore`。理由見 `docs/06_安裝.md` §1〈為什麼模型權重與 venv 不放進 repo〉。

## 同步層級（本專案初始化至第 3 層級）

| 層級 | 平台 | 位置 | 讀取時機 |
|------|------|------|---------|
| L1 | 本地（GDrive） | `AGENTS.md`＋`handoff.md`（不進 git，只走雲端硬碟）＋`CLAUDE.md`（橋接） | 每個 session |
| L2 | GitHub | changyiwu/media-short-film（公開） | 指定時 |
| L3 | Obsidian | media-short-film/專案工作流程.md | 有需要時 |

## 三個檔案的職責（依「時效性」分家，不是依「詳細程度」）

| 檔案 | 時效 | 寫入方式 | 放什麼 |
|------|------|---------|--------|
| `handoff.md` | **只對下一個 session 有效**，過期即丟 | 每次收工**整份重寫** | 做到哪、下一步、**這次**的暫時 workaround |
| `AGENTS.md`（本檔） | **長期有效**，每個 session 都適用 | 只有規則本身變了才改 | 目標、路線圖、常設規則、結構 |
| Obsidian（L3）／`git log` | **歷史**：發生過什麼、為什麼 | 只增不刪 | 決策紀錄、踩坑完整版、逐次進度 |

驗收標準：**`handoff.md` 整份刪掉，不應損失任何長期資訊**——會的話代表該升級進本檔卻沒升級。

**本檔不要出現的東西**（會無限膨脹，且開工每次都要重讀）：
- ❌ `## 最近進度`／逐次工作紀錄 → 有 L3 寫 Obsidian「🗓️ 最近更動紀錄」；沒有就靠 `git log`（所以 commit 訊息要寫「做什麼＋為什麼」）
- ❌ 決策記錄、取捨理由、踩坑經過的完整版 → Obsidian「決策紀錄」「🕳️ 踩坑筆記」
- ✅ 只留「結論式的規則」：踩過的坑收斂成一條**祈使句**寫進〈工作約定〉或〈專案專屬規則〉，理由那一大段留在 Obsidian

## 工作約定
- 任何 Agent、任何電腦：**開工先讀 `handoff.md`，收工必更新 `handoff.md`**
- `handoff.md` **不進 git**（含真實電腦名與本機絕對路徑），已列入 `.gitignore`，跨電腦靠雲端硬碟同步——不要把它加回版控
- 修改共用檔案前先讀最新內容，避免覆蓋其他 Agent 的變更
- 所有回應與文件使用繁體中文
- 修改前先確認計畫，優先保留原有資料結構
- agent 要寫一次性的批次腳本時改寫 PowerShell（`.ps1`，用 `pwsh -File` 跑），不要用 Write 寫 `.cmd`：寫出來是 LF＋UTF-8，路徑有中文時 cmd 會把整行讀壞。
- Windows 上 agent 用 Bash（Git Bash）改檔時，凡是字串裡有反斜線，一律先用 Write 把 Python 修改腳本寫成檔案再執行，不要用 heredoc 或 `python -c`（反斜線會被吃掉或變成控制字元，寫出壞掉的路徑）
- **產出一律放 `output/`**：每支片的產出放該片的 `films/<類型>/<片名>/output/`（工作檔在子資料夾，定案的 `<片名>.mp4`、`<片名>_手機版.mp4` 放 `output/` 最上層，一打開就找得到）；安裝驗證與範例的產出放各自旁邊的 `output/`（`setup/output/`、`pipeline/demo_local/output/`）。不另開 `out/`、`outputs/` 之類的資料夾；`output/` 不進 git。
