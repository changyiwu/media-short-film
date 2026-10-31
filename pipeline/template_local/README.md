# template_local：全本地多鏡短片範本（做新片從這裡開始）

一個設定檔 `film.json` 寫完整支片（角色、場景、每一鏡、台詞、配樂、片尾），`make_film.py` 從角色定妝照一路做到成片和自審。生圖預設用 OpenAI 生圖（Image 2.5 API 金鑰優先、沒有金鑰才用 Codex CLI，失敗就停下，要用本機 Qwen 得整支片設 `IMAGE_BACKEND=local`），角色定妝是轉面圖＋表情表＋臉部近照、首幀依景別每個角色附 1–3 張（千問備選為單張半身）；配音用 VoxCPM2（送進 TTS 前套 repo 根目錄的讀音替換表 `tts-lexicon.md`）；其餘全部本機模型。片尾名單會依實際用到的生圖後端自動寫（記在 `work/image_backends.json`）。

範例 `film.json` 是〈被狗吃掉的作業〉：7 鏡、正片約 28 秒（片尾選用、預設不加；打開時再加 9.5 秒），開新片時整份換成自己的劇本。

## 用法

1. 在 repo 根目錄跑 `python tools/new_film.py <類型> <片名>`（或 `tools\new_film.cmd <類型> <片名>`），會把本範本的 `film.json`、`make_film.py`、`review.py` 複製成 `output/<類型>/<片名>/`，並建好 `劇本.md`、`製作紀錄.md`（`output/` 不進 repo）。如果手動複製到別的地方，請把 `film.json` 的 `repo_dir` 改成指向本 repo 根目錄（片尾範本在 `<repo>/templates/ending/`）。
2. 改 `film.json`（欄位說明見下一節）。劇本先照 `short-film` 技能寫好（需求訪談 → 劇本與鏡表），再把鏡表填進 `shots`（填寫規則見 `.agents/skills/short-film/references/film-json.md`）。
3. 在同一個 cmd 視窗執行：
   ```
   set PYTHONUTF8=1
   call <repo>\configs\profile.cmd
   <repo>\tools\start_comfy.cmd
   cd <repo>\output\<類型>\<片名>
   "%PY_H3%" make_film.py chars masters frames
   ```
4. **人工關卡 1**：看 `work/first/_sheet.jpg`（`frames` 結尾會提醒臉比角色多的鏡）。臉、服裝要一致，不能多手多腳，背景不能有字，窗戶方向要對。不滿意的鏡：刪 `work/first/<鏡>.png`，在 `film.json` 的 `seeds` 加 `"frame_<鏡>": 新數字`，或改該鏡的 `frame` 描述，再跑 `frames`。
5. `make_film.py voices inserts h3`（`inserts` 只在有後製插入鏡時才有事做）
   - 有句子 8 個候選都念錯時程式會停下來：以後也會遇到的詞加進 repo 根目錄的 `tts-lexicon.md`（只對這支片的，在片子資料夾放一份同名檔）；只有這句的就在該句加 `"tts"`，把念錯的字換成同音字（VoxCPM2 不支援注音）。刪掉 `work/voice/bv` 再跑 `voices`。
   - 單字喊叫這類 ASR 本來就聽不準的句子，人聽過沒問題就用 `set ALLOW_REVIEW=1` 繼續。
   - 上面兩條只適用 `fixed` 的句子與旁白。預設 `voice_mode` 為 `h3_ref`（H3 自己念）：角色參考音在 `chars` 已做好（或從 `output/角色/` 複製），`h3` 結尾自動分離人聲、聽寫、拼音比對原文，結果寫在 `work/voice_picks.json`（`heard`、`match`、`at`）。差太多會停下來：在 `seeds` 加 `"h3_<鏡>": 新數字`、刪 `work/h3/<鏡>/clip.mp4`，`set ONLY=<鏡>` 再跑 `h3`；抽 2–3 次都不對（常見：數字日期、H3 改用詞），在該句 `line` 加 `"voice_mode": "fixed"`，跑 `voices` 再重拍那一鏡。
6. **人工關卡 2**：看 `work/review/clips_<鏡>.jpg`（每鏡 6 格），檢查有沒有換臉、多出人、鏡頭漂移。不滿意就刪 `work/h3/<鏡>/clip.mp4`，在 `seeds` 加 `"h3_<鏡>": 新數字`，再跑 `set ONLY=S3 S5` → `make_film.py h3`。後製插入鏡也會出 `clips_<鏡>.jpg`；要改就刪 `work/insert/<鏡>.mp4` 再跑 `inserts`。
7. `make_film.py amb edl music ending cut review`
8. **人工關卡 3**：看 `work/review/` 的自審結果，最後**一定要人看完整的** `work/cut/film_1080p.mp4`。
   - 只改剪接（`cut_in`、`tail`）：跑 `edl cut review`。
   - 換配樂：改 `music.seeds`，刪 `work/music`，跑 `music cut review`。

不給 stage 就是全部依序跑。每一步已經存在的檔案都會跳過，所以中斷後重跑會從斷點接著做。

## film.json 欄位

