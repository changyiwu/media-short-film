# 填 film.json（把鏡表變成製作設定）

欄位完整說明在 `<repo>/pipeline/template_local/README.md`〈film.json 欄位〉；技術規則的完整版與理由在 `<repo>/docs/03_規則與踩坑.md` §2–4。本檔只列**填寫時最常出錯、一定要照做**的事，不重抄那兩份。

## 開始前

- `output/<類型>/<片名>/需求確認.md` 與 `劇本.md`（含鏡表）都已經使用者確認。
- 每個角色的 `look`、`voice_design` **照抄** `output/角色/<角色>/README.md`，不要自己改寫外觀。
- 定妝已定：把 `<角色>_turn.png`、`<角色>_expr.png`（千問備選為 `<角色>.png`）複製到 `work/chars/`，`make_film.py` 看到檔案已存在就會沿用，不會重生。
- 有做預演的話，旁邊開著 `camera_plan_v<N>.json`：`visible`、`motion` 要跟這裡一致。

## 鏡表 → shots[]

| 鏡表欄位 | `shots[]` | 注意 |
|:---|:---|:---|
| 鏡號 | `id` | |
| 秒數 | `dur` | 4–12；有台詞會自動延長到夠念完 |
| 場景／景別 | `scene` | 同場景的鏡頭都裁**同一張母版**；景別、窗戶方向跨鏡一致 |
| 畫面裡的角色 | `refs` | **只放入鏡演戲的人**。寫了沒入鏡的角色 H3 會把他叫進畫面 |
| 首幀附哪幾張定妝 | `sheets` | `turn`／`expr`／`face` 挑 1–3 張（沒寫＝`turn`＋`expr`）：全身鏡不附 `face`，特寫 `["face", "expr"]`，雙人鏡每人少附；可寫 `{角色: [...]}` 各自指定（見 docs/07 §0） |
| 首幀畫面 | `frame` | 英文；景別、誰在哪、做什麼、表情、窗戶在哪一邊。`<imageN>`＝第 N 個 `refs` 角色，最後一號是場景，不管附幾張定妝 |
| 動作 | `action` | 英文；見下方〈逐鏡加註〉 |
| 台詞 | `line` | 沒台詞寫 `null`（給靜音音軌，角色才不會嘟囔） |
| 旁白 | `vo` | 要先在頂層寫 `narrator`（只有聲音，不生定妝）；見下方〈旁白、後製插入鏡、疊字〉 |
| 後製鏡（字卡、圖表動畫） | `insert` | 不寫 `refs`、`scene`、`frame`、`action` |
| 畫面文字（片名、標示） | `overlay` | 一律後製疊字 |
| 運鏡 | `camera`（選填） | 不寫就用 `h3.camera`（預設靜止三腳架）；見〈運鏡〉 |
| 額外限制 | `extra_constraints`（選填） | 這一鏡才需要的限制句 |

## 旁白、後製插入鏡、疊字

- **旁白**（`narrator`＋各鏡 `vo`）：聲音設計照抄需求確認的旁白描述；旁白不進 H3 引導音軌，所以畫面裡有人時 `action` 還是要寫他不說話（He does not speak）。角色台詞和旁白放同一鏡時，`at` 錯開、不要重疊。
- **後製插入鏡**（`insert`）：數字、圖表、字卡這種要逐字正確的畫面，不交給生成模型。繪製腳本放片子資料夾的 `inserts/`，它要吃 `--out --dur --fps --size` 四個參數（`make_film.py` 會自動加），最後留 1.5 秒左右停住讓人看。
- **疊字**（`overlay`）：片名、「人物與場景為想像重現」這類標示都用它，不要寫進 `frame` 叫模型畫。
- **某一鏡配樂調大**（`music_gain`，選填）：結尾只有字卡、沒旁白時配樂常小到聽不見，該鏡設倍數（例：10），改完跑 `cut review`。

## 誰在畫面裡（最常退件的來源）

- **單人鏡**：提示詞完全不提其他人；`refs` 只放那一人。需要時在 `extra_constraints` 加：
  `Only the <角色> is visible. The other remains outside the frame to the right. Exactly one visible person.`
- **多人同框**：寫 `Exactly N people`，並寫清楚左右：
  `Both must stay visible simultaneously, <A> LEFT and <B> RIGHT, throughout the complete shot.`
- **說話者在畫面外**：台詞照常給，`action` 寫明說話者 offscreen、畫面中的人嘴巴不動。
- 不要讓角色橫向走（H3 會跟拍、桌椅跟著滑），改原地轉身。

## 運鏡

