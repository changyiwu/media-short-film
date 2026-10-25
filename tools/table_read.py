"""生成前試映：在首幀與 H3 之前，照 film.json 排出文字讀本時間軸，估片長，做一支靜音試映影片給人看節奏。
移植自上游 tools/assemble_read.py＋make_storyboard.py（2026-10-23），改成直接讀 film.json（不另寫 shots.json）、16:9、
鏡長照 make_film.py 的 shot_secs／edl 算法、配音長度用 VoxCPM2 語速估（不先做 TTS）。

用法（H3 venv，要 numpy、Pillow、ffmpeg）：
  "%PY_H3%" tools\\table_read.py <片子資料夾> [--storyboard] [--target 秒] [--film 別的.json]
  --storyboard  另生 16 宮格鉛筆草圖（每 16 鏡一張 4×4，gen_image.py 的 IMAGE_BACKEND，預設 Image 2.5 API → Codex，失敗就停）；
                不給就只有字幕。草圖已存在就沿用，要重畫刪掉 output/preview/storyboard_*.png。草圖只看故事順序與構圖、不附定妝圖、
                不進成片，所以不記到 output/image_backends.json（片尾名單不列它）。
  --target      目標片長（秒，需求確認的長度），報告會比對。
輸出 <片子資料夾>/output/preview/：讀本_timeline.json、讀本試映.mp4（1280×720、靜音）、_frames/、storyboard_<k>[_label].png。

估法（每句字數＝中文字＋英數字，不含標點）：
  - 配音長度＝字數 ÷ VOICE_CPS（3.5 字／秒；2026-10-24 量本機 4 支片 56 句 VoxCPM2：整體 3.4–3.95，最慢一句 2.3）。
    output/voice_picks.json 已有的句子改用實際音長。
  - H3 生成長度＝max(dur, 開口 at＋配音長度＋0.8 秒)，湊成 H3 格數（17n+5）；> 12 秒的鏡要拆。
    voice_mode h3_ref（H3 自己念，預設）的句子改用 max(dur, 3, 字數 ÷ 3＋2 秒)：上游實測 H3 每秒 2.3–4.7 字、有時晚 1.5–2.1 秒開口。
  - 成片裡的鏡長＝cut_out（"full"＝整段；不寫＝最後一句結束＋tail）− cut_in，同 make_film.py 的 edl。
試映畫面每鏡停留＝估計的成片鏡長；字幕照 make_film.py：角色台詞加「名字：」，旁白不加（narrator.sub_prefix 為 true 才加）。"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

T = Path(__file__).resolve().parent
sys.path.insert(0, str(T))
from fonts import font  # noqa: E402

FPS = 24
W, H = 1280, 720
PER_SHEET = 16
VOICE_CPS = 3.5
H3_CPS, H3_PAD, H3_MIN = 3.0, 2.0, 3.0      # voice_mode h3_ref：H3 生成長度＝max(3, 字數 ÷ 3＋2 秒)（上游實測，同 make_film.py）


def nchars(t):
    return len(re.findall(r"[一-鿿A-Za-z0-9]", t or ""))


def frames_for(d):
    n = 0
    while 17 * n + 5 < d * FPS:
        n += 1
    return 17 * n + 5


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout)


def lines_of(cfg):
    """同 make_film.py 的 LINES：[(鏡, {who, text, at, kind})]，角色台詞在前、旁白在後；索引對應 voice_picks.json。"""
    out = []
    for s in cfg["shots"]:
        if s.get("line"):
            out.append((s["id"], {**s["line"], "kind": "line"}))
        if s.get("vo"):
            out.append((s["id"], {**s["vo"], "who": "vo", "kind": "vo"}))
    return out


def estimate(cfg, here):
    picks_f = here / "output" / "voice_picks.json"
    picks = json.loads(picks_f.read_text(encoding="utf-8")) if picks_f.exists() else {}
    voices = dict(cfg["chars"], **({"vo": cfg["narrator"]} if cfg.get("narrator") else {}))
    lines, mix = lines_of(cfg), cfg.get("mix", {})
    rows, t = [], 0.0
    for s in cfg["shots"]:
        ins = bool(s.get("insert")); caps, n_chars, end, need = [], 0, None, s["dur"]
        for i, (sid, ln) in enumerate(lines):
            if sid != s["id"]:
                continue
            p = picks.get(str(i), {}); f = Path(p.get("file", ""))
            f = f if f.is_absolute() else here / f
            real = bool(p) and f.is_file()
            d = dur(f) if real else nchars(ln["text"]) / VOICE_CPS
            at = float(p["at"]) if real and p.get("source") == "h3" else ln["at"]
            n_chars += nchars(ln["text"]); end = max(end or 0, at + d)
            if ln["kind"] == "line" and ln.get("voice_mode", cfg.get("voice_mode", "h3_ref")) == "h3_ref":
                need = max(need, H3_MIN, nchars(ln["text"]) / H3_CPS + H3_PAD)   # H3 自己念：同 make_film.py 的 shot_secs
            else:
                need = max(need, at + d + 0.8)
            v = voices.get(ln["who"], {})
            name = f"{v.get('name', ln['who'])}：" if v.get("sub_prefix", ln["who"] != "vo") else ""
            caps.append(name + ln["text"])
        clip = need if ins else frames_for(need) / FPS
        a = round(float(s.get("cut_in", 0.0)) * FPS) / FPS; b = s.get("cut_out", "full" if ins else None)
        if b is None and end is not None:
            b = end + s.get("tail", mix.get("default_tail", 0.55))
        b = clip if b in (None, "full") else min(float(b), clip)
        b = min(round(b * FPS), int(clip * FPS + 1e-6)) / FPS
        voiced = sum(1 for i, (sid, _) in enumerate(lines) if sid == s["id"] and str(i) in picks)
        rows.append(dict(shot=s["id"], start=round(t, 2), dur=round(b - a, 2), table_dur=s["dur"], clip=round(clip, 2), chars=n_chars,
                         insert=ins, voiced=voiced, captions=caps))
        t += b - a
    return rows, round(t, 2)


def ending_secs(cfg):
    e = cfg.get("ending")
    on = bool(e) and (e.get("enabled", False) or os.environ.get("ENDING") == "1")
    return len(e["cards"]) * e.get("card_dur", 3.3) + e.get("title_dur", 7.5) if on else 0.0


# ----------------------------------------------------------------------------------------------- storyboard
def panel_desc(s):
    if s.get("insert"):
        return "a plain graphic title card or chart insert, no people"
    d = re.sub(r"\s*(of|in|from) <image\d+>", "", s.get("frame", "")).replace("<image", "image ")
    return " ".join(re.split(r"(?<=\.)\s+", d)[:2])          # 前兩句就夠看構圖，16 格的提示詞不要太長


def sheet_prompt(cfg, ps):
    """永遠 4×4（1536×1024 的格子才是橫的），鏡數不滿 16 的格子留白。"""
    cast = "; ".join(f"{c['name']} = {c['look']}" for c in cfg["chars"].values())
    ps = ps + [("", "an empty blank white panel")] * (PER_SHEET - len(ps))
    lines = "\n".join(f"Panel {i + 1} (row {i // 4 + 1}, column {i % 4 + 1}): {d}" for i, (_, d) in enumerate(ps))
    return ("A film storyboard sheet: exactly 4 columns and 4 rows of equal-sized horizontal panels, separated by thin white gutters, "
            "read left to right, top to bottom. Rough pencil sketch with light watercolor tint, simple and clear staging, cinematic framing. "
            "Absolutely NO text, letters, numbers, logos or captions anywhere in the image. "
            f"Characters (keep consistent across panels): {cast}\n{lines}")


def storyboard(cfg, pv):
    ps = [(s["id"], panel_desc(s)) for s in cfg["shots"]]
    for k, chunk in enumerate((ps[i:i + PER_SHEET] for i in range(0, len(ps), PER_SHEET)), start=1):
        raw, lab = pv / f"storyboard_{k}.png", pv / f"storyboard_{k}_label.png"
        if not raw.exists():
            tmp = pv / "_gen"; tmp.mkdir(exist_ok=True)
            r = subprocess.run([sys.executable, T / "gen_image.py", "--prompt", sheet_prompt(cfg, chunk),
                                "--width", "1536", "--height", "1024", "--prefix", f"film/storyboard_{k}", "--out", str(tmp)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            print(r.stdout[-1500:], r.stderr[-1500:], flush=True)
            fs = sorted(tmp.glob("*.png"), key=lambda f: f.stat().st_mtime)
            if r.returncode or not fs:
                raise SystemExit(f"草圖第 {k} 張生成失敗（不改用別的後端）；不要草圖就拿掉 --storyboard")
            fs[-1].replace(raw)
        im = Image.open(raw).convert("RGB"); w, h = im.size; d = ImageDraw.Draw(im); rows = 4
        f = ImageFont.truetype(font("jhbd"), max(18, w // 40))
        for i, (sid, _) in enumerate(chunk):                    # 鏡號用 PIL 疊（叫模型寫字會寫錯）
            x, y = (i % 4) * w / 4 + 6, (i // 4) * h / rows + 4
            d.rectangle([x, y, x + w // 14, y + w // 32], fill=(0, 0, 0))
            d.text((x + 4, y), sid, font=f, fill=(255, 220, 120))
        im.save(lab)
    print(f"{len(ps)} 鏡 → {(len(ps) + PER_SHEET - 1) // PER_SHEET} 張草圖（看節奏與構圖順序用，不是首幀）", flush=True)


def panel(pv, i):
    """從 storyboard_<k>_label.png 切出第 i 格（用白色格線切，列高不一定等分；切不出來就等分）。"""
    k, j = i // PER_SHEET + 1, i % PER_SHEET
    lab = pv / f"storyboard_{k}_label.png"
    if not lab.exists():
        return None
    nrows = 4
    im =Image.open(lab).convert("RGB"); w, h = im.size
    g = np.asarray(Image.open(pv / f"storyboard_{k}.png").convert("L")) > 235

    def cuts(frac, n):
        runs = []
        for x in (x for x, v in enumerate(frac) if v > 0.9):
            if runs and x == runs[-1][1] + 1:
                runs[-1][1] = x
            else:
                runs.append([x, x])
        edges = [0] + [x for a, b in runs for x in (a, b + 1)] + [n]
        return [(edges[t], edges[t + 1]) for t in range(0, len(edges), 2) if edges[t + 1] - edges[t] > 20]
    rows, cols = cuts(g.mean(1), h), cuts(g.mean(0), w)
    if len(rows) != nrows or len(cols) != 4:
        rows = [(int(h * t / nrows), int(h * (t + 1) / nrows)) for t in range(nrows)]
        cols = [(int(w * t / 4), int(w * (t + 1) / 4)) for t in range(4)]
    (y0, y1), (x0, x1) = rows[j // 4], cols[j % 4]
    return im.crop((x0, y0, x1, y1))


def frame(pv, i, r):
    bg = Image.new("RGB", (W, H), (12, 12, 16)); d = ImageDraw.Draw(bg)
    pn = panel(pv, i)
    if pn:
        k = min((W - 80) / pn.width, 470 / pn.height); pn = pn.resize((int(pn.width * k), int(pn.height * k)), Image.LANCZOS)
        bg.paste(pn, ((W - pn.width) // 2, 30))
    else:
        d.text((W // 2, 250), "（後製插入鏡）" if r["insert"] else "（沒有草圖）", font=ImageFont.truetype(font("jh"), 34),
               fill=(110, 110, 120), anchor="mm")
    d.text((30, 520), f"{r['shot']}  {r['dur']:.1f} 秒", font=ImageFont.truetype(font("jhbd"), 30), fill=(120, 230, 255))
    y, f = 565, ImageFont.truetype(font("jhbd"), 34)
    for c in r["captions"] or ["（無台詞）"]:
        while c and y < H - 40:
            seg, c = c[:34], c[34:]
            d.text((30, y), seg, font=f, fill=(240, 240, 240) if r["captions"] else (130, 130, 140)); y += 46
    return bg


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        sys.exit(__doc__)
    here = Path(args[0]).resolve()
    cfg = json.loads((here / (args[args.index("--film") + 1] if "--film" in args else "film.json")).read_text(encoding="utf-8"))
    target = float(args[args.index("--target") + 1]) if "--target" in args else None
    pv = here / "output" / "preview"; pv.mkdir(parents=True, exist_ok=True)
    if "--storyboard" in args:
        storyboard(cfg, pv)
    rows, story = estimate(cfg, here)
    end = ending_secs(cfg); total = round(story + end, 2)
    vid = pv / "_frames"; vid.mkdir(exist_ok=True); concat = []
    for i, r in enumerate(rows):
        fp = vid / f"{r['shot']}.png"; frame(pv, i, r).save(fp)
        concat += [f"file '{fp.as_posix()}'", f"duration {r['dur']:.3f}"]
    concat.append(f"file '{(vid / (rows[-1]['shot'] + '.png')).as_posix()}'")
    (vid / "list.txt").write_text("\n".join(concat), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(vid / "list.txt"),
                    "-vf", f"fps={FPS},format=yuv420p", "-t", f"{story:.3f}",   # concat 結尾重複的那張會多停一段，裁回估計長度
                    "-c:v", "libx264", "-crf", "23", "-an", str(pv / "讀本試映.mp4")], check=True)
    (pv / "讀本_timeline.json").write_text(json.dumps(dict(story=story, ending=end, total=total, target=target, voice_cps=VOICE_CPS, shots=rows),
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
    n_lines = len(lines_of(cfg)); n_voiced = sum(r["voiced"] for r in rows)
    print(f"估計本片 {story:.1f} 秒" + (f"＋片尾 {end:.1f} 秒＝{total:.1f} 秒" if end else "")
          + (f"（目標 {target:.0f} 秒，{'超出' if total > target else '少'} {abs(total - target):.1f} 秒）" if target else ""))
    print(f"配音長度：{n_voiced}／{n_lines} 句用實際音檔，其餘照每秒 {VOICE_CPS} 字估（語速慢的聲音可能再長 30%）")
    print("最長三鏡：", [(r["shot"], r["dur"]) for r in sorted(rows, key=lambda r: -r["dur"])[:3]])
    print("台詞把鏡頭撐長（H3 長度 > dur）：", [(r["shot"], r["table_dur"], r["clip"]) for r in rows if not r["insert"] and r["clip"] > frames_for(r["table_dur"]) / FPS + 0.01])
    print("H3 超過 12 秒（要拆）：", [(r["shot"], r["clip"]) for r in rows if not r["insert"] and r["clip"] > 12])
    print(f"→ {pv / '讀本試映.mp4'}")


if __name__ == "__main__":
    main()
