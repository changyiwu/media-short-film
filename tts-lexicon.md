# 讀音替換表

送進 TTS 之前，把「原文」換成 TTS 念得對的「改寫」。只改送進 TTS 的文字，字幕、劇本、畫面上的字照常寫正確用字。

## 這份表有四份，內容完全相同

下面四個 repo 各帶一份。四個都是公開的，不能假設使用者每個都下載，所以**每份都要完整、單獨可用**：

| repo | 位置 | 用在 |
|------|------|------|
| [media-video-specs](https://github.com/changyiwu/media-video-specs) | 根目錄 | 02／03 範本的 `generate_narration.py`（Edge-TTS／Kokoro 旁白） |
| [media-short-film](https://github.com/changyiwu/media-short-film) | 根目錄 | `tools/tts_lexicon.py`：VoxCPM2 台詞、edge-tts 答案卷、挑音聽寫比對 |
| [media-voice-clone](https://github.com/changyiwu/media-voice-clone) | 根目錄 | `tts_lexicon.py`：`clone.py`、`dialogue.py`（VoxCPM2 克隆） |
| [agent-speak](https://github.com/changyiwu/agent-speak) | `speak/` | speak 技能（Edge-TTS 語音回覆；裝成全域技能時跟著複製） |

- **改表時四份一起改**，內容維持逐位元組相同。四個 repo 放在同一層時，用 `python media-short-film/tools/tts_lexicon.py --check` 檢查四份是否一致，`--sync` 把各份的條目合併後寫回四份。
- 四個 repo 放在同一層時，每個程式都會把找得到的其他份一起讀（合併），同一個原文以自己那份為準。所以本機漏同步時自己出片察覺不到，但只下載其中一個 repo 的人就會缺那條。

## 規則

- Edge-TTS 不能用 SSML 指定讀音（`<phoneme>` 無效），VoxCPM2 不支援注音標記，多音字、英文詞念錯只能靠改字。
- 每列一條：`| 原文 | 改寫 | 說明 |`。說明寫正確讀音、出處（哪個 repo、哪支片、哪個引擎）、是否已人耳確認。
- 長的原文先換；同一段文字只換一次，換過的結果不會再被其他條目換。
- 改寫盡量用**同音字**或**補字**（奇數 → 基數、十一少一 → 十一少了一），不要換成意思不同、字數差很多的說法：media-short-film 挑音會拿改寫後的文字比對聽寫。條目寫得越具體越安全，避免誤換其他詞。
- 只有某個引擎會念錯的條目，四份照樣都加，說明欄註明引擎（同音字換給別的引擎念通常也對）。
- 內容有 `|` 時寫成 `\|`；要讓前後空白看得出來，可以用反引號包起來（`` `GPT four` ``）。
- 只對某支片生效的條目，在那支片的資料夾放一份同名的 `tts-lexicon.md`（同樣的表格格式），同一個原文以近的為準。
- 找表順序（近的覆蓋遠的）：同層其他三個 repo 的表 → 自己這份（設了環境變數 `TTS_LEXICON` 就改讀它指的表）→ 工作資料夾往上每一層的同名檔。
- 新增條目後要重生那幾句並實際聽過：改字會改變旁白長度與逐詞時間。media-video-specs 照 GOTCHAS H-4／H-5 處理；media-short-film 已挑好的句子不會自動重挑，要刪掉該片 `output/voice/bv` 裡那句的候選再跑 `voices`。

## 替換表

| 原文 | 改寫 | 說明 |
|---|---|---|
| 奇數 | 基數 | 奇讀 jī（1 聲），Edge-TTS 會念成 qí（media-video-specs 倍數判別法影片，2026-10，已人耳確認） |
| 十一少一 | 十一少了一 | 少讀 shǎo（3 聲），「十比十一少一」會念成 shào（media-video-specs 倍數判別法影片，2026-10，已人耳確認） |
| 八加四乘三 | 八加四乘以三 | 乘讀 chéng，句首「八加四乘三」的「四乘」被念成古文的 sì shèng（media-video-specs 四則運算規則複習影片第 2 頁，Edge-TTS HsiaoChen +35%，2026-10，已人耳確認；同片第 5 頁同一句未回報念錯） |
| GPT-4 | GPT four | 英文型號的數字用英文念（media-video-specs 03 範本，尚未重生旁白試聽） |
