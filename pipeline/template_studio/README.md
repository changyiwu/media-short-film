# template_studio：單人錄音室範本（一首歌 → 2.5–3 分鐘橫式錄音室唱歌影片）

古代人物穿原本的服裝，在現代錄音室對著麥克風唱一首華語流行歌，錄音室一鏡到底的感覺，只有一位主唱。`studio.json` 寫完整支（主唱、歌詞、錄音室、片名卡、每一鏡），`make_studio.py` 從生歌一路做到成片、手機版和自審。

改寫自 `pipeline/template_battle/make_battle.py`（2026-11-18）：拿掉 DJ、第二位饒舌手、換場、觀眾聲、對決特效與投票卡；加上候選歌比較（`pick`，每首做試聽影片）、定妝圖從 `output/角色/` 複製、錄音室母版、ASS 燒字幕（片名卡＋歌詞，選填英文）。

範例 `studio.json`＝〈別碰我的圓〉（阿基米德，16 句主副歌＋橋段＋尾段、30 鏡）。

類型規則（不沿用 THE FIRST TAKE 名稱、結尾自我揭穿殺句、傳說在說明欄標明）在 `output/錄音室/AGENTS.md`。

## 用法

1. `python tools/new_film.py 錄音室 <片名>` 建 `output/錄音室/<片名>/`（本範本的副本）。
2. 主唱要先在 `output/角色/<角色>/` 定好裝（`<code>_turn.png`、`_expr.png`、`_face.png`），`singer.char_dir`、`code`、`look`（照抄角色 README）填好。
3. 寫歌詞填進 `lyrics`，寫完跑 `tools/poly_check.py`（破音字），送去生歌的寫法用同音字修（`sing`），字幕用 `show` 或 `show_replace` 換回原字。
4. 在同一個 cmd 視窗（**生歌、拍片前先確認顯卡沒有被別的工作佔用**）：
   ```
   set PYTHONUTF8=1
   call <repo>\configs\profile.cmd
   <repo>\tools\start_comfy.cmd
   cd <repo>\output\錄音室\<片名>
   %PY_VOICE% make_studio.py music3            :: Music 3 抽 MUSIC3_SEEDS（預設 1,2,3,4）
   %PY_VOICE% make_studio.py yue               :: 要比較再跑：YuE2 抽 YUE_SEEDS（預設 1–6）
   %PY_VOICE% make_studio.py pick              :: 排序＋每首一支試聽影片 work/試聽/
   ```
   **人看著 `work/試聽/` 的影片聽完挑一首**，把 `work/gen/pick.json` 那首的 `file` 填進 `studio.json` 的 `song`。
5. `make_studio.py songs audio chars studio frames` → **人工關卡 1**：`work/scenes/studio.png`（背景布、麥克風、沒有人和字）、`work/first/_sheet.jpg`（每鏡首幀）。重畫：刪那張 png，那鏡加 `frame_seed_bump` 或改 `frame`，再跑 `frames`。
6. `make_studio.py specs h3` → **人工關卡 2**：`work/review/clips_*.jpg`。重拍：那鏡加 `seed_bump`（會切鏡的再加 `last_first: true`），再跑 `specs h3`。
7. `make_studio.py cut review srt` → **人工關卡 3**：看 `work/review/fc_v1/sheet_*.jpg`，**最後一定要人看完整成片** `work/cut/film_1080p.mp4`。改版：`--ver 2`（輸出 `film_v2_1080p.mp4`）。
8. 成片定案照專案規則：使用者說可以才把 `work/cut/film_1080p.mp4` 移到片子資料夾最上層改名 `<片名>.mp4`（手機版 `<片名>_手機版.mp4`），生成 `發布資訊.md`。

不給 stage 就從 `songs` 依序跑到 `srt`（生歌的 `lyrics music3 yue pick` 要手動跑）。已存在的輸出會跳過，中斷後重跑會接著做。還沒跑 H3 的鏡，`cut` 會用首幀靜態圖代替（沒有首幀就用灰底鏡號），可以先看節奏。

## 生歌

- 使用者有 Suno 就用 Suno（網頁貼 `work/songtext/music3_lyrics.txt` 的歌詞、自己寫風格），生好的檔放進 `work/gen/suno/` 一樣跑 `pick`。
- 沒有 Suno：本機 **MiniMax Music 3**（`gen_music3.py --tiled`，超過約 100 秒一定要 tiled）或 **YuE2**（`yue_song.py --cfg 1.3 --temp 0.85`）。換引擎前先問使用者。
- 歌詞送進模型前會經 `tools/song_lyrics.py`（繁轉簡＋讀音替換表），`work/songtext/` 裡的是繁體原稿。
- `pick` 的聽寫排序只是初篩：抒情歌拉長音，聽寫分數天生偏低；**一定要人聽**。看 `gaps`（人聲在唱、歌詞沒對到＝多唱一遍副歌）和 `duration`（太短可能少唱一段）。
- 唱錯一兩個字：同一首別處唱對的句子可以用饒舌範本的 `song_swap.py` 換（要複製過來、改讀 `align_S.json`，還沒實跑）；不然改 `sing` 的寫法重抽。

