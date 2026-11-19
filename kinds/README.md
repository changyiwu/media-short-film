# 影片類型

每個類型一個資料夾，`rules.md` 只寫**這類影片**跟通用規則（[../docs/rules/](../docs/rules/README.md)）不同或額外的規則；清單在 [kinds.json](kinds.json)，`tools/new_film.py <類型> <片名>` 照它建片。

| 類型 | 範本 | 技能 |
|---|---|---|
| [數學故事](數學故事/rules.md) | `pipeline/template_local/` | `short-film` |
| [原創短劇](原創短劇/rules.md) | `pipeline/template_local/` | `short-film` |
| [換角重製](換角重製/rules.md) | `pipeline/template_local/`＋`tools/recast.py` | `short-film` |
| [饒舌對決](饒舌對決/rules.md) | `pipeline/template_battle/` | `rap-battle` |
| [錄音室](錄音室/rules.md) | `pipeline/template_studio/` | （範本 README） |
| [測試](測試/rules.md) | `pipeline/template_local/` | 沙盒，不發布 |

## 加新類型

1. 建 `kinds/<類型>/rules.md`（照下面的格式；還沒有規則就寫「還沒有本類型專屬的規則」）。
2. 在 `kinds.json` 加一行：

   | 欄位 | 說明 |
   |---|---|
   | `desc` | 一句話說明 |
   | `template` | 用 `pipeline/` 底下哪個範本 |
   | `config` | 範本的設定檔（`film.json`／`battle.json`／`studio.json`），建片時把 `title` 換成片名 |
   | `copy` | 要複製的檔案；`*.py` 表示範本資料夾裡全部 Python 檔 |
   | `script` | 建一個空白的 `<script>.md`（劇本、歌詞）；`null` 不建 |
   | `skill`、`next` | 建好後提示用哪個技能、下一步做什麼 |
   | `sandbox` | `true`＝實驗用，不發布 |

3. 需要新範本時另外在 `pipeline/` 建，範本程式的 H3 步數一律呼叫 `tools/h3_steps.py`。

## rules.md 格式

```markdown
# <類型>：類型規則

> 通用做片規則在 `docs/rules/`，這裡只放這類影片額外的規則。

## 這類片是什麼

<一兩句話：內容、觀眾、用途>

## 規則

- <一句做法>（<一行理由>）
```

`output/<類型>/` 底下的 `CLAUDE.md` 會直接載入這份 `rules.md`，`output/<類型>/AGENTS.md` 只指過來，不再複製一份。
