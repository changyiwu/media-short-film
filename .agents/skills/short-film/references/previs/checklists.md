# 預演檢查清單

每一關都要能回答「憑什麼說通過」。需求確認、選鏡返工、對嘴、後製、交付的檢查已移到 `../interview.md` 與 `../review.md`。

## 1. 鏡位契約

- [ ] 每鏡都有 `camera`、`frames`、`lens_mm`、`location`、`target`、`motion`、`visible`
- [ ] 幀數符合 **17n+5**（`make_film.py` 會自動對齊；手動用 guide 影片時要自己算）
- [ ] 已列出 `identical_camera_setups` 與 `distinct_setups` 數量
- [ ] 運鏡狀態（static / push）與 `film.json` 的 `camera`、`action` 一致
- [ ] 已確認哪些鏡**只有一人**、哪些**兩人必須同框**

## 2. 布置圖（生成前）

- [ ] 每鏡都算了一張，人工確認座位、朝向、背景、景別、道具
- [ ] 空景鏡角色已隱藏、道具保留
- [ ] 沒有不該出現的物件（多餘窗、雜物、重複人物）
- [ ] 同機位的鏡頭確認是刻意的，不是誤用

**布置圖通過 ≠ 對嘴或表演通過。**

## 3. 運鏡

- [ ] 運鏡是 `.blend` 內的 keyframe，不是算圖腳本逐格位移
- [ ] 只有真的要運鏡的鏡頭才有 keyframe
- [ ] 重算驗證與原腳本等價（逐格比對）

## 4. 交給生成前

- [ ] 確認實際 ComfyUI 版本與模型（**目錄名稱不代表實際版本**）
- [ ] 收件鎖正確的 Save 節點 ID
- [ ] `.blend` 另存 `<場景>_reusable.blend`，不覆寫原檔
