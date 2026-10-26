# 生成：跑 make_film.py

指令、每一步怎麼重做的完整說明在 `<repo>/pipeline/template_local/README.md`〈用法〉，**照那份做**；本檔只講節奏與關卡。

## 開跑前

- [ ] `film.json` 已照 `film-json.md` 自查過
- [ ] 生成前試映（`table-read.md`）使用者已說「通過」；`h3_shot.py` 的 `action` 字數警告看過
- [ ] 本機環境已裝好（`<repo>/AGENT_SETUP.md`）；顯卡跑不動 H3（顯存 < 15GB 或記憶體 < 30GB）時 h3／amb 會自動送 Colab（見 `<repo>/cloud/README.md`）
- [ ] ComfyUI 在線、queue 沒有別人的工作、顯存沒被 TTS／LLM 佔用；H3 不和別的 GPU 工作同時跑
- [ ] 跟使用者報過每一段的預估時間與費用（預設走 Image 2.5 API 會花錢；沒金鑰時改走 Codex CLI 扣 ChatGPT 訂閱、每張約 1 分半）

## 三段、三個人工關卡

| 段 | 指令（在 `output/<類型>/<片名>/`） | 關卡 |
|---|---|---|
| 1 | `"%PY_H3%" make_film.py chars masters frames` | **關卡 1**：看 `work/first/_sheet.jpg`——臉、服裝一致，沒有多手多腳，背景沒有字，窗戶方向對 |
| 2 | `make_film.py voices inserts h3`（`inserts` 只在有後製插入鏡時才有事做） | **關卡 2**：看 `work/review/clips_<鏡>.jpg`（後製插入鏡也有）——沒有換臉、多出人、鏡頭漂移、左右換位 |
| 3 | `make_film.py amb edl music ending cut review`（片尾預設不做：`ending.enabled` 為 true 或設 `ENDING=1` 才做） | **關卡 3**：自審（`review.md`）後，人一定要看完整的 `work/cut/film_1080p.mp4` |

- **每個關卡都停下來給使用者看**，等使用者說再往下。使用者說「我去睡了」＝授權自動做完並自審，早上交成片＋自審報告。
- 最難的一鏡先單獨跑（`set ONLY=<鏡號>`），過了再整批。
- 不滿意只重做那幾鏡：刪該鏡產出、在 `seeds` 換數字、`set ONLY=…` 重跑；認可過的鏡頭不重拍。
- 中斷後直接重跑同一段，已存在的檔案會跳過。
- `make_film.py` 生圖預設 Image 2.5 API 優先、Codex CLI 次之，不用另外呼叫 `draw`；看 log 的 `[backend]` 確認實際用哪個，規則見 repo 的 `AGENTS.md`〈生圖〉。

## 收件與紀錄

- 每階段做完回報產出、耗時與下一步；耗時分類記（準備／排隊／生成／QA／返工），不要只記總時間。
- 每次修正另存新版本，不覆寫已提交的成果。
- 在 `製作紀錄.md` 記：用了哪些 seed、退件原因、重做了哪幾鏡。