- 預設靜止：`h3.camera` 與 `h3.constraints` 已有三腳架鎖定句（範例：`LOCKED-OFF STATIC CAMERA on a tripod`）。**靜止鏡不要在 `action` 裡寫推進、搖鏡**——自相矛盾是已記錄的踩坑。
- 只有真的要運鏡的鏡頭才在該鏡寫 `camera`；有做預演時，運鏡必須跟 `camera_plan` 的 `motion` 一致（`static`／`push`）。
- 空景、時鐘、桌面特寫：用靜圖＋慢推，不要讓 H3 自由發揮（會自己加人或切走）。

## 動作怎麼寫（`action`）

H3 照字面演，一句話的 `action` 動作只有官方結構的 1/2.7（完整說明與實測見 `<repo>/docs/02_端到端流程.md` §5〈動作寫法〉）：

- **50–120 個英文字**，照官方順序：`Starting from <Picture 1>, …` 首幀定錨 → 動作開始 → 持續發展 → 結果。
- 寫**哪個身體部位**動、**動多大**（until the arms are fully straight）、**做幾次**（again and again）；不寫 lively、exaggerated 這類抽象詞。
- 只是說話、點頭的鏡頭也照這個結構，寫到眉毛、嘴角、頭的轉向與點頭次數。
- 動作鏡的 `frame` 畫**動作開始前**的姿勢，不要畫在動作最高點；全身大動作（跳）首幀留頭頂空間。
- 大動作鏡、背景容易冒人的鏡，`action` 前先加 2–4 句首幀描述（構圖、人物外觀與位置、光線）。
- 少於 50 字時 `h3_shot.py` 會印 `WARN`，跑 `h3` 前看一下。

## 逐鏡加註（依實際問題加，不要每鏡都塞）

| 鏡頭類型 | 加在 `action` 或 `extra_constraints` |
|:---|:---|
| 動作要跟台詞同時發生 | 寫成「說到那個字的瞬間」做動作（例：stands up as he says …），否則慢半拍 |
| 道具不可舉起展示 | `hand quietly tucks paper below the crop, without raising or displaying it.` |
| 頭套、玩偶等實體道具 | `is a real sewn costume prop with rigid button eyes: no eyelids, no blinking or animal expressions. Only the real human face beneath it performs.` |
| 沒台詞 | `He does not speak.`（`line: null` 之外也寫進 `action`） |
| 長音 | 寫長音秒數＋「嘴維持張開到聲音結束」 |
| 畫面裡不能有字 | `frame_suffix` 已寫 No text；黑板、紙張再寫一次 blank |

## 對嘴的界線

- **台詞聲音二選一**（`voice_mode`）：`h3_ref`（預設，H3 拿角色參考音自己念，表演較生動；會改用詞、讀音替換表無效）或 `fixed`（VoxCPM2 配音當固定音軌；數學名詞、數字日期這類要一字不差的片或句子用它，整支片就在頂層寫 `"voice_mode": "fixed"`）。單句可在 `line` 加 `"voice_mode"` 覆寫；旁白一律 `fixed`。說明見 `<repo>/docs/02_端到端流程.md` §5。
- `h3_ref` 的台詞避開數字日期、難字、H3 容易換說法的詞；角色參考音（`voice_design`＋`voice_sample`）要是平常說話的語氣，要吼的戲另做一個兇的參考音角色。
- `h3_ref` 跑完 `h3` 後，看 `work/voice_picks.json` 每句的 `heard` 跟 `text` 對一遍：程式只擋明顯念錯（拼音相似度 < 0.7），小幅改詞（「也正好」→「也剛剛好」約 0.77）和聲調錯不會擋；自審第 2 遍（門檻 0.8）會再列出改詞。
- **配音先定稿**（`fixed`），H3 用同一份音訊當引導；不要事後換聲音掩蓋不同步。
- **長靜默**（說話 → 停頓 → 再說話）最容易露餡：盡量拆成兩鏡；拆不了就在 `action` 寫明靜默時段嘴巴閉上。
- 不用嘴／眼 XY 平移貼片修表演；未做逐音素量測就照實寫「未做逐音素認證」，不寫「完美對嘴」。

## 填完自查

- [ ] 每鏡 `refs` 只有入鏡演戲的人，單人鏡沒有提到其他人
- [ ] 每鏡 `action` 50–120 字、照「Starting from <Picture 1> → 開始 → 發展 → 結果」寫；動作鏡的 `frame` 畫動作開始前
- [ ] 靜止鏡的 `action` 沒有寫運鏡；有運鏡的鏡頭跟預演契約一致
- [ ] 沒台詞的鏡頭 `line: null` 且 `action` 寫明不說話
- [ ] 同場景各鏡的母版、景別、窗戶方向一致
- [ ] `look` 是照抄角色 README，不是改寫
- [ ] 片尾是選用、預設不加（`ending.enabled` 預設 false；要加改 true 或設 `ENDING=1`）；有片尾時，`ending.cards` 的生圖工具名稱符合實際用的後端（`make_film.py` 依 `work/image_backends.json` 自動寫；有手動放進去的圖要再核對）
