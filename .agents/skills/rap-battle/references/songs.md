# 生歌、檢查、接法

## 先問：有沒有 Suno？

| 情況 | 用什麼 | 備註 |
|:--|:--|:--|
| 有 Suno 帳號 | **Suno**（網頁 Custom 模式，） | 編曲最豐富、rap 最有攻擊性、會自帶刷碟聲。四場對決都用它 |
| 沒有 Suno | 先問使用者 → **YuE2 14 版**（`make_battle.py yue`，配方 `templates/song_yue2_v14/`） | ComfyUI 原生節點；比 Suno 平、攻擊性弱；權重 CC BY-NC |
- YuE2 也不滿意 → ACE-Step 1.5（上游有，本專案未移植，要用先問使用者）。

不要自己從 Suno 換成 YuE2：換之前一定問。

## Suno

1. `make_battle.py songtext` → `work/songtext/suno_A_lyrics.txt`、`suno_A_style.txt`（B 同理）。
2. **網頁**：Create → Custom，Lyrics 貼歌詞、Styles 貼風格，每人各生一首（一次 2 版）。
3. 每人先抽 2 版，不滿意再改風格抽；挑好的放到 `song/A.mp3`、`song/B.mp3`。

### 風格寫法（英文，≤ 1000 字元）

依序寫：
1. 結構：`ONE CONTINUOUS RAP SONG by ONE rapper … EXACTLY 144 BPM`（有唱段就寫 `rap verse, then a short 4-line SUNG melodic hook, then back to rap`）。
2. 曲風＋招牌樂器（每場不同）：英國巴洛克 boom-bap＋大鍵琴、德國巴洛克 trap＋管風琴、G-funk＋里拉琴、爵士 boom-bap＋古琴洞簫、銅管進行曲 hard trap……
3. 前奏與收尾：A＝4 小節樂器前奏、`the beat STOPS DEAD on one huge hit (hard stop, no outro)`；B＝4 小節 DJ 刷碟前奏、`the LAST EIGHT LINES build gradually …（見第 6 點）… crowd roars 'OHHH' … rides out 4 bars with scratches`。
4. 聲音：`ONE SOLO MALE RAPPER only: a DEEP, RASPY baritone …` vs `a BRIGHT, SHARP young TENOR …`——**兩人一定要一低一高、個性不同**（每場還要跟前幾場不同，見下面〈人聲每場都要換〉）。
5. 咬字：`crystal-clear Mandarin rap with Taiwanese diction, every number clear`。
6. 殺招段：`The LAST EIGHT LINES build GRADUALLY at the same BPM, never faster: first two lines stripped back with no drums, a quiet restrained voice; then drums return; every two lines add one layer and the voice gets louder and higher; one beat of silence before the final line, which is the loudest moment of the song`（上游使用者 2026-11-01 要情緒慢慢堆）。**上游實測（〈瑜亮之戰〉16 版）：Suno 不太聽話**：長描述幾乎沒用；歌詞裡的短標籤 `[Breakdown: no drums, ...]`、`[Build-up: ...]`、`[Drop: shouted]` 約四分之一的版本會在殺句前真的空一拍，但人聲響度仍很平。做法：多抽，量伴奏有沒有收、殺句前有沒有空拍，挑有的給人聽。
7. negative：`slow ballad, mumble rap, autotune-heavy, female voice, choir, second rapper, duet, featuring, melisma, vocal runs, Indian scale`。

Suno 不吃藝人名字，要寫成特徵。範例見 `pipeline/template_battle/battle.json` 的 `suno_style`。

### 兩人聲音太像

- 兩人的聲音描述拉開（低沉沙啞 vs 明亮尖銳），兩首都生完用聲紋比對（`voice_diff.py`，CAM++，越低越像兩個人；0.7 左右可以接受）。
- 還是太像：Suno 的 persona（用某一版的聲音當角色）鎖住其中一人的聲音再生。

### 人聲每場都要換

上游每一場都寫「低沉 baritone vs 明亮 tenor」，聽起來都是同幾個人（上游使用者 2026-11-02：「不要老是用同類的幾個人聲」）。
- **開工先列前幾場寫過的聲音**，這場換不同類型：煙嗓氣音、尖鼻音嘲諷、懶散拖拍、老派、戲劇腔……同時換曲風，Suno 的聲音會跟著曲風走。
- **一個角色試 2–3 種聲音描述**，不要只抽同一段風格；negative 寫上不要的類型（`deep baritone, bright tenor`）。
- **選版前跑 `voice_diff.py 候選檔…`**（比對 `output/饒舌對決/` 前面各場的人聲分軌，列最像的 3 個和音高），分數只是輔助，最後要人聽。只取前 40 秒，比不出局部重唱段。

