# AI 影片工作流（專案藍圖）

> 本檔為跨 Agent 通用的專案藍圖（AGENTS.md 開放標準）。任何 Agent 的每個 session 都應先讀本檔＋`handoff.md`。
> Claude Code 預設只在沒有 `CLAUDE.md` 時才讀 `AGENTS.md`，故由 `CLAUDE.md` 的 `@AGENTS.md` import 本檔（`CLAUDE.md` 只有這一行）；Claude 專屬規範寫在本檔〈Claude Code 專屬〉一節。

## 專案簡介
在 16GB VRAM＋64GB RAM 的本機，用開源模型（MiniMax H3、Qwen-Image 2.1／Edit、VoxCPM2、Ming-3.0-TTS、MiniMax Music 3）製作 1–3 分鐘、16:9、24fps 的原創 AI 短片。改作自 [mathruffian-dot/shanshiba-workflow-16gvram-64gram](https://github.com/mathruffian-dot/shanshiba-workflow-16gvram-64gram)，來源與修改內容見 `NOTICE.md`。

## 關鍵時程

- 2026-10-25：從 `media-music-video`（原 `media-comfyui-studio`）搬入古裝庭院惡搞短片《臭豆腐》（`output/原創短劇/臭豆腐/`）與 H3 灰模動作參考測試（`output/測試/測試_H3灰模動作參考/`，瘦身後只留筆記、參考片產生腳本與對照圖）

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
- [x] 階段三之二：RTX Spark 筆電上機驗證（照 `docs/hardware_rtxspark.md`「第一次上機」，結果回填該文件；`run_demo.py` 因缺 Qwen-Image-Edit 未跑）
- [x] 階段四：建立第一個角色（`output/角色/`），用 `short-film` 技能（`tools/new_film.py`）做第一支片
  - [x] 角色「狗狗」（`output/角色/狗狗/`）＋第一支片〈狗熊哆嗦毛_狗狗版〉（換角重製，`docs/08`）
- [ ] 階段五：換角重製工具化與其他版本
  - [x] 把首幀換角、各鏡 spec／骨架切段、剪接收尾的一次性腳本整理成 `tools/recast.py`（片子資料夾放 `recast.json`）
  - [x] 舞蹈鏡嘴型：聽寫寫台詞＋閉嘴首幀＋換 seed（`docs/08`〈有發聲的骨架鏡〉）
  - [ ] 〈狗熊哆嗦毛〉台灣黑熊、貓貓版（「台灣黑熊」比「狗熊」多兩字，開頭鏡要拉長）
- [ ] 階段六：劇本導向教學片（`output/數學故事/`）
  - [x] `output/` 依影片類型分資料夾（`output/<類型>/<片名>/`，類型規則 2026-11-19 起在 `kinds/<類型>/rules.md`）
  - [x] `make_film.py` 範本支援旁白（`narrator`＋`vo`）、後製插入鏡（`insert`）、疊字（`overlay`）、每鏡 `setting`／`soundscape`、統一人聲響度（`mix.voice_lufs`）
  - [x] 角色「埃拉托賽尼」＋〈埃拉托賽尼的篩子〉（1.5 分鐘課堂引起動機）成片 99 秒
  - [x] 〈埃拉托賽尼的篩子〉人聲音量確認，存為範本 `film.json` 的預設混音
  - [x] 〈埃拉托賽尼的篩子〉發布資訊（YouTube＋Facebook，`output/數學故事/埃拉托賽尼的篩子/發布資訊.md`）
  - [x] `pron_check.py` 的「不」「一」一律記本調、變調交給 `sur`（「不是」「不適」不再判成不同聲調）
  - [x] 配樂維持 14 段，乾淨的都不夠長時交叉淡入自動接長（多寫段數會讓 Music 3 唱歌）
  - [x] `.gitattributes` 讓 `*.cmd`／`*.bat` 簽出成 CRLF
  - [x] 角色「歐幾里得」＋〈歐幾里得的完美數〉（課本 88 頁〈完美數〉，依史料改主角為歐幾里得）成片 100 秒＋發布資訊
  - [x] 挑音加響度與嘶聲篩選、配音混音前濾波與真峰值把關；`breezyvoice_pick.py` 改名 `voice_pick.py`
  - [x] 角色「劉徽」＋〈劉徽的紅黑算籌〉（康軒 7 上 1-2〈整數的加減〉〈數學史：算籌〉）成片 101 秒＋發布資訊
  - [x] 每鏡配樂倍數（`music_gain`）併進範本
  - [x] 移除選用配音引擎 BreezyVoice／Breeze TTS 2；讀音替換表從 media-video-specs 移植成兩專案共用的 `tts-lexicon.md`
  - [x] 旁白與 `fixed` 台詞預設引擎改 Ming-3.0-TTS（`voice_engine`，參考音設計維持 VoxCPM2）
  - [x] 角色「丟番圖」＋〈丟番圖的墓誌銘〉（康軒 7 上 3-3〈應用問題〉備課 p.219）成片 130 秒＋發布資訊
  - [x] 角色「畢達哥拉斯」＋〈畢達哥拉斯的三個正方形〉（康軒 8 上 2-3〈畢氏定理〉p.94～97）成片 138 秒＋發布資訊＋封面
  - [x] 旁白參考音改成系列共用（`output/角色/旁白/ref_vo.wav`，範本 `voices` 自動沿用）；挑音加嗡嗡聲檢查（`tools/tone_check.py`）；配樂低通 9 kHz
  - [x] 旁白聲音庫（`output/角色/旁白/voices.json`）：預設改「雅文」（溫暖熟齡女聲），原本的改名「小晴」留作候選，`narrator.voice` 選聲音
  - [ ] 旁白聲音庫加男聲

- [ ] 階段七：饒舌對決（`pipeline/template_battle/`、`rap-battle` 技能）
  - [x] 範本與技能移植，〈微積分之戰〉跑到歌曲比較
  - [x] 歌詞送模型前繁轉簡（`tools/song_lyrics.py`）、歌曲聽寫改 Qwen3-ASR
  - [x] 比較 Qwen3-ForcedAligner 與 stable-ts，`make_battle.py`、`pick_song.py` 改用 Qwen（`stt.load_song_aligner()`）
  - [x] 〈微積分之戰〉定案 YuE2 歌，跑完 `songs dj audio`（影像階段不做：測試片，題材已有人做過）
  - [x] 補移植上游到 `3aec3d1` 的對決音訊修正（殺句殘響、定論墊底、DJ 逐字字幕、聲音自動檢查）、自審與修歌工具、自審清單 H 節
  - [ ] 選新主題跑完整流程（`chars` 之後的階段還沒實跑）

- [ ] 階段八：錄音室唱歌片（`pipeline/template_studio/`，古代人物在現代錄音室唱華語流行歌）
  - [x] 單人錄音室範本 `make_studio.py`＋`studio.json`（改寫自饒舌範本），`new_film.py` 新增「錄音室」類型
  - [x] 〈別碰我的圓〉（阿基米德）成片 167 秒＋發布資訊＋封面；新增直排片名卡、片尾曲目卡、牙齒自審 `tools/teeth_sheet.py`
  - [x] 〈別碰我的圓〉第 2 版定案（第一鏡空景＋走進來）＋Shorts（裁 9:16、67 秒、`work/shorts/make_shorts.py`）

- [x] 規則總整理：通用規則 `docs/rules/`、類型 `kinds/`（`new_film.py` 讀 `kinds.json`）、H3 步數共用 `tools/h3_steps.py`；踩坑經過搬到 Obsidian

## 資料夾結構
```
README.md / AGENT_SETUP.md     專案說明、給 agent 的安裝手冊
NOTICE.md                      來源與作者、本分支修改清單（必須保留）
LICENSE / LICENSE-docs.md      MIT（程式）／CC BY-NC 4.0（文件素材）
THIRD_PARTY_NOTICES.md         第三方模型與工具授權
tts-lexicon.md                 讀音替換表（多音字、英文詞 → TTS 念得對的寫法；五個 repo 各一份、內容相同，同層時合併讀取）
docs/                          總覽、端到端流程、rules/（通用做片規則）、自審清單、安裝、角色與首幀、換角重製、硬體說明
kinds/                         影片類型：kinds.json（類型清單，new_film.py 讀）＋<類型>/rules.md（類型規則）
tools/                         全域工具（各腳本直接用這裡，不再複製到 C:\AI\tools）
output/                         自己的片與角色資產（.gitignore，不進 repo；規則見 output/AGENTS.md）
pipeline/                      template_local（新片範本）、template_battle（饒舌對決範本）、template_studio（單人錄音室唱歌範本）、demo_local（安裝驗證）
setup/                         模型下載清單、套件清單、check_env（只讀環境核對）、smoke_test、硬體偵測、16GB 模擬測試
cloud/                         H3 送 Google Colab 跑
sfx/                           Freesound CC0 音效
templates/                     片尾範本、法陣素材、AGENTS_TEMPLATE.md（頻道規則範本）、發布資訊範本.md（YouTube／FB／IG／Threads；五個媒體專案各一份、內容逐位元組相同，正本在 media-youtube-publish 的 `skills/youtube-long/references/`，改正本再整份覆蓋，不在本專案就地改）
.agents/skills/                專案層級技能：short-film（做片全流程：開新片、訪談、編劇、預演、製作、自審）、rap-battle（饒舌對決）；不裝全域，見〈技能路由〉
configs/profile.cmd            桌機（16GB VRAM＋64GB RAM）環境變數
configs/profile_rtxspark.cmd   RTX Spark 筆電（Windows on Arm＋64GB 統一記憶體）環境變數
setup/spark_check.py、setup/env/arm64/   RTX Spark 相容性檢查與 ARM64 套件清單
```

## 專案專屬規則

### 規則在哪裡（做片前先讀）

| 層 | 位置 | 內容 |
|---|---|---|
| 專案 | 本檔 | 授權、環境、安全、資料夾結構、規則索引 |
| 通用做片規則 | `docs/rules/`（先看 `README.md`） | 劇本、構圖與角色、道具、H3、配音、配樂與音效、後製與發布、環境；每條一句做法＋一行理由 |
| 類型規則 | `kinds/<類型>/rules.md`，清單 `kinds/kinds.json` | 只屬於某類影片的規則；`output/<類型>/CLAUDE.md` 直接載入 |
| 頻道規則 | `output/AGENTS.md`（不進 git） | 頻道名稱、角色禁則、工作習慣、已否決的做法 |
| 自審 | `docs/04_自審清單.md` | 交片前逐項檢查 |

- 同一條規則只寫在一個地方，其他文件連過去、不抄；範本程式的預設值要跟規則一致（例：H3 步數由 `tools/h3_steps.py` 統一判斷，三個範本都呼叫它）。
- **做片得到的經驗一律寫回 repo**（`output/` 不進 git，本 repo 公開）：通用的寫 `docs/rules/` 對應的檔、做法細節寫對應的 `docs/`（道具參考圖在 `docs/07` §6），只屬於某類影片的寫 `kinds/<類型>/rules.md`，範本專屬的用法寫該範本的 `README.md`；實測數字與退件經過寫 Obsidian（L3）的〈規則踩坑紀錄〉，repo 只留結論。寫回時不放個人資訊，跟既有規則衝突就改掉舊的、不兩條並存。

### 授權與來源
- **僅限非商業用途**：文件素材為 CC BY-NC 4.0；Qwen-Image 2.1 只能非商用。要營利前先照 `THIRD_PARTY_NOTICES.md` 替換模型。
- **必須保留來源標示**：`LICENSE`、`LICENSE-docs.md`、`THIRD_PARTY_NOTICES.md`、`NOTICE.md`、`.agents/skills/short-film/NOTICE.md`、`.agents/skills/short-film/LICENSE-AI-drama-pound.txt` 不可刪除或移除原作者署名；修改上游文件時在 `NOTICE.md` 的修改清單補一筆。

### 兩台硬體
- 桌機：RTX 5060 Ti 16GB＋64GB RAM，用 `configs\profile.cmd`。筆電：RTX Spark（Windows on Arm、64GB 統一記憶體），用 `configs\profile_rtxspark.cmd`。
- 第二台桌機 PC-YI-FY 與桌機同規格（RTX 5060 Ti 16GB＋64GB RAM、Comfy Desktop），也用 `configs\profile.cmd`。
- 改 `setup/env/requirements_*.txt` 後要跑 `python setup/spark_check.py --wheels --emit` 重產 ARM64 清單，並看 diff 有沒有不合理的版本跳動。
- RTX Spark 的語音／Ming venv 換 NVIDIA win_arm64 nightly（20261107 起）後，site-packages 要有 `torch-lib-path.pth`（把 `torch\lib` 加進 PATH，寫法同 media-voice-clone 的 `install.ps1`），否則 cuDNN 一用到卷積就直接退出；換版後驗證要跑一次 cuDNN 卷積，不能只測矩陣乘法。
- 判斷套件有沒有 ARM64 版不要只看 PyPI：NVIDIA 的套件（如 `nvidia-vfx`）在 PyPI 只放 wheel-stub 空殼，真正的 wheel 在 pypi.nvidia.com；也要核對 wheel 的 Python 版本（cpXY／abi3）。

### 做片
- 自己的片一律放 `output/<類型>/<片名>/`，用 `tools/new_film.py <類型> <片名>`（`--list` 列出類型；`short-film` 技能）照 `kinds/kinds.json` 從對應的範本建立，不要手動複製；新類型先建 `kinds/<類型>/rules.md` 並在 `kinds.json` 加一行（`kinds/README.md`）。`output/` 已列入 `.gitignore`，只走雲端硬碟、沒有 GitHub 備份。
- 已做好的片各有自己的 `make_film.py`／`make_battle.py`／`make_studio.py` 副本，範本更新不會自動帶到舊片。
- 《臭豆腐》與〈測試_H3灰模動作參考〉是搬來的舊作，結構不照範本（成品在 `media/`）；重現《臭豆腐》用它自己的 `build_seg.py`，舊產生器 `ref2va.py` 封存在該片的 `legacy/`，不要搬進 `tools/`。
- 成片定案、發布資訊、封面照 `docs/rules/後製與發布.md`〈定案與發布〉：使用者說「可以成片」才把 `work/cut/film_1080p.mp4` 移到片子資料夾最上層改名 `<片名>.mp4`。
- 持續出現的道具跟角色一樣放 `output/道具/<道具>/`，做法照 `docs/07` §6。
- `output/AGENTS.md` 是從 `templates/AGENTS_TEMPLATE.md` 改寫的獨立檔：改了範本，要手動同步過去。
- 技能只放專案的 `.agents/skills/`，不用 skill-sync 裝到任何 agent 的全域目錄，也不另建 `.claude/skills/` 副本或符號連結（雲端硬碟不同步符號連結）；改完直接生效。技能要用的腳本照舊放 `tools/`，SKILL.md 從當前目錄往上找 repo 根。

## 技能路由（四個 Agent 共用）

本專案技能**只放在專案內的 `.agents/skills/`**。Codex、OpenCode、Antigravity 會自動載入；Claude Code 不讀 `.agents/skills/`，遇到下列情境時**先讀對應的 SKILL.md 再照做**（其他 Agent 沒自動觸發時也照此表）：

| 情境 | 讀取 |
|------|------|
| 開新片、需求訪談、寫劇本與鏡表、改台詞、審劇本、拆鏡頭、預演與布置圖、填 `film.json`、跑 `make_film.py`、自審成片、成片定案 | `.agents/skills/short-film/SKILL.md` |
| 饒舌對決、rap battle、人物用 rap 對嗆、寫對決歌詞、跑 `make_battle.py` | `.agents/skills/rap-battle/SKILL.md` |

### 安全與隱私
- **金鑰由使用者自己設定**（`OPENAI_API_KEY`／`OPENAI_KEY_FILE`／`~/.openai.env`），agent 不經手、不讀出內容、不寫進 repo。
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
- **產出一律放 `output/`**：每支片整個資料夾就在 `output/<類型>/<片名>/`：定案的 `<片名>.mp4`、`<片名>_手機版.mp4` 放片子資料夾最上層（一打開就找得到），工作檔放片內的 `work/`，手動跑的 log 放 `work/log/`，舊稿、舊程式放 `舊版/`；安裝驗證與範例的產出放各自旁邊的 `output/`（`setup/output/`、`pipeline/demo_local/output/`）。不另開 `out/`、`outputs/` 之類的資料夾；`output/` 不進 git。
