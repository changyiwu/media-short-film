"""首幀臉數檢查：臉比角色多就提醒（可能多畫了人，也可能是劇情本來就有旁人，要人看）。make_film.py 的 frames 階段會自動呼叫。
用法（Voice venv，要 opencv-python-headless）：
  "%PY_VOICE%" face_count.py <首幀資料夾> S1=1 S2=2 ...      每個 <鏡號>=<角色數>，看 <鏡號>.png
只算臉高 ≥ 畫面高 8% 的臉（背景遠處的小臉不算）。臉偵測用 YuNet（約 230 KB，第一次自動下載到 AI_ROOT/models）。
做法改寫自上游 pipeline/template_battle/make_battle.py 的 frames 與 battle_gfx.py 的 faces。"""
import os
import sys
import urllib.request
from pathlib import Path

import cv2
import numpy as np

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
YUNET = Path(os.environ.get("AI_ROOT", r"C:\AI")) / "models" / "face_detection_yunet_2023mar.onnx"
MIN_FACE = 0.08


def faces(im):
    """臉框 [(x, y, w, h)]。"""
    if not YUNET.exists():
        YUNET.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(YUNET_URL, str(YUNET))
    h, w = im.shape[:2]
    _, res = cv2.FaceDetectorYN.create(str(YUNET), "", (w, h), 0.6).detect(im)
    return [tuple(int(v) for v in r[:4]) for r in (res if res is not None else [])]


def main():
    d = Path(sys.argv[1]); extra = []
    for kv in sys.argv[2:]:
        sid, n = kv.split("="); p = d / f"{sid}.png"
        if not p.exists():
            continue
        im = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_COLOR)   # imread 讀不了中文路徑
        found = len([f for f in faces(im) if f[3] >= im.shape[0] * MIN_FACE])
        if found > int(n):
            extra.append(f"{sid}（{found} 張臉／{n} 位角色）")
    print("⚠ 首幀臉比角色多（可能多畫了人，也可能是劇情本來就有旁人，要看）：" + "、".join(extra) if extra else "首幀臉數：沒有比角色多的", flush=True)


if __name__ == "__main__":
    main()
