"""手指放大表（上游〈向日葵之戰〉2026-11-04：3:50 張開的手只有 4 根）：
每鏡首幀用 YOLO pose 找手腕，沿「手肘→手腕」方向切出手部，拼成 work/review/fingers_XX.jpg，一隻一隻數。
--clips：改看 H3 成片（上游 1:55 首幀 5 根，H3 拍動作時才多長出第 6 根），每鏡取 25%／50%／75% 三格，只留看得清手指的大手 → cfingers_XX.jpg。
⚠ 靠畫面邊緣的手常抓不到，只能當輔助：一定還要看每鏡完整首幀，張開的手逐隻數。
移植自上游 pipeline/template_battle/finger_sheet.py（上游 e634cce）；檔案在 work/，字型走 tools/fonts.py。

需要 ultralytics（AGPL-3.0，Voice venv 預設沒裝，選用）："%PY_VOICE%" -m pip install ultralytics
權重 yolo11x-pose.pt 第一次跑時由 ultralytics 自動下載到 %AI_ROOT%\\tools\\models\\yolo\\（或用 YOLO_POSE 指定檔案）。
用法（Voice venv，片子資料夾）："%PY_VOICE%" finger_sheet.py [--clips] [鏡號 …]"""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")
try:
    from ultralytics import YOLO
except ImportError:
    sys.exit("沒有 ultralytics：\"%PY_VOICE%\" -m pip install ultralytics（AGPL-3.0，只在本機用）")

HERE = Path(__file__).resolve().parent
OUT = HERE / "work"
CFG = json.loads((HERE / "battle.json").read_text(encoding="utf-8"))
sys.path.insert(0, str((HERE / CFG.get("repo_dir", "../../..") / "tools").resolve()))
from fonts import font as font_path  # noqa: E402

CLIPS = "--clips" in sys.argv
args = [x for x in sys.argv[1:] if x != "--clips"]
want = args or [s["id"] for s in CFG["shots"] if not s.get("painting")]
TH, COLS, ROWS = int(os.environ.get("FINGER_TH", 260)), int(os.environ.get("FINGER_COLS", 8)), 5
wdir = Path(os.environ.get("AI_ROOT", r"C:\AI")) / "tools" / "models" / "yolo"; wdir.mkdir(parents=True, exist_ok=True)
model = YOLO(os.environ.get("YOLO_POSE") or str(wdir / "yolo11x-pose.pt"))
font = ImageFont.truetype(font_path("jhbd"), 22)
crops = []


def samples(sid):
    if not CLIPS:
        p = OUT / "first" / f"{sid}.png"
        if p.exists():
            yield sid, cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)
        return
    p = OUT / "h3" / sid / "clip.mp4"
    if not p.exists():
        return
    cap = cv2.VideoCapture(str(p))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    for f in (0.25, 0.5, 0.75):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * f))
        ok, im = cap.read()
        if ok:
            yield f"{sid} {int(f * 100)}", im
    cap.release()


for sid, img in (x for s_ in want for x in samples(s_)):
    res = model.predict(img, conf=0.35, verbose=False, device=os.environ.get("YOLO_DEVICE", "cpu"))[0]
    kp = res.keypoints.data.cpu().numpy() if res.keypoints is not None else np.zeros((0, 17, 3))
    H, W = img.shape[:2]
    for person in kp:
        shoulder = np.linalg.norm(person[5][:2] - person[6][:2])
        for el, wr in ((7, 9), (8, 10)):
            if person[wr][2] < 0.3:
                continue
            e, w = person[el][:2], person[wr][:2]
            c = w + (w - e) * 0.35
            r = int(max(70, min(220, np.linalg.norm(w - e) * 0.7, shoulder * 0.55) if shoulder else 110))
            if CLIPS and r < int(os.environ.get("FINGER_MIN_R", 75)):      # 手太小，觀眾也數不到
                continue
            x0, y0 = int(np.clip(c[0] - r, 0, W - 1)), int(np.clip(c[1] - r, 0, H - 1))
            x1, y1 = int(np.clip(c[0] + r, 1, W)), int(np.clip(c[1] + r, 1, H))
            if x1 - x0 < 40 or y1 - y0 < 40:
                continue
            crops.append((sid, Image.fromarray(cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)).resize((TH, TH), Image.LANCZOS)))
(OUT / "review").mkdir(parents=True, exist_ok=True)
n = COLS * ROWS
for k in range(0, len(crops), n):
    sheet = Image.new("RGB", (COLS * TH, ROWS * TH), "black")
    d = ImageDraw.Draw(sheet)
    for i, (sid, c) in enumerate(crops[k:k + n]):
        x, y = i % COLS * TH, i // COLS * TH
        sheet.paste(c, (x, y))
        d.rectangle((x, y, x + 110, y + 28), fill="black")
        d.text((x + 4, y + 2), sid, fill="yellow", font=font)
    sheet.save(OUT / "review" / f"{'cfingers' if CLIPS else 'fingers'}_{k // n:02d}.jpg", quality=88)
print(len(crops), "隻手；", (len(crops) + n - 1) // n, "張表 → work/review/")