## studio.json 欄位

| 欄位 | 說明 |
|---|---|
| `title` | 片名 |
| `seed0` | H3 seed 的起點（每鏡再依鏡號加） |
| `song` | 定案的歌（相對片子資料夾），`pick` 之後人填 |
| `song_seconds` | 生歌長度上限（Music 3 `--seconds`、YuE2 `--secs`） |
| `bpm` | 抓拍子的先驗（慢歌要給，不然會抓成兩倍速） |
| `tail`、`fade` | 最後一個字唱完後留幾秒、最後幾秒淡出（預設 6、3） |
| `last_word_end`、`align_from` | 選填：最後一個字唱完的秒數（自動抓錯時）；對齊時把這秒數之前靜音（前奏有哼唱時） |
| `singer` | `name`、`code`（定妝檔名前綴）、`char_dir`（相對片子資料夾的角色資料夾）、`pronoun`、`look`（照抄角色 README）、`studio_wear`（耳機等錄音室穿戴，每張首幀加在 frame 後面）、`desc`（H3 短描述）、`perform`（唱歌鏡的表演句，接在 action 後面） |
| `studio` | `master`（錄音室空景提示詞）、`keep`（首幀鎖定句，`{ref}`＝母版圖號）、`light`、`setting`／`style`／`keep_h3`（H3 用） |
| `film_look`、`no_text` | 首幀電影感句、不要字的句子 |
| `title_card` | 片名卡：`series`（左上系列名）、`text`（歌名）、`sub`（主唱）、`sec`（出現到第幾秒；前奏比它短就在前面墊靜音）、`color`（ASS 的 &HBBGGRR） |
| `subs` | 歌詞字幕：`size`、`margin`、`color`、`english`（true＝每句的 `en` 當第二行） |
| `song_style` | `music3`（Music 3 caption：Genre／Vocal／Arrangement）、`yue`（YuE2 英文逗號標籤，語言放第一個、最後寫 BPM） |
| `show_replace` | `sing`→字幕的替換表（國字數字→阿拉伯數字、同音字→原字） |
| `lyrics` | `[{sec, lines: [{sing, show?, en?}]}]`，`sec` 含 verse／pre／chorus／bridge／outro／intro 會轉成對應段落標籤 |
| `locked` | 鏡頭鎖死不推近的鏡號 |
| `shots[]` | 每一鏡，見下表 |

每一鏡（`shots[]`）：

| 欄位 | 說明 |
|---|---|
| `id` | 鏡號 |
| `at` | 開始時間：秒數｜`["L", i]`（第 i 句開口前 0.12 秒，i 從 0 數；-1／-2＝第一句前 4／2.5 秒）｜`["L", i, 偏移秒]`｜`["mark", "first|last_end|music_end", 偏移秒]`。結束＝下一鏡開始，最後一鏡到片尾。超過 12 秒會警告 |
| `kind` | `sing`（對嘴人聲分軌）或 `silent`（閉嘴） |
| `dist` | `ECU`／`CU`／`MCU`／`MS`／`WIDE`；決定預設附哪幾張定妝（特寫：臉部近照＋表情表；中景以上：轉面圖＋臉部近照） |
| `sheets` | 選填，指定附哪幾張定妝：`turn`／`expr`／`face` 1–3 張 |
| `singer` | 預設 true；false＝空景（不附定妝、不檢查臉數） |
| `frame` | 首幀描述（英文，畫開口前的姿勢） |
| `action` | H3 動作（`Starting from <Picture 1>, …`，慢而清楚） |
| `camera` | 選填，預設三腳架極慢推近 |
| `still`、`calm`、`draft`、`cons`、`seed_bump`、`frame_seed_bump`、`last_first` | 首幀靜態慢推、慢動作、`false`＝14 步、額外限制句、換 H3 seed、換首幀 seed、尾幀＝首幀 |

## 輸出（`work/`）

`songtext/` 生歌文字、`gen/<引擎>/` 候選歌＋`pick.json`、`試聽/` 試聽影片、`song/` 分軌＋對齊（`align_S.json`）、`audio/`（`mix.wav`、`vocals.wav`、`timeline.json`）、`chars/`、`scenes/studio.png`、`first/`、`h3/<鏡>/`、`post/`（放大、片段、`subs.ass`）、`cut/`（`film_1080p.mp4`、`film_phone.mp4`、`film.srt`）、`review/`、`image_backends.json`（生圖實際用的後端，寫發布資訊用）、`timing.json`。

## 驗證紀錄

2026-11-18 寫成，只做過不用顯卡的乾跑（設定檔讀取、歌詞檔、鏡表時間換算、字幕檔），生歌、首幀、H3、剪接還沒實跑。