| 欄位 | 說明 |
|---|---|
| `title` | 片名（片尾標題） |
| `repo_dir` | 本 repo 根目錄，相對於片的資料夾（放在 `output/<類型>/<片名>/` 是 `../../..`，`new_film.py` 會填；範本本身在 `pipeline/template_local/`，所以是 `../..`） |
| `cine` | 每張首幀開頭的電影感句（底片、鏡頭、光線、調色）。光線要寫具體，只寫 soft daylight 會變平淡白光 |
| `set_sentence` | 場景參考圖那句，`{n}` 會換成場景圖的編號（角色數＋1） |
| `frame_suffix` | 每張首幀結尾（不要字、不要浮水印…） |
| `voice_mode` | 台詞聲音：`"h3_ref"`（預設，2026-10-24 起）＝H3 拿角色參考音（`work/voice/ref_<角色>.wav`）自己念，嘴型和聲音一起生成、表演較生動，但會改用詞、讀音替換表無效；`"fixed"`＝VoxCPM2 配音當 H3 的固定音軌（數學名詞、數字日期這類要一字不差的片，或 H3 念錯抽不出來的句子）。單句可在 `line` 裡另設；旁白一律 `fixed`。移植自上游 2026-10-23，實測見 `docs/02` §5 |
| `voice_engine` | 旁白與 `fixed` 台詞的 TTS：`"ming"`（預設，2026-10-31 起，要先照 `AGENT_SETUP.md` §2d 安裝）或 `"voxcpm2"`。參考音設計都用 VoxCPM2 |
| `h3` | H3 共用設定：`style`、`setting`、`soundscape`（不寫台詞）、`camera`、`constraints`（每鏡都加的限制） |
| `chars.<代號>` | `name`（字幕顯示）、`look`（**完整外觀描述**，每張首幀都會照抄）、`voice_design`（VoxCPM2 設計聲音的描述）、`voice_sample`（設計聲音時念的句子）、`h3_voice`、`edge_voice`（挑音用的台灣國語答案卷聲音）、`sub_color`（字幕顏色，ASS 格式 `&H00BBGGRR`） |
| `narrator` | 旁白（選填，只有聲音）：`name`、`voice_design`、`voice_sample`、`edge_voice`、`sub_color`，跟角色同一套欄位但**不要 `look`、`h3_voice`**——不生定妝、不進 H3。代號固定是 `vo`（`chars` 不能再用這個代號）。字幕預設不加「名字：」，要加就設 `"sub_prefix": true` |
| `masters.<名稱>` | 場景母版（空景）提示詞。同一個場景的鏡頭都裁同一張母版，空間才一致 |
| `shots[]` | 每一鏡，見下表 |
| `seeds` | 想換的 seed：`char_<角色>`、`master_<名稱>`、`frame_<鏡>`、`h3_<鏡>`、`voice_<角色>` |
| `music` | `caption`（純器樂描述，寫明 Vocal: NONE）、`seeds`（抽幾首，挑人聲殘留最少的） |
| `mix` | `say_lead`（台詞比畫面提前幾秒，預設 0.2）、`default_tail`、`music_under_lines`（台詞期間配樂音量，0.15–0.30）、`music_bed_rms`、`target_lufs`、`voice_lufs`（每句台詞、旁白先調到同一個響度再混，範本預設 -20；不同聲音設計出來大小常差 10 dB 以上，不寫就照原音量。用 LUFS 不用 RMS：同 RMS 的低沉男聲聽起來比較小）、`amb_gain`（`amb` 環境音的音量倍數，預設 0.8）、`music_level`（選填，true＝配樂比自己典型音量大的段落壓回典型音量、不放大小聲處；Music 3 的前奏常比平均大 10 dB 以上，兩句之間會突然爆出來時用） |
| `ending` | 片尾（選用，預設不加）：`enabled`（預設 false；改 true，或設環境變數 `ENDING=1`，才做片尾並接進成片）、`closeups`（拿哪幾鏡的首幀當特寫）、`cards`（每張卡最多 3 行工具）、`card_dur`、`title_dur` |

每一鏡（`shots[]`）：

