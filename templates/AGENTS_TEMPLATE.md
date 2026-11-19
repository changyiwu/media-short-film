# <頻道名稱>：頻道規則

> 做片入口範本：`tools/new_film.py` 在 `output/AGENTS.md` 不存在時把本檔複製過去（並建一行 `@AGENTS.md` 的 `CLAUDE.md` 橋接），再改成自己的頻道規則。Codex、opencode 直接讀 `AGENTS.md`；Claude Code 讀 `output/` 底下的檔案時透過 `CLAUDE.md` 自動載入。
> 本資料夾已列入 repo 的 `.gitignore`：只走雲端硬碟同步，**沒有 GitHub 備份**。
> 本檔只放**屬於這個頻道**的規則（頻道名稱、角色禁則、工作習慣、已否決的做法）。做法上的規則不寫這裡：通用的在 repo 的 `docs/rules/`，某類影片的在 `kinds/<類型>/rules.md`；退件理由整理成規則時寫回那兩處（`output/` 不進 git，只寫在這裡別人拿不到）。每支片的進度與教訓寫在 `<類型>/<片名>/製作紀錄.md`。

## 專案簡介

<頻道名稱、主角、每月產量、片長、風格>

## 資料夾

```
output/
  AGENTS.md、CLAUDE.md   本檔＋橋接
  角色/<角色>/            轉面圖、表情表、臉部近照、README.md（鎖定的外觀描述）、參考音；各類型共用
  道具/<道具>/            持續出現的道具的多角度總覽＋細部特寫、README.md（鎖定的外觀描述）；各類型共用
  <類型>/                 影片類型（清單在 repo 的 kinds/kinds.json）
    AGENTS.md、CLAUDE.md  指向 repo 的 kinds/<類型>/rules.md（new_film.py 建）
    <片名>/               用 tools/new_film.py 建立
      <片名>.mp4（定案成片）  發布資訊.md  cover*.png  劇本.md  製作紀錄.md  <設定檔>  work/
```

開新片：說「開新片 <類型> <片名>」（`short-film` 技能），或在 repo 根目錄跑 `python tools/new_film.py <類型> <片名>`（`--list` 列出類型）。

## 必讀（開工前）

- 通用做片規則：`../docs/rules/`（先看 README，再讀這次會用到的主題）；自審：`../docs/04_自審清單.md`。
- 這類影片的規則：`../kinds/<類型>/rules.md`（Claude Code 讀 `output/<類型>/` 底下的檔案時會自動載入）。
- 生角色圖前讀 `角色/<角色>/README.md`，照抄鎖定的外觀描述；畫面裡持續出現的道具先到 `道具/` 找參考圖。
- 做片流程（訪談、劇本、預演、設定檔、製作、自審）：照 `short-film` 技能；饒舌對決照 `rap-battle` 技能；錄音室照 `pipeline/template_studio/README.md`。

## 頻道規則

- <頻道名稱、片頭片尾、系列名稱>
- <角色禁則：例如某角色不碰觸、不用手機>

## 工作習慣

- 多步驟工作開跑前，先報每一步的時間與費用。
- 啟動背景工作後，自己確認真的在跑（log、ComfyUI `/queue`、GPU 使用率）。
- 交片前自己照自審清單審過，不合格就重拍。
- 使用者說「我去睡了」＝授權自動做完並自審；早上交成片＋自審報告。
- 一幕一幕做，做完先給人看；認可過的鏡頭不重拍。
- 收工前：在該片 `製作紀錄.md` 補一段；退件理由整理成一條規則寫回 repo（通用的 `docs/rules/`、某類影片的 `kinds/<類型>/rules.md`），只有頻道自己的規則才寫本檔。
- 金鑰不印出、不寫進專案。

## 已否決的做法（不要再提）

| 做法 | 原因 |
|---|---|
| <例：EasyCache 當定稿> | <近景糊、靜止鏡雜訊> |
