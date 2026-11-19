"""牙齒自審：每個有聲音的 H3 鏡挑對嘴音軌最大聲的幾個時間點（嘴張最開），從 clip.mp4 截原解析度上半部畫面，
上下疊成一張圖，看牙齒是一顆一顆的、還是糊成一條白帶（DMAD 4 步的毛病，見 docs/03 §4）。

用法：
  python tools/teeth_sheet.py <片子資料夾> [鏡 ...] [--n 3] [--out <資料夾>]
    片子資料夾：底下有 work/h3/<鏡>/{clip.mp4, guide.wav}（template_local／template_battle／template_studio 都是這個結構）
    鏡：不給＝全部有聲音的鏡
輸出：<片子資料夾>/work/review/teeth/<鏡>.jpg（每張圖標鏡號、秒數、步數）＋印出每鏡的步數，方便挑出還是 4 步的近景。
判讀：看得到嘴的特寫、近景、中景，牙齒糊成白帶就把那鏡改 14 步、同 seed 重拍（構圖動作幾乎不變）；純側臉、嘴張得小、全景不用。
"""
import argparse
import json
import subprocess
import sys
import wave
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fonts import font  # noqa: E402


def loudest(wav, n, gap=0.8, win_s=0.1):
    """對嘴音軌最大聲的 n 個時間點（彼此至少隔 gap 秒）；整段靜音回傳 []。"""
    with wave.open(str(wav)) as wf:
        sr, ch = wf.getframerate(), wf.getnchannels()
        g = np.frombuffer(wf.readframes(wf.getnframes()), np.int16).astype(np.float32) / 32768
    if ch > 1:
        g = g.reshape(-1, ch).mean(1)
    win = int(win_s * sr)
    if len(g) <= win:
        return []
    rms = np.sqrt(np.mean(g[: len(g) // win * win].reshape(-1, win) ** 2, axis=1))
    if rms.max() < 0.01:
        return []
    picks = []
    for k in np.argsort(-rms):
        if rms[k] < rms.max() * 0.3:
            break
        t = (k + 0.5) * win_s
        if all(abs(t - p) >= gap for p in picks):
            picks.append(t)
        if len(picks) == n:
            break
    return sorted(picks)


def steps(d):
    """spec.json 的步數：draft＝DMAD 4 步，否則 steps（預設 14）。"""
    try:
        s = json.loads((d / "spec.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "?"
    return 4 if s.get("draft") else int(s.get("steps", 14))


def frame(clip, t):
    png = subprocess.check_output(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", clip.name, "-frames:v", "1",
                                   "-f", "image2pipe", "-vcodec", "png", "-"], cwd=clip.parent)   # 中文路徑：cwd 切進去只給檔名
    return Image.open(BytesIO(png)).convert("RGB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("film"); ap.add_argument("ids", nargs="*")
    ap.add_argument("--n", type=int, default=3, help="每鏡截幾格（預設 3）")
    ap.add_argument("--top", type=float, default=0.72, help="保留畫面上方幾成（臉在上半部，預設 0.72）")
    ap.add_argument("--out", help="輸出資料夾（預設 <片子>/work/review/teeth）")
    a = ap.parse_args()
    film = Path(a.film).resolve(); h3 = film / "work" / "h3"
    out = Path(a.out) if a.out else film / "work" / "review" / "teeth"; out.mkdir(parents=True, exist_ok=True)
    dirs = [h3 / i for i in a.ids] if a.ids else sorted(p for p in h3.iterdir() if p.is_dir())
    fnt = ImageFont.truetype(font("jhbd"), 30)
    for d in dirs:
        clip, wav = d / "clip.mp4", d / "guide.wav"
        if not clip.exists() or not wav.exists():
            if a.ids:
                print("skip（沒有 clip.mp4 或 guide.wav）", d.name)
            continue
        picks = loudest(wav, a.n)
        if not picks:
            continue                                                  # 無聲鏡：嘴是閉的，不用看牙齒
        st = steps(d); rows = []
        for t in picks:
            im = frame(clip, t); im = im.crop((0, 0, im.width, int(im.height * a.top)))
            ImageDraw.Draw(im).text((10, 8), f"{d.name}  {t:.1f}s  {st} 步", font=fnt, fill=(255, 220, 0),
                                    stroke_width=2, stroke_fill=(0, 0, 0))
            rows.append(im)
        sheet = Image.new("RGB", (rows[0].width, sum(r.height for r in rows)))
        y = 0
        for r in rows:
            sheet.paste(r, (0, y)); y += r.height
        sheet.save(out / f"{d.name}.jpg", quality=92)
        print(f"{d.name}\t{st} 步\t" + " ".join(f"{t:.1f}s" for t in picks))
    print("→", out)


if __name__ == "__main__":
    main()