### 唱歪的字（Suno）

- **冷僻專有名詞（堯舜這類）Suno 每版都唱歪**（上游〈人性之辯〉10 版全唱成「老鑽／藥犯／老殘」）→ 寫歌詞時就先改常用字同音（字幕再換回）。
- 歌已定稿才發現：**Suno 局部重唱（replace-section）**，窗最短 10 秒、同音字當歌詞，抽幾版 → `resing_lines.py <A|B> 窗開始 窗結束 候選…` 逐句聽寫、量窗前後時間差，挑最清楚的 → `splice_resing.py` 整段連音樂接回定稿（接點自動搬到兩版都沒在唱的空隙）→ 重跑 `songs`、`lyric_audit.py`、`gap_check.py`，只重拍唱那句的對嘴鏡。窗外 Suno 會整段重生（窗後完全不同），不能整首換。上游用 Kie API 送件（`suno_replace.py`，付費），本分支沒移植，在 Suno 網頁的編輯器做。
- **局部重唱的三個坑**（上游〈Bravo 之戰〉20 多版）：①窗內放 `[Breakdown…]`、`[Melodic Hook…]` 這類標籤，Suno 會唱慢、句子往後掉 → 整窗只用 `[Verse]`，提示寫「每句剛好兩小節、不要放慢」；②窗從副歌接主歌的地方開始，Suno 常整窗不開口 → 標籤改 `[Rap Verse: vocals start immediately on the first beat, no pause]`；③同一個字抽 4 版都唱成別的（「到處講」→「出家」），換同音字沒用，改一個押同韻的詞（「到處張揚」）。
- 局部重唱**要在最終混音上聽寫**：分軌上聽寫對，混音裡可能還是錯（上游「傳」分軌是「賺」、混音是「穿」，換同音字「篆」再抽才過）。單字剪不乾淨就換整句，換到有對嘴的句子要重拍那一鏡。
- **副歌第二遍唱錯，用第一遍同一句整句蓋過去**（上游〈向日葵之戰〉2:53 第二遍把「世界就」唱成「看」，對齊分數還有 0.77）：週期用伴奏低頻量、搜尋範圍放寬、結果不能貼邊界；接點落在兩版同時無聲的換氣處；蓋完比兩遍的起音時間，差要 < 30 ms，再跑 `gap_check.py`。目前沒有工具，要手動做。
- **YuE2 換 seed 是另一首歌**（旋律、編曲都不同），不能拿來局部接；YuE2 唱錯就改 `sing` 的寫法重抽整首。

## YuE2（沒有 Suno 時）

一條指令（配方照 `templates/song_yue2_v14/README.md`）：
```
make_battle.py yue                           # songtext → 每人 YuE2 抽 YUE_SEEDS 首（預設 10）→ 只留目標 BPM、逐句聽寫排序 → 第一名放 song/
```
- 目標 BPM 讀 `yue_style` 裡的「144 BPM」（或填 `rappers.<A|B>.yue_bpm`）；約一半會跑掉，全掉就多抽（`YUE_SEEDS=11,12,…,20`）。
- 第一名只是聽寫初篩，**人聽過 `work/yue/<A|B>/` 的候選再定**；換歌就把那首轉檔覆蓋 `song/A.mp3`，刪掉 `work/song/sep/` 裡同名的分軌（分軌依檔名快取，不刪會沿用舊歌），再跑 `songs`。
- YuE2 沒有器樂前奏、刷碟不一定有：A 停在拍上→B 的接法照樣能用，但前奏很短時 DJ 口白會把音樂往後推（範本自動處理）。

## 檢查（`make_battle.py songs` 自動做）

