# pipeline：新片範本與安裝驗證

| 資料夾 | 用途 | 怎麼用 |
|---|---|---|
| [`template_local/`](template_local/README.md) | **新片範本**：`film.json` 寫完整支片，`make_film.py` 從角色定妝做到成片＋自審 | 在 repo 根目錄跑 `python tools/new_film.py <類型> <片名>`（`short-film` 技能），建成 `output/<類型>/<片名>/`；不要手動複製、不要直接在這裡改 |
| `demo_local/` | **安裝驗證**：約 20 秒、4 鏡的示範片，證明本機環境能從頭跑到成片 | `"%PY_H3%" pipeline\demo_local\run_demo.py`（照 `AGENT_SETUP.md`、階段三） |

- 自己的片一律放 `output/<類型>/<片名>/`（不進 repo，只走雲端硬碟）；做片規則在 `output/AGENTS.md`，整體流程見 [docs/02_端到端流程.md](../docs/02_端到端流程.md)。
- `run_demo.py` 固定用本機 Qwen-Image 生圖、單張半身定妝（驗證本機安裝用）；做片的 `make_film.py` 預設走 OpenAI 生圖、轉面圖＋表情表＋臉部近照。
- 兩支腳本都直接用 repo 的 `tools/`，輸出在 `demo_local/output/`、各片的 `work/`（都已列入 `.gitignore`）。
