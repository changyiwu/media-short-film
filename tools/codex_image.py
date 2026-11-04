"""Image generation through the Codex CLI's built-in image tool (ChatGPT subscription, no OpenAI API key).
gen_image.py's default backend (auto) tries this first; the Image 2.5 API is used only when Codex is not usable here.

Finding codex.exe (same order as the global draw skill, route C; the version folder changes on every update):
  env CODEX_EXE -> Windows Codex App (Get-AppxPackage OpenAI.Codex) -> ~/.codex/.sandbox-bin/codex.exe -> codex on PATH.
Needs `codex login status` = "Logged in using ChatGPT" and feature image_generation = true.

generate(prompt, refs, out_png, size) -> Path. Refs are attached with `codex exec -i`; <imageN> in the prompt should already
read "Image N" (gen_image.py rewrites it). Codex cannot be told an exact pixel size, so the result is center-cropped to the
requested aspect ratio and resized to `size` ("WxH"). One image takes about a minute (timeout CODEX_TIMEOUT, default 600 s).
The original stays in ~/.codex/generated_images/.
"""
import os
import shutil
import subprocess
import time
from pathlib import Path

TIMEOUT = int(os.environ.get("CODEX_TIMEOUT", "600"))


def _run(cmd, **kw):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def find_codex():
    """Path of a usable codex.exe, or None."""
    cands = []
    if os.environ.get("CODEX_EXE"):
        cands.append(Path(os.environ["CODEX_EXE"]))
    if os.name == "nt":
        try:
            r = _run(["powershell", "-NoProfile", "-Command", "(Get-AppxPackage OpenAI.Codex).InstallLocation"], timeout=30)
            loc = r.stdout.strip()
            if loc:
                cands.append(Path(loc) / "app" / "resources" / "codex.exe")
        except Exception:
            pass
        cands.append(Path.home() / ".codex" / ".sandbox-bin" / "codex.exe")
    w = shutil.which("codex")
    if w:
        cands.append(Path(w))
    return next((c for c in cands if c.is_file()), None)


def check(cx):
    """None when codex can generate images, else the reason it cannot."""
    r = _run([cx, "login", "status"], timeout=60)
    if "Logged in using ChatGPT" not in (r.stdout + r.stderr):
        return "codex is not logged in with a ChatGPT account (run: codex login)"
    r = _run([cx, "features", "list"], timeout=60)
    line = next((l for l in r.stdout.splitlines() if l.split()[:1] == ["image_generation"]), "")
    if not line.rstrip().endswith("true"):
        return "codex feature image_generation is not enabled"
    return None


def _fit(src, dst, size):
    """Center-crop src to the aspect ratio of size ("WxH") and resize to exactly that size."""
    from PIL import Image
    w, h = (int(x) for x in size.lower().split("x"))
    im = Image.open(src).convert("RGB")
    W, H = im.size
    if W / H > w / h:
        nw = round(H * w / h); im = im.crop(((W - nw) // 2, 0, (W - nw) // 2 + nw, H))
    else:
        nh = round(W * h / w); im = im.crop((0, (H - nh) // 2, W, (H - nh) // 2 + nh))
    im.resize((w, h), Image.LANCZOS).save(dst)


def available():
    """(codex path, None) when Codex can generate images on this machine, else (None, reason)."""
    cx = find_codex()
    if not cx:
        return None, "codex.exe not found (install the Codex app/CLI, or set CODEX_EXE)"
    why = check(cx)
    return (None, why) if why else (cx, None)


def generate(prompt, refs, out_png, size="1536x1024", cx=None):
    """cx = a path already returned by available() (skips the checks); None = check here."""
    if cx is None:
        cx, why = available()
        if why:
            raise RuntimeError(why)
    out_png = Path(out_png)
    wd = out_png.parent / f"{out_png.stem}_work"
    wd.mkdir(parents=True, exist_ok=True)
    w, h = (int(x) for x in size.lower().split("x"))
    refs = [Path(r).resolve() for r in (refs or [])]
    ref_note = (f" The {len(refs)} attached image(s) are references, in order: Image 1"
                + "".join(f", Image {i}" for i in range(2, len(refs) + 1)) + "." if refs else "")
    task = ("Use your built-in image generation tool to create exactly ONE image. Do not write code and do not draw it yourself."
            f" Aspect ratio {w}:{h} (width:height).{ref_note}\n\nImage prompt:\n{prompt}\n\n"
            "When it is done, copy the generated image into the current working folder as result.png "
            "and reply with only its absolute path.")
    cmd = [cx, "exec", "--skip-git-repo-check", "--cd", wd, "--sandbox", "workspace-write"]
    for r in refs:
        cmd += ["-i", r]
    cmd += ["--", "-"]                               # prompt from stdin: no quoting / command-line length issues
    t0 = time.time()
    r = _run(cmd, input=task, timeout=TIMEOUT)
    res = wd / "result.png"
    if not res.exists():                             # it may have used another name
        pngs = sorted(wd.glob("*.png"), key=lambda f: f.stat().st_mtime)
        res = pngs[-1] if pngs else None
    if r.returncode != 0 or not res:
        raise RuntimeError(f"codex exec failed (exit {r.returncode}, {time.time() - t0:.0f}s): {(r.stderr or r.stdout)[-800:]}")
    _fit(res, out_png, size)
    return out_png