- BS-RoFormer 分人聲 → 歌詞強制對齊（Qwen3-ForcedAligner）→ **逐句**聽寫（Qwen3-ASR）、BPM、最後一個字唱完的時間。
- 歌曲聽寫用 `stt.load_song_asr()`，不要用 Whisper：它在前奏和有配樂的段落會幻覺出「混音 李宗盛」之類的字，還會漏聽整句。
- 看低分句（< 0.5）是唱錯還是只是聽寫不準；Qwen3-ASR 也會把怪詞改成常見說法，**最後一定要人聽**。
- 對齊出來的段數跟歌詞句數不同＝歌詞跟送去生歌的不一樣，先修。
- 最後一個字的時間不對（Suno 自己在後面加喊聲）→ `rappers.<A|B>.last_word_end` 填秒數。
- 慢歌的 BPM 會抓成兩倍速 → `battle.json` 填 `bpm`（抓拍子的先驗）。
- 前奏有 Suno 自己加的喊話，把前幾句的對齊拉走 → `rappers.<A|B>.align_from` 填秒數（對齊時把這秒數之前靜音）。
- **整首對齊可能把幾句壓成 0.1 秒**（前奏長、某段含糊時；上游〈瑜亮之戰〉）：看 `work/song/align_*.json` 每句長度，太短的只取那段人聲重新對齊，同時更新 `words`，字幕韻腳才對得上。
- **Suno 常自己把副歌多唱一遍**：`songs` 會印「⚠ 人聲還在唱，但歌詞沒對到」→ 照實把那幾句補進歌詞（後面句子的編號跟著移）和字幕，並拍唱的人本人。**說「器樂段」前先看人聲分軌，不要憑對齊結果判斷**。
- **Suno 會在開口前自加「喔耶」長音**：對齊把它算進第一句，字幕會早出現 → 人聲分軌那段歸零，或在 `align_*.json` 那句加 `show_start`（字幕從真正開口的字開始）。
- **Suno 會多唱字，對齊不會告訴你**（上游「那把火**車**」「站在船上**想**看戲」）：`ok` 低於 0.3 的句子一定要查，不能當成氣音段聽寫不準。**對齊分數高也不代表字唱對**（「吵到你」唱成「好當你」分數 0.85）→ 定稿後跑 `lyric_audit.py`（每句人聲、混音各聽寫一次，拼音比），兩邊都對不上的字逐一單獨聽。

## 兩首怎麼接（`make_battle.py audio` 自動做）

1. A 整首：前奏改用伴奏分軌（拿掉 Suno 前奏裡含糊的喊話，免得跟 DJ 開場口白打架）。
2. A 最後一個字唱完後的**第一拍重拍收**：留 0.25 秒原音＋0.6 秒短衰減，**不淡出**。
3. **正好 1 小節後** B 那首的第一拍進來（B 自帶 DJ 刷碟前奏，換場口白壓在上面）。B 前奏塞不下口白時，1 小節空拍後多接整數小節的 B 伴奏再進歌，不留長靜音。
4. B 最後一個字後換伴奏分軌（Suno 常自己再唱），走到「最後一句的小節線＋8 小節」，最後 2 小節淡出；伴奏分軌的破洞用前一、兩小節同拍位補。
   - 最後一句後面有長音、Suno 自己收掉 → `rappers.B.end_on_hold: true`（唱到底就結束，不換伴奏分軌）。
   - 最後一個音跟音樂一起停、停一下再進器樂收尾 → `rappers.B.keep_stop: true`（人聲慢一點收，那個空檔不補）。
5. **殺句後不准突然切斷**（`tail_ring`，預設開）：A、B 最後一個字和收尾拍加殘響，`cut` 再墊全場歡呼；B 的前奏（或墊的 B 伴奏）淡入，不在 A 的殘響上突然進來。
6. DJ：開場口白在 1 秒開始（塞不下就整段音樂往後延）、換場口白在 B 開口前 1.2 秒講完、定論口白在 B 唱完 3.2 秒後、片尾口白在音樂結束後；口白期間音樂壓 −5 dB。定論口白下面墊 A 前奏裡最平穩的 2 小節循環（`verdict_bed`，預設開，−14 dB）。DJ 口白逐字對齊存 `work/voice/ming/dj_align.json`，字幕照實際念到的字出。
7. 兩人饒舌段調成一樣大聲；兩首 BPM 不同時 A→B 會接不準，盡量同 BPM（前四場三場 144、一場 94）。
8. 換了歌一定要重跑 `audio` 再跑 `specs`、`cut`（漏跑 `make_battle.py` 會停下來）。

**音量**：人聲分軌常混著音樂、伴奏分軌在 Suno 喊話處會挖空。不要只清人聲，要換就人聲連音樂整段換；不要自己鋪低音底（手機喇叭放不出來）；不要為了特效壓音樂。`review` 會先濾掉 300 Hz 以下再量音量破洞與突然掉音，成片和手機版另用 `level_scan.py` 量。

Suno 的 extend 生的「自然尾奏」接起來不好，不要用；需要收尾就寫進 B 歌詞的 `[Outro]`。