| 欄位 | 說明 |
|---|---|
| `id` | 鏡號 |
| `refs` | 畫面裡的角色代號（依序對應 `<image1>`、`<image2>`…）。**只放畫面裡要演戲的人**，有定義但不入鏡的角色 H3 會把他叫進畫面 |
| `sheets` | 首幀每個角色附哪幾張定妝（選填，預設 `["turn", "expr"]`）：`turn` 轉面圖、`expr` 表情表、`face` 臉部近照，挑 1–3 張。寫清單＝鏡裡所有角色共用，寫 `{"角色": [...]}`＝各自指定（沒寫到的角色用預設）。依景別挑法見 `docs/07` §0；千問備選（`IMAGE_BACKEND=local`）不看這欄。`frame` 裡的 `<imageN>` 照「第 N 個角色、最後一個是場景」寫，附幾張都不用改號，`frames` 會換成實際圖號 |
| `scene` | `[母版名稱, [x0, y0, x1, y1]]`：從母版裁哪一塊當場景參考（0–1 比例） |
| `dur` | 秒數（4–12）。有台詞時會自動延長到「開口時間＋台詞長度＋0.8 秒」；`h3_ref` 的台詞改用 max(3, 字數 ÷ 3＋2 秒) |
| `line` | `{"who", "text", "at"}`：誰說、字幕文字、第幾秒開口（`h3_ref` 時開口由 H3 決定，實際時間由聽寫抓）；`"voice_mode"`（選填）這句改用別的模式；`"tts"`（選填）是送給配音引擎的寫法（同音字；讀音替換表會再套在它上面）。沒台詞寫 `null`（H3 會收到靜音音軌，角色不會自己嘟囔） |
| `vo` | `{"text", "at", "tts"?}`：這一鏡的旁白（要先有 `narrator`）。配音、挑音、混音、字幕都跟 `line` 同一套，但**不放進 H3 的引導音軌**，畫面裡的人不會跟著動嘴（`action` 照樣寫他不說話）。同一鏡可以同時有 `line` 和 `vo`，時間不要重疊（自審第 5 遍會抓） |
| `insert` | 後製插入鏡（字卡、圖表動畫）：不生首幀、不走 H3 和放大，`inserts` 階段直接做 1080p 影片 `work/insert/<鏡>.mp4`。`{"image": "圖.png"}`＝靜態圖；`{"script": "inserts/x.py", "args": [...]}`＝用 `PY_H3` 跑片子資料夾裡的腳本，它會收到 `args` 再加 `--out <mp4> --dur <秒> --fps 24 --size 1920x1080`。這種鏡不用寫 `refs`、`scene`、`frame`、`action`；鏡長＝`dur`，有旁白就延長到念完＋0.8 秒，預設整段用完（`cut_out` 預設 `"full"`） |
| `overlay` | 後製疊字（片名、標示、說明），每項 `{"text", "start", "end", "pos", "size", "color", "font"}`：秒數從這一鏡在成片裡的開頭算（`end` 不寫＝到鏡尾），`pos` 是 `center`／`top`／`bottom`／`top-left`／`top-right`／`bottom-left`／`bottom-right`，`font` 是 `kai`（標楷）／`jh`／`jhbd`（預設）。畫面上要讀的字一律用這個後製，不交給生成模型 |
| `frame` | 首幀描述：景別、角色在哪、做什麼、表情、窗戶在畫面哪一邊 |
| `action` | H3 的動作描述（沒台詞的鏡頭寫明 He does not speak）。照官方結構寫 50–120 個英文字：「Starting from <Picture 1>, …」首幀定錨→動作開始→持續發展→結果（見 `docs/02` §5〈動作寫法〉） |
| `extra_constraints` | 這一鏡額外的限制 |
| `setting`、`soundscape` | 這一鏡的 H3 場景與環境音描述（選填，不寫就用 `h3.setting`、`h3.soundscape`）：換到別的地點的鏡頭才需要 |
| `amb`、`amb_seed` | `true`＝這鏡需要動作音效（翻書包、腳步）：另拍一支 H3 原生音效版，聽寫確認沒有人聲才取它的音軌；有人聲就換 `amb_seed` 或改用 `sfx/` 的音效 |
| `music_gain` | 這一鏡的配樂倍數（選填，預設 1）：乘在閃避人聲後的配樂音量上，前後平滑 0.5 秒。結尾只有字卡、沒有旁白時配樂太小聲就設大（例：10）；改完跑 `cut review` 即可 |
| `cut_in` | 剪掉鏡頭開頭幾秒（H3 常晚開口） |
| `cut_out` | `"full"`＝用到鏡尾；不寫＝台詞結束＋`tail` 秒 |
| `tail` | 台詞後留幾秒反應（喜劇停頓） |

## 輸出（`work/`）

`chars/` 定妝（`<角色>_turn.png`、`<角色>_expr.png`、`<角色>_face.png`；千問備選為 `<角色>.png`）、`masters/` 場景母版與每鏡裁切、`first/` 首幀與 `_sheet.jpg`、`voice/` 角色參考音、答案卷與 `bv/`（候選、`picks.json`、選中的台詞）、`h3/<鏡>/` 每鏡 spec、提示詞與 clip、`insert/` 後製插入鏡、`music/`、`ending/`、`post/`（`edl.json` 時間軸、放大片段、混音、字幕）、`cut/film_1080p.mp4` 成片＋手機版、`review/` 自審、`timing.json` 各階段時間。

## 耗時參考

本專案的桌機（RTX 5060 Ti 16GB）與 RTX Spark 筆電都還沒跑完整支範例片，實測後把各階段秒數（`work/timing.json`）寫進 `docs/hardware.md`／`docs/hardware_rtxspark.md`。

目前只有上游在 RTX 5090、配音用當時的另一套引擎、生圖用本機 Qwen 時的參考：範例片 7 鏡從零跑完約 29 分鐘（首幀 7 張約 10 分、H3 7 鏡 DMAD 約 7 分、配音 6 句約 4 分，其餘各 1–2 分），成片 −15.7 LUFS、峰值 −2.1 dBFS。
