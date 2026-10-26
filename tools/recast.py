"""換角重製（docs/08）步驟 5–8 的工具：照參考影片換主角，動作（骨架）、背景、聲音沿用原片。

每支片一份 recast.json（放片子資料夾；裡面的相對路徑以片子資料夾為準；範例 tools/examples/recast.json）。
在片子資料夾執行（或加 --film <片子資料夾>）：
  python ../../../tools/recast.py first A B1         首幀：原片格補成 16:9 → Image 2.5 換角（會花 API 費用）
  python ../../../tools/recast.py close-mouth B2 --box 555 335 670 425
                                                     有發聲的鏡：首幀改成閉嘴（遮罩只開放嘴部）→ work/first/B2_closed.png
  python ../../../tools/recast.py check              首幀對照圖：原片｜首幀｜首幀＋骨架 → work/first/_check.jpg
  python ../../../tools/recast.py voice --seeds 6    新台詞候選：VoxCPM2「只給參考音」與「接續」兩種模式 × N 個 seed，逐條聽寫（自動改用 PY_VOICE）
  python ../../../tools/recast.py track cont_s1 [--word-end 0.48]
                                                     新音軌：整句換（a）；給 --word-end（候選裡新詞結束的秒數）再多做只換詞（b）
  python ../../../tools/recast.py prep [鏡…] [--take t2]   各鏡 shot.json＋骨架切段＋音軌切段＋cut.json（不用 GPU）
  python ../../../tools/recast.py run [鏡…] [--take t2]    逐鏡跑 h3_shot.py（做過的跳過；ComfyUI 沒開會自動在背景啟動）
  python ../../../tools/recast.py finish             剪到時間軸→接起來→淡入→RTX VSR→疊字卡→換新音軌→（ending.enabled 才）接片尾

時間軸一律用 24 fps 的格數（原片 30 fps 也換算成 24 fps，成片才會跟原片逐格對齊）。
短鏡照 docs/03 至少生 h3.min_dur 秒：骨架用最後一格延長、音軌補靜音，finish 再剪回原長度。
鏡的 "vocals": "auto" 會從音軌切段偵測有聲音的時段，填進 h3_shot 的 vocals（讓嘴跟著不是台詞的發聲動）。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent
FPS = 24
SR = 48000


# ----------------------------------------------------------------------------------------------- 共用
def ff(*a):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *map(str, a)], check=True)


def frames_for(d):  # 同 h3_shot.frames_for：H3 的格數是 17n+5
    n = 0
    while 17 * n + 5 < d * FPS:
        n += 1
    return 17 * n + 5


def count_frames(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True)
    return int(r.stdout.strip())


def grab(video, n, dst):
    ff("-i", video, "-vf", f"select=eq(n\\,{n})", "-vsync", "0", "-frames:v", "1", dst)


def read_audio(path):
    import numpy as np
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def write_audio(path, x):
    import numpy as np
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "f32le", "-ac", "1", "-ar", str(SR), "-i", "-",
                    "-c:a", "pcm_s16le", str(path)], input=np.clip(x, -1, 1).astype(np.float32).tobytes(), check=True)


def voiced(wav, end, db=-30.0, gap=0.25, shortest=0.08):
    """有聲音的時段 [(start, end)]（秒）：silencedetect 的反面，間隔 < gap 併起來，短於 shortest 丟掉。"""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(wav), "-af", f"silencedetect=n={db}dB:d=0.06", "-f", "null", "-"],
                       capture_output=True, text=True)
    marks = [(m.group(1), float(m.group(2))) for m in re.finditer(r"silence_(start|end): ([0-9.]+)", r.stderr)]
    segs, t = [], 0.0
    for kind, v in marks:
        if kind == "start":
            if v > t:
                segs.append([t, min(v, end)])
        else:
            t = v
    if not marks or marks[-1][0] == "end":
        segs.append([t, end])
    out = []
    for a, b in segs:
        if a >= end or b <= a:
            continue
        if out and a - out[-1][1] < gap:
            out[-1][1] = b
        else:
            out.append([a, b])
    return [(round(a, 2), round(b, 2)) for a, b in out if b - a >= shortest]


class Film:
    def __init__(self, path):
        self.dir = Path(path).resolve()
        self.cfg = json.loads((self.dir / "recast.json").read_text(encoding="utf-8"))
        fj = self.dir / "film.json"
        self.film = json.loads(fj.read_text(encoding="utf-8")) if fj.exists() else {}
        self.h3 = self.dir / "work" / "h3"
        self.size = self.cfg.get("size", [1344, 768])
        self.shots = self.cfg["shots"]

    def p(self, rel):
        return self.dir / rel

    def shot(self, sid):
        for s in self.shots:
            if s["id"] == sid:
                return s
        sys.exit(f"recast.json 沒有鏡 {sid}")

    def take_dir(self, s, take=None):
        return self.h3 / f"{s['id']}_{take or s.get('take', 't1')}"

    def pose_start_frame(self):
        return round(self.cfg["pose"]["start"] * FPS)

    def rel_repo(self):  # 給 cmd 用的相對路徑（中文絕對路徑在 cmd 參數裡會壞掉）
        return os.path.relpath(REPO, self.dir)


def in_env(film, var, args, log=None):
    """在片子資料夾用 configs\\profile.cmd 設好的直譯器（%PY_H3%／%PY_VOICE%）跑；參數一律用相對路徑。"""
    return in_profile(film, f'"!{var}!" ' + " ".join(args), log)  # !VAR!：profile.cmd 設好之後才展開（%VAR% 在整行開跑前就展開了）


def in_profile(film, cmd, log=None):
    line = f"call {film.rel_repo()}\\configs\\profile.cmd >nul && {cmd}"
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    if log:
        with open(log, "w", encoding="utf-8") as f:
            return subprocess.run("cmd /v:on /c " + line, cwd=film.dir, env=env, stdout=f, stderr=subprocess.STDOUT).returncode
    return subprocess.run("cmd /v:on /c " + line, cwd=film.dir, env=env).returncode


# ----------------------------------------------------------------------------------------------- first
def padded_source(film, fid, t):
    W, H = film.size
    src = film.p("work/first/_src")
    src.mkdir(parents=True, exist_ok=True)
    orig, pad = src / f"{fid}_orig.png", src / f"{fid}_pad.png"
    ff("-ss", f"{t:.3f}", "-i", film.p(film.cfg["source"]), "-frames:v", "1", orig)
    ff("-i", orig, "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black", pad)
    return pad


def cmd_first(film, a):
    sys.path.insert(0, str(TOOLS))
    import img25
    e = film.cfg["edit"]
    key = film.cfg["char"]
    look = film.film.get("chars", {}).get(key, {}).get("look", "")
    who, it = e.get("person", "the person"), e.get("char", "the character")
    refs = [film.p(r) for r in e.get("refs", [f"work/chars/{key}_turn.png", f"work/chars/{key}_expr.png"])]
    pics = " and ".join(f"Image {i + 2}" for i in range(len(refs)))
    W, H = film.size
    for fid in a.ids or list(film.cfg["firsts"]):
        f = film.cfg["firsts"][fid]
        pad = padded_source(film, fid, f["time"])
        prompt = (
            f"Image 1 is {e['frame']}. Edit it: replace {who} with {it} from {pics} ({e.get('same', 'the same character')}). "
            + f["pose"] + " "
            f"SIZE AND POSITION ARE CRITICAL: {it} occupies exactly the same area as {who} in Image 1 - the top of its head (ears included) "
            f"at the same height as the top of {who}'s head, its body as wide as {who}'s body, its feet exactly where {who}'s feet are; "
            f"{it}'s front limbs take the place of {who}'s arms and copy their position. "
            + (look + ". " if look else "")
            + "Remove any caption bar or text and continue the background there. "
            f"Fill the black bars by naturally extending {e['backdrop']}. "
            "Keep everything else as in Image 1: same camera framing and zoom, same lighting, same colors, "
            "same image quality - the character must be exactly as soft and as saturated as the rest of the frame, "
            f"not sharper, not cinematic. Exactly one {e.get('noun', 'character')}, no people. No text, no captions, no watermark. "
            f"Use {pics} only for {it}'s appearance, not their layout, pose or background.")
        stem = film.p("work/first/_test") / f"{fid}_{int(time.time())}"
        stem.parent.mkdir(parents=True, exist_ok=True)
        files = img25.edit(prompt, [pad, *refs], stem, size=f"{W}x{H}")
        log_f = film.p("work/image_backends.json")
        log = json.loads(log_f.read_text(encoding="utf-8")) if log_f.exists() else {}
        log["img25"] = log.get("img25", 0) + 1
        log_f.write_text(json.dumps(log), encoding="utf-8")
        dst = film.p(f"work/first/{fid}.png")
        dst.write_bytes(files[0].read_bytes())
        print("[ok]", fid, files[0].name, "->", dst)
    print("下一步：python ../../../tools/recast.py check，看首幀跟骨架有沒有對齊")


def paste_mouth(src_png, gen_png, box, dst_png):
    """把 gen 的嘴部對齊後貼回 src，嘴巴以外跟 src 逐像素相同。
    Image 2.5 即使給遮罩也會整張重畫：顏色變飽和、角色大小與位置偏掉，H3 照首幀生成整鏡就會跟著變（狗狗版 B2_t4）。
    對齊：比對嘴巴周圍一圈（不含嘴），搜尋縮放 0.85–1.15 與位移，先 1/4 解析度粗找再全解析度細修；顏色再照那一圈校正到 src。"""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    src = Image.open(src_png).convert("RGB")
    gen = Image.open(gen_png).convert("RGB").resize(src.size, Image.LANCZOS)
    W, H = src.size
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    M = 110  # 比對範圍：嘴部外擴的像素
    rx0, ry0, rx1, ry1 = max(0, x0 - M), max(0, y0 - M), min(W, x1 + M), min(H, y1 + M)
    hole = Image.new("L", (W, H), 0)
    ImageDraw.Draw(hole).ellipse((x0 - 12, y0 - 12, x1 + 12, y1 + 12), fill=255)
    ring = (np.asarray(hole, dtype=np.float32)[ry0:ry1, rx0:rx1] == 0)

    def warp(img, s, dx, dy, k=1):  # 以嘴部中心縮放 s 倍再平移 (dx, dy)；k = 圖已縮小幾倍
        c, d = cx / k, cy / k
        return img.transform(img.size, Image.AFFINE, (1 / s, 0, c - (c + dx / k) / s, 0, 1 / s, d - (d + dy / k) / s), Image.BILINEAR)

    def gray(img, k=1):
        g = np.asarray(img.convert("L"), dtype=np.float32)
        return g[ry0 // k:ry1 // k, rx0 // k:rx1 // k]

    def ncc(a, b, m):
        a, b = a[m], b[m]
        a, b = a - a.mean(), b - b.mean()
        return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-6))

    k = 4
    small = lambda im: im.resize((W // k, H // k), Image.BILINEAR)
    gen_k = small(gen).convert("L")
    gs = gray(small(src), k)
    mk = np.asarray(Image.fromarray(ring.astype(np.uint8) * 255).resize((gs.shape[1], gs.shape[0]))) > 127
    best = (-2, 1.0, 0, 0)
    for s in np.arange(0.85, 1.151, 0.01):
        for dy in range(-48, 49, k):
            for dx in range(-48, 49, k):
                v = ncc(gs, gray(warp(gen_k, s, dx, dy, k), k), mk)
                if v > best[0]:
                    best = (v, s, dx, dy)
    _, s0, dx0, dy0 = best
    best = (-2, s0, dx0, dy0)
    gs, gen_l = gray(src), gen.convert("L")
    for s in np.arange(s0 - 0.01, s0 + 0.0101, 0.005):
        for dy in range(dy0 - 4, dy0 + 5):
            for dx in range(dx0 - 4, dx0 + 5):
                v = ncc(gs, gray(warp(gen_l, s, dx, dy)), ring)
                if v > best[0]:
                    best = (v, s, dx, dy)
    v, s, dx, dy = best
    al = np.asarray(warp(gen, s, dx, dy), dtype=np.float32)
    sa = np.asarray(src, dtype=np.float32)
    # 顏色：嘴部外一圈，每個色版的平均與標準差照 src 校正
    band = Image.new("L", (W, H), 0)
    ImageDraw.Draw(band).ellipse((x0 - 40, y0 - 40, x1 + 40, y1 + 40), fill=255)
    ImageDraw.Draw(band).ellipse((x0, y0, x1, y1), fill=0)
    bm = np.asarray(band) > 0
    for c in range(3):
        g, t = al[..., c][bm], sa[..., c][bm]
        al[..., c] = (al[..., c] - g.mean()) * (t.std() / (g.std() + 1e-6)) + t.mean()
    feather = Image.new("L", (W, H), 0)
    ImageDraw.Draw(feather).ellipse((x0, y0, x1, y1), fill=255)
    m = np.asarray(feather.filter(ImageFilter.GaussianBlur(8)), dtype=np.float32)[..., None] / 255
    out = sa * (1 - m) + np.clip(al, 0, 255) * m
    Image.fromarray(out.round().astype(np.uint8)).save(dst_png)
    print(f"[paste] 對齊 NCC={v:.3f} 縮放={s:.3f} 位移=({dx},{dy}) -> {dst_png}")
    if v < 0.6:
        print("  ⚠️ 對齊分數偏低：嘴部附近可能被大幅重畫，請放大檢查")


def cmd_close_mouth(film, a):
    """首幀改成閉嘴（發聲鏡的首幀張著嘴，H3 就整鏡維持張嘴，嘴型不跟聲音動）。
    Image 2.5 遮罩編輯只取嘴部，對齊後貼回原首幀（paste_mouth），嘴巴以外不變。
    --reuse：不重生，直接用上次的 work/first/<id>_closed_raw.png 重新貼。"""
    raw = film.p(f"work/first/{a.id}_closed_raw.png")
    src = film.p(f"work/first/{a.id}.png")
    dst = film.p(f"work/first/{a.id}_closed.png")
    if a.reuse:
        if not raw.exists():
            sys.exit(f"沒有 {raw}")
        paste_mouth(src, raw, a.box, dst)
        return
    sys.path.insert(0, str(TOOLS))
    import img25
    from PIL import Image, ImageDraw
    W, H = film.size
    e = film.cfg["edit"]
    key = film.cfg["char"]
    it = e.get("char", "the character")
    mask = film.p(f"work/first/_src/{a.id}_mouth_mask.png")
    mask.parent.mkdir(parents=True, exist_ok=True)
    m = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    ImageDraw.Draw(m).ellipse(tuple(a.box), fill=(0, 0, 0, 0))  # 透明 = 可以重畫
    m.save(mask)
    prompt = (f"Image 1 is a video frame. Inside the masked area only, close {it}'s mouth: lips closed, no tongue visible, a calm "
              "closed-mouth expression like the closed-mouth faces in Image 2. THE OUTPUT MUST BE PIXEL-ALIGNED WITH IMAGE 1: same framing, "
              f"same zoom, no reframing, no zooming out, {it} stays exactly the same size and in exactly the same place, head at the same "
              "height. Change nothing outside the mouth: same pose, limbs, motion blur, fur, background, lighting and image quality.")
    stem = film.p("work/first/_test") / f"{a.id}_closed_{int(time.time())}"
    stem.parent.mkdir(parents=True, exist_ok=True)
    files = img25.edit(prompt, [src, film.p(e.get("expr", f"work/chars/{key}_expr.png"))], stem, size=f"{W}x{H}", mask=mask)
    log_f = film.p("work/image_backends.json")
    log = json.loads(log_f.read_text(encoding="utf-8")) if log_f.exists() else {}
    log["img25"] = log.get("img25", 0) + 1
    log_f.write_text(json.dumps(log), encoding="utf-8")
    raw.write_bytes(files[0].read_bytes())
    paste_mouth(src, raw, a.box, dst)
    print(f"在 recast.json 那一鏡寫 \"first\": \"{a.id}_closed\"；先跑 check 看有沒有對齊骨架")


def cmd_check(film, a):
    import tempfile
    from PIL import Image, ImageChops
    W, H = film.size
    S = 0.4
    pose = film.p(film.cfg["pose"]["file"])
    p0 = film.cfg["pose"]["start"]
    rows = []
    with tempfile.TemporaryDirectory() as td:
        items = [(fid, f, film.p(f"work/first/{v}.png")) for fid, f in film.cfg["firsts"].items() for v in (fid, f"{fid}_closed")]
        for fid, f, gen in items:
            if not gen.exists():
                if not gen.stem.endswith("_closed"):
                    print("[skip] 沒有首幀", fid)
                continue
            pad = film.p(f"work/first/_src/{fid}_pad.png")
            if not pad.exists():
                pad = padded_source(film, fid, f["time"])
            o = Image.open(pad).convert("RGB")
            g = Image.open(gen).convert("RGB").resize((W, H))
            ov = g
            if f["time"] >= p0:
                pf = Path(td) / f"{fid}.png"
                grab(pose, round((f["time"] - p0) * FPS), pf)
                ov = ImageChops.screen(g, Image.open(pf).convert("RGB").resize((W, H)))
            row = Image.new("RGB", (W * 3 + 20, H), (20, 20, 20))
            for i, im in enumerate((o, g, ov)):
                row.paste(im, (i * (W + 10), 0))
            rows.append(row.resize((int(row.width * S), int(H * S)), Image.LANCZOS))
    if not rows:
        sys.exit("還沒有任何首幀")
    sheet = Image.new("RGB", (rows[0].width, sum(r.height + 6 for r in rows)), (20, 20, 20))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height + 6
    out = film.p("work/first/_check.jpg")
    sheet.save(out, quality=90)
    print("[ok]", out)


# ----------------------------------------------------------------------------------------------- voice / track
def ensure_ref(film):
    ln = film.cfg["line"]
    ref = film.p(ln["ref"])
    if not ref.exists():  # 從原片切出那一句，前後各留約 0.1 秒
        ff("-ss", f"{max(0, ln['start'] - 0.11):.3f}", "-to", f"{ln['end'] + 0.11:.3f}", "-i", film.p(film.cfg["source_audio"]),
           "-ac", "1", "-ar", SR, ref)
        print("[ref]", ref)
    return ref


def trim(x, db=-40.0, margin=0.02):
    import numpy as np
    thr = 10 ** (db / 20) * max(1e-6, float(np.abs(x).max()))
    idx = np.where(np.abs(x) > thr)[0]
    if not len(idx):
        return x
    m = int(margin * SR)
    return x[max(0, idx[0] - m): idx[-1] + m]


def cmd_voice(film, a):
    if not a.inside:  # VoxCPM2 只裝在語音環境
        args = [f"{film.rel_repo()}\\tools\\recast.py", "voice", "--film", ".", "--inside", "--seeds", str(a.seeds)]
        sys.exit(in_env(film, "PY_VOICE", args))
    import torch
    from voxcpm import VoxCPM
    sys.path.insert(0, str(TOOLS))
    from tts_lexicon import load_lexicon, speakable
    ln = film.cfg["line"]
    say = speakable(ln["text"], load_lexicon(film.p(".")))  # 讀音替換表：念的與聽寫比對都用替換後的文字
    ref = ensure_ref(film)
    out = film.p(ln.get("cand_dir", "素材/voice/cand"))
    out.mkdir(parents=True, exist_ok=True)
    model_dir = Path(os.environ.get("AI_ROOT", r"C:\AI")) / "Voice" / "models" / "VoxCPM2"
    model = VoxCPM.from_pretrained(str(model_dir), load_denoiser=False, optimize=False, device="cuda")
    sr = model.tts_model.sample_rate
    files = []
    for mode in ("ref", "cont"):  # cont（接續模式）實測最準；ref 常漏最後一個字
        for s in range(1, a.seeds + 1):
            torch.manual_seed(s)
            kw = dict(text=say, cfg_value=2.0, inference_timesteps=10, normalize=False, denoise=False, reference_wav_path=str(ref))
            if mode == "cont":
                kw.update(prompt_wav_path=str(ref), prompt_text=ln["ref_text"])
            wav = model.generate(**kw)
            f = out / f"{mode}_s{s}.wav"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "f32le", "-ac", "1", "-ar", str(sr), "-i", "-", "-ar", str(SR),
                            "-c:a", "pcm_s16le", str(f)], input=wav.astype("float32").tobytes(), check=True)
            write_audio(out / f"trim_{mode}_s{s}.wav", trim(read_audio(f)))
            files.append(f)
            print("[gen]", f.name, f"{len(wav) / sr:.2f}s", flush=True)
    del model
    torch.cuda.empty_cache()
    import stt
    asr = stt.load_asr()
    rep = []
    for f in files:
        segs, _ = asr.transcribe(str(f), language="zh", beam_size=5, initial_prompt=say)
        heard = "".join(s.text for s in segs).strip()
        ok = say in re.sub(r"[，。！？、\s]", "", heard)
        rep.append({"file": f.name, "heard": heard, "ok": ok})
        print("[asr]", f.name, heard, "OK" if ok else "✗", flush=True)
    (out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"下一步：聽過後挑一條 → python ../../../tools/recast.py track <例如 cont_s1>")


def cmd_track(film, a):
    import numpy as np
    ln = film.cfg["line"]
    cdir = film.p(ln.get("cand_dir", "素材/voice/cand"))
    vdir = cdir.parent
    f = cdir / f"trim_{a.cand}.wav"
    cand = read_audio(f) if f.exists() else trim(read_audio(cdir / f"{a.cand}.wav"))
    orig = read_audio(film.p(film.cfg["source_audio"]))
    listen = vdir / "listen"

    def fade(x, ms=10):
        k = min(len(x) // 2, int(SR * ms / 1000))
        r = np.linspace(0, 1, k, dtype=np.float32)
        x = x.copy()
        x[:k] *= r
        x[-k:] *= r[::-1]
        return x

    def place(base, clip, t):
        i = int(t * SR)
        base[i:i + len(clip)] += clip[: len(base) - i]

    def silence(base, s, e):
        i, j, k = int(s * SR), int(e * SR), int(SR * 0.01)
        base[i:i + k] *= np.linspace(1, 0, k, dtype=np.float32)
        base[i + k:j - k] = 0
        base[j - k:j] *= np.linspace(0, 1, k, dtype=np.float32)

    head = int(max(3.0, ln["end"] + 1.0) * SR)
    write_audio(listen / "0_原音.wav", orig[:head])
    x = orig.copy()
    silence(x, ln["start"] - 0.03, ln["end"] + 0.04)
    place(x, fade(cand), ln["start"])
    write_audio(vdir / f"track_a_{a.cand}.wav", x)
    write_audio(listen / f"a_{a.cand}_整句換.wav", x[:head])
    print("[a]", vdir / f"track_a_{a.cand}.wav")
    if a.word_end:
        if "word_end" not in ln:
            sys.exit("只換詞要在 recast.json 的 line 寫 word_end（原句裡被換掉的詞結束的秒數）")
        w = fade(cand[: int(a.word_end * SR)])
        y = orig.copy()
        silence(y, ln["start"] - 0.03, ln["word_end"])
        place(y, w, ln["word_end"] - len(w) / SR)
        write_audio(vdir / f"track_b_{a.cand}.wav", y)
        write_audio(listen / f"b_{a.cand}_只換詞.wav", y[:head])
        print("[b]", vdir / f"track_b_{a.cand}.wav")
    print("聽 listen/ 裡的檔案，選定後把 recast.json 的 \"track\" 改成那條（例如 素材/voice/track_a_" + a.cand + ".wav）")


# ----------------------------------------------------------------------------------------------- prep / run
def cmd_prep(film, a):
    h = film.cfg["h3"]
    track = film.p(film.cfg["track"])
    pose = film.p(film.cfg["pose"]["file"])
    p0 = film.pose_start_frame()
    sub = h["subject"]
    for s in film.shots:
        if a.ids and s["id"] not in a.ids:
            continue
        d = film.take_dir(s, a.take)
        d.mkdir(parents=True, exist_ok=True)
        g0, g1 = s["frames"]
        n = g1 - g0
        dur = max(h.get("min_dur", 5.1), round(n / FPS + 0.05, 2))
        L = frames_for(dur)
        t0, t1 = g0 / FPS, g1 / FPS
        ff("-ss", f"{t0:.4f}", "-to", f"{t1:.4f}", "-i", track, "-af", f"apad=pad_dur={L / FPS + 0.2 - (t1 - t0):.3f}",
           "-ar", SR, "-ac", 1, d / "guide.wav")
        subj = dict(sub, voice=s.get("voice", sub.get("voice")))
        if not subj.get("voice"):
            subj.pop("voice")
        shot = {"camera": s["camera"], "action": s["action"], "dialogue": s.get("dialogue", [])}
        if s.get("vocals") == "auto":
            segs = voiced(d / "guide.wav", n / FPS)
            shot["vocals"] = [{"subject": sub["key"], "start": x, "end": y, "sound": s.get("vocal_sound", "a rhythmic wordless vocal sound")}
                              for x, y in segs]
            print(f"  {s['id']} vocals:", ", ".join(f"{x}-{y}s" for x, y in segs) or "（沒偵測到）")
        elif s.get("vocals"):
            shot["vocals"] = s["vocals"]
        spec = {"size": film.size, "style": h["style"], "setting": h["setting"],
                "soundscape": s.get("soundscape", h.get("soundscape")), "music": h.get("music", "N/A"),
                "duration": dur, "seed": s.get("seed", h.get("seed", 20261017) + g0), "steps": 4 if s.get("draft") else 14,
                "draft": bool(s.get("draft")), "subjects": [subj], "audio": {"fixed": {"file": "guide.wav"}},
                "shots": [shot], "constraints": h.get("constraints", []) + s.get("constraints", [])}
        if s.get("control", True):
            if g0 < p0:
                sys.exit(f"{s['id']} 從第 {g0} 格開始，比骨架影片的起點（第 {p0} 格）早；不要骨架就設 \"control\": false")
            ff("-i", pose, "-vf", f"select='between(n\\,{g0 - p0}\\,{g1 - p0 - 1})',setpts=N/{FPS}/TB,tpad=stop_mode=clone:stop={L - n}",
               "-r", FPS, "-c:v", "libx264", "-crf", 12, "-pix_fmt", "yuv420p", d / "control.mp4")
            spec["control"] = {"file": "control.mp4", "strength": s.get("control_strength", 1.0)}
        first = s.get("first", s["id"])
        if first.startswith("after:"):
            prev = film.shot(first[6:])
            clip = film.take_dir(prev) / "run" / "clip.mp4"
            if clip.exists():
                grab(clip, prev["frames"][1] - prev["frames"][0] - 1, d / "first.png")
            else:
                print(f"  {s['id']} 的首幀要等 {prev['id']} 生完（run 會自動補）")
        else:
            (d / "first.png").write_bytes(film.p(f"work/first/{first}.png").read_bytes())
        spec["first_frame"] = "first.png"
        (d / "shot.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        (d / "cut.json").write_text(json.dumps({"frames": n, "global": [g0, g1]}), encoding="utf-8")
        print(s["id"], d.name, f"用 {n} 格、生 {L} 格（{dur}s）", "骨架" if "control" in spec else "無骨架")


def cmd_run(film, a):
    rr = film.rel_repo()
    if in_profile(film, f"call {rr}\\tools\\start_comfy.cmd"):
        sys.exit("ComfyUI 啟動失敗")
    for s in film.shots:
        if a.ids and s["id"] not in a.ids:
            continue
        d = film.take_dir(s, a.take)
        if not (d / "shot.json").exists():
            sys.exit(f"{d.name} 沒有 shot.json：先跑 prep")
        if (d / "run" / "clip.mp4").exists() and not a.force:
            print("[skip]", d.name)
            continue
        first = s.get("first", "")
        if first.startswith("after:"):
            prev = film.shot(first[6:])
            clip = film.take_dir(prev) / "run" / "clip.mp4"
            if not clip.exists():
                sys.exit(f"{s['id']} 的首幀取自 {prev['id']}，但 {prev['id']} 還沒生")
            grab(clip, prev["frames"][1] - prev["frames"][0] - 1, d / "first.png")
        rel = os.path.relpath(d, film.dir)
        print("[start]", d.name, time.strftime("%H:%M:%S"), flush=True)
        args = [f"{rr}\\tools\\h3_shot.py", f"{rel}\\shot.json", "--out", f"{rel}\\run"] + (["--force"] if a.force else [])
        if in_env(film, "PY_H3", args, log=d / "run.log"):
            sys.exit(f"{d.name} 失敗，看 {d / 'run.log'}")
        print("[done]", d.name, time.strftime("%H:%M:%S"), (d / "run.log").read_text(encoding="utf-8").strip().splitlines()[-1], flush=True)


# ----------------------------------------------------------------------------------------------- finish
def caption_png(c, W, H, dst):
    from PIL import Image, ImageDraw, ImageFont
    k = W / 1344  # 位置與大小寫成 1344×768 的座標
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bar_h, y0, bar_w = round(c.get("bar_h", 84) * k), round(c.get("y", 632) * k), round(c.get("bar_w", 560) * k)
    bar = Image.new("RGBA", (bar_w, bar_h))
    bd = ImageDraw.Draw(bar)
    r, g, b = c.get("bar_color", [232, 92, 30])
    for x in range(bar_w):  # 左邊實色，右半段漸層淡出
        t = x / bar_w
        al = 235 if t < 0.45 else int(235 * (1 - (t - 0.45) / 0.55) ** 1.5)
        bd.line([(x, 0), (x, bar_h)], fill=(r, g, b, al))
    img.alpha_composite(bar, (round(c.get("x", 0) * k), y0))
    font = ImageFont.truetype(c.get("font", "C:/Windows/Fonts/msjhbd.ttc"), round(c.get("size", 50) * k))
    ImageDraw.Draw(img).text((round(c.get("text_x", 88) * k), y0 + bar_h // 2), c["text"], font=font, fill=tuple(c.get("color", [255, 232, 20])),
                             anchor="lm", stroke_width=round(4 * k), stroke_fill=(40, 20, 10))
    img.save(dst)


def ending_on(film):  # 同 make_film.ending_on：片尾是選用、預設不加
    e = film.film.get("ending")
    return bool(e) and (e.get("enabled", False) or os.environ.get("ENDING") == "1")


def cmd_finish(film, a):
    fin = film.cfg.get("finish", {})
    cut = film.p("work/cut")
    cut.mkdir(parents=True, exist_ok=True)
    total = 0
    lines = []
    for s in film.shots:
        n = s["frames"][1] - s["frames"][0]
        src = film.take_dir(s) / "run" / "clip.mp4"
        if not src.exists():
            sys.exit(f"{s['id']} 還沒生：{src}")
        dst = cut / f"{s['id']}.mp4"
        ff("-i", src, "-an", "-vf", f"select='lt(n\\,{n})',setpts=N/{FPS}/TB", "-frames:v", n, "-r", FPS,
           "-c:v", "libx264", "-crf", 10, "-preset", "slow", "-pix_fmt", "yuv420p", dst)
        lines.append(f"file '{dst.as_posix()}'")
        total += n
    secs = total / FPS
    lst = cut / "parts.txt"
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    body = cut / "body_768.mp4"
    vf = f"fade=t=in:st=0:d={fin['fade_in']}" if fin.get("fade_in") else "null"
    # upscale_vsr.py 會複製來源的音軌，先給一條靜音（第 4 步換成新音軌）
    ff("-f", "concat", "-safe", 0, "-i", lst, "-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono", "-vf", vf,
       "-c:v", "libx264", "-crf", 10, "-preset", "slow", "-pix_fmt", "yuv420p", "-r", FPS, "-c:a", "aac", "-shortest", body)
    got = count_frames(body)
    print("[concat]", got, "格", "（時間軸", total, "格）")
    if got != total:
        sys.exit("接起來的格數跟時間軸對不上")

    vsr = cut / "body_1080.mp4"
    if vsr.exists():
        vsr.unlink()  # upscale_vsr.py 不肯覆寫
    if in_env(film, "PY_H3", [f"{film.rel_repo()}\\tools\\upscale_vsr.py", "--source", "work\\cut\\body_768.mp4",
                              "--output", "work\\cut\\body_1080.mp4"]):
        sys.exit("RTX VSR 失敗")

    main = cut / "film_1080p.mp4"
    track = film.p(film.cfg["track"])
    c = fin.get("caption")
    if c:
        capf = cut / "caption.png"
        caption_png(c, 1920, 1080, capf)
        ff("-i", vsr, "-loop", 1, "-t", secs, "-i", capf, "-i", track, "-filter_complex",
           f"[1:v]format=rgba,fade=t=in:st={c.get('from', 0)}:d=0.3:alpha=1[c];[0:v][c]overlay=0:0:shortest=1,format=yuv420p[v]",
           "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-crf", 14, "-preset", "slow", "-c:a", "aac", "-b:a", "256k", "-ar", SR,
           "-t", secs, main)
    else:
        ff("-i", vsr, "-i", track, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", 14, "-preset", "slow", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "256k", "-ar", SR, "-t", secs, main)
    print("[ok]", main, f"{secs:.2f}s")

    if ending_on(film):
        ending = film.p("work/ending/ending.mp4")
        if not ending.exists():
            sys.exit("ending.enabled 開著但沒有 work/ending/ending.mp4：先跑 python make_film.py ending")
        has_a = "audio" in subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(ending)],
                                          capture_output=True, text=True).stdout
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ending)],
                                   capture_output=True, text=True).stdout.strip())
        ea = f"[1:a]aresample={SR},aformat=channel_layouts=mono[ea]" if has_a else f"anullsrc=r={SR}:cl=mono,atrim=0:{dur}[ea]"
        out = cut / "film_1080p_ending.mp4"
        ff("-i", main, "-i", ending, "-filter_complex",
           f"[0:a]aformat=channel_layouts=mono[ma];{ea};[0:v][ma][1:v][ea]concat=n=2:v=1:a=1[v][a]",
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", 14, "-preset", "slow", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "256k", out)
        print("[ok]", out)


# ----------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--film", default=".", help="片子資料夾（有 recast.json），預設目前資料夾")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("first"); p.add_argument("ids", nargs="*")
    p = sp.add_parser("close-mouth"); p.add_argument("id"); p.add_argument("--box", type=int, nargs=4, required=True,
                                                                          metavar=("X0", "Y0", "X1", "Y1"), help="嘴部橢圓範圍（首幀像素座標）")
    p.add_argument("--reuse", action="store_true", help="不重生，用上次的 <id>_closed_raw.png 重新對齊貼回")
    sp.add_parser("check")
    p = sp.add_parser("voice"); p.add_argument("--seeds", type=int, default=6); p.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    p = sp.add_parser("track"); p.add_argument("cand"); p.add_argument("--word-end", type=float)
    for name in ("prep", "run"):
        p = sp.add_parser(name); p.add_argument("ids", nargs="*"); p.add_argument("--take", help="例如 t2：寫到 work/h3/<鏡>_t2/")
        if name == "run":
            p.add_argument("--force", action="store_true", help="已經生過也重生")
    sp.add_parser("finish")
    # --film 放在子命令後面也可以
    argv = sys.argv[1:]
    if "--film" in argv[1:] and argv[0] != "--film":
        i = argv.index("--film")
        argv = argv[i:i + 2] + argv[:i] + argv[i + 2:]
    a = ap.parse_args(argv)
    film = Film(a.film)
    {"first": cmd_first, "close-mouth": cmd_close_mouth, "check": cmd_check, "voice": cmd_voice, "track": cmd_track, "prep": cmd_prep, "run": cmd_run,
     "finish": cmd_finish}[a.cmd](film, a)


if __name__ == "__main__":
    main()
