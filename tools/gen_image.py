"""Image generation. Default = OpenAI image models: Codex CLI first, Image 2.5 API second; local ComfyUI (Qwen) is opt-in.

Backend (--backend or env IMAGE_BACKEND):
  auto (default)   2026-11-04: Codex CLI if usable here (codex.exe found, logged in with ChatGPT, image_generation on;
                   ChatGPT subscription, its model version is not disclosed), otherwise img25 if an API key is found,
                   otherwise STOP. The choice is made per run BEFORE generating: a Codex/API call that fails
                   STOPS - no retry on the other one (a film can still mix both if Codex becomes usable/unusable between
                   images; make_film.py credits whatever was really used)
                   Qwen is never picked automatically: it looks different and needs different character refs.
  codex            Codex CLI built-in image tool on the ChatGPT subscription (tools/codex_image.py, no API key).
                   Refs attached, result cropped to the requested aspect ratio; seed ignored.
  img25            OpenAI Image 2.5 API (tools/img25.py). Key: OPENAI_API_KEY / OPENAI_KEY_FILE / ~/.openai.env.
                   <imageN> in the prompt becomes "Image N". --seed/--steps/--cfg are ignored (cloud).
                   IMAGE_FALLBACK=1 restores the old fall-back-to-local when the API fails.
  local            ComfyUI on this machine (below).
--lora, --uncensored and krea*/*-unc presets always run locally.
Every run prints "[backend] img25", "[backend] codex" or "[backend] local" so callers can credit the right tool.

Local image generation via the ComfyUI API.

Main model = Qwen-Image 2.1. Other installed options: Krea 2, Qwen-Image-Edit 2511.

Prereqs:
  * ComfyUI running on http://127.0.0.1:8188  (see tools/start_comfy.ps1)

Presets (--model):
  qwen21         Qwen-Image 2.1 (official int8)                steps 50, cfg 1, default 2688x1536 (2K)
  qwen21-unc     Qwen-Image 2.1 (uncensored GGUF + heretic TE) steps 50, cfg 1, default 2688x1536 (2K)

Qwen-Image 2.1 quality defaults (A/B 2026-09-28, 試行/Qwen21畫質比較_20260928): 50 steps + native 2K + a LONG
photographer-style prompt (camera/lens, light, subject, simple background, "uncluttered") is what closes most of the gap
to Image 2.5; listing every room object makes a cluttered image. cfg stays 1 (official), so --negative is ignored.
  krea2          Krea 2 Turbo (official fp8)                   steps 8,  cfg 1
  krea2-unc      Krea 2 Turbo (uncensored v1.1)                steps 8,  cfg 1
  qwen-edit      Qwen-Image-Edit 2511 (official fp8mixed)      steps 20, cfg 4
  qwen-edit-unc  Qwen-Image-Edit 2511 (uncensored v1.1)        steps 16, cfg 1

Examples (cmd, after call <repo>\\configs\\profile.cmd):
  "%PY_H3%" tools/gen_image.py --prompt "a red fox, cinematic" --width 1024 --height 1024
  ... --model qwen21-unc --prompt "..."
  ... --model krea2 --prompt "a sci-fi street market at night"
  ... --model qwen-edit --ref base.png --ref shirt.png --prompt "put the shirt from <image2> on <image1>"

Outputs go to ComfyUI/output/<prefix>_00001_.png (the script prints the path).
"""
import argparse
import json
import shutil
import time
import urllib.request
import os
from pathlib import Path

DEFAULT_HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
COMFY_DIR = Path(os.environ.get("COMFY_DIR", r"C:\AI\H3\ComfyUI-0.36.0"))
import comfy_paths  # noqa: E402  input／output 資料夾（Comfy Desktop 不在 COMFY_DIR 底下）

PRESETS = {
    "qwen21": dict(
        unet="qwen_image_2.1_int8_convrot.safetensors", clip="qwen3vl_8b_int8_convrot.safetensors",
        clip_type="qwen_image", vae="qwen_image_2.1_vae_bf16.safetensors",
        encoder="qwen21", steps=50, cfg=1.0, sampler="euler", scheduler="simple", size=(2688, 1536)),
    "qwen21-unc": dict(
        unet="qwen-image-2.1-uncensored-Q8_0.gguf", clip="qwen3vl_8b_w4a8_heretic.safetensors",
        clip_type="qwen_image", vae="qwen_image_2.1_vae_bf16.safetensors",
        encoder="qwen21", steps=50, cfg=1.0, sampler="euler", scheduler="simple", size=(2688, 1536)),
    "krea2": dict(
        unet="krea2_turbo_fp8_scaled.safetensors", clip="qwen3vl_4b_fp8_scaled.safetensors",
        clip_type="krea2", vae="qwen_image_vae.safetensors",
        encoder="clip", steps=8, cfg=1.0, sampler="euler", scheduler="simple"),
    "krea2-unc": dict(
        unet="Krea2_turbo_uncensored_edit_v1.1-fp8_scaled.safetensors", clip="qwen3vl_4b_fp8_scaled.safetensors",
        clip_type="krea2", vae="qwen_image_vae.safetensors",
        encoder="clip", steps=8, cfg=1.0, sampler="euler", scheduler="simple"),
    "qwen-edit": dict(
        unet=os.environ.get("QWEN_EDIT_UNET", "qwen_image_edit_2511_fp8mixed.safetensors"), clip="qwen_2.5_vl_7b_fp8_scaled.safetensors",
        clip_type="qwen_image", vae="qwen_image_vae.safetensors",
        encoder="editplus", steps=20, cfg=4.0, sampler="euler", scheduler="simple", auraflow=3.1),
    "qwen-edit-unc": dict(
        unet="qwen_image_edit_uncensored_v1.1-fp8.safetensors", clip="qwen25_vl_7b_uncensored_fp8.safetensors",
        clip_type="qwen_image", vae="qwen_image_vae.safetensors",
        encoder="editplus", steps=16, cfg=1.0, sampler="euler", scheduler="simple", auraflow=3.1),
}


def _req(host, path, data=None, timeout=60):
    req = urllib.request.Request(
        host + path,
        data=json.dumps(data).encode("utf-8") if data is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def ensure_server(host):
    try:
        return _req(host, "/system_stats", timeout=5)
    except Exception as e:
        raise SystemExit(f"ComfyUI is not reachable at {host} ({e}).\nStart it: tools\\start_comfy.ps1")


def stage_image(image):
    p = Path(image)
    if p.is_file():
        dest = comfy_paths.input_dir(DEFAULT_HOST) / p.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if p.resolve() != dest.resolve():
            shutil.copy2(p, dest)
        return p.name
    return image


def build(a, preset, prompt):
    g = {}
    if preset["unet"].lower().endswith(".gguf"):
        g["1"] = {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": preset["unet"]}}
    else:
        g["1"] = {"class_type": "UNETLoader", "inputs": {"unet_name": preset["unet"], "weight_dtype": "default"}}
    g["2"] = {"class_type": "CLIPLoader",
              "inputs": {"clip_name": preset["clip"], "type": preset["clip_type"], "device": "default"}}
    g["3"] = {"class_type": "VAELoader", "inputs": {"vae_name": preset["vae"]}}
    g["5"] = {"class_type": "EmptyLatentImage",
              "inputs": {"width": a.width, "height": a.height, "batch_size": 1}}
    g["6"] = {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "latent_image": ["5", 0], "seed": a.seed, "steps": a.steps,
                         "cfg": a.cfg, "sampler_name": a.sampler, "scheduler": a.scheduler, "denoise": 1.0}}
    g["7"] = {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}}
    g["8"] = {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": a.prefix}}

    refs = []
    for i, ref in enumerate(a.ref or [], start=1):
        node = str(10 + i)
        g[node] = {"class_type": "LoadImage", "inputs": {"image": stage_image(ref)}}
        refs.append(node)

    enc = preset.get("encoder", "qwen21")
    if enc == "qwen21":
        ins = {"clip": ["2", 0], "prompt": prompt, "negative_prompt": a.negative, "resolution": a.resolution}
        for i, node in enumerate(refs, start=1):
            ins[f"images.image_{i}"] = [node, 0]
        g["4"] = {"class_type": "TextEncodeQwenImage21", "inputs": ins}
        g["6"]["inputs"]["positive"] = ["4", 0]
        g["6"]["inputs"]["negative"] = ["4", 1]
    elif enc == "clip":
        g["4"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}}
        g["9"] = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}}
        g["6"]["inputs"]["positive"] = ["4", 0]
        g["6"]["inputs"]["negative"] = ["9", 0]
    else:  # editplus (Qwen-Image-Edit 2511)
        pos = {"clip": ["2", 0], "vae": ["3", 0], "prompt": prompt}
        neg = {"clip": ["2", 0], "vae": ["3", 0], "prompt": a.negative}
        for i, node in enumerate(refs, start=1):
            pos[f"image{i}"] = [node, 0]
            neg[f"image{i}"] = [node, 0]
        g["4"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": pos}
        g["9"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": neg}
        g["14"] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
                   "inputs": {"conditioning": ["4", 0], "reference_latents_method": "index_timestep_zero"}}
        g["15"] = {"class_type": "FluxKontextMultiReferenceLatentMethod",
                   "inputs": {"conditioning": ["9", 0], "reference_latents_method": "index_timestep_zero"}}
        model_src = ["1", 0]
        if preset.get("auraflow"):
            g["16"] = {"class_type": "ModelSamplingAuraFlow",
                       "inputs": {"model": model_src, "shift": preset["auraflow"]}}
            model_src = ["16", 0]
        g["17"] = {"class_type": "CFGNorm", "inputs": {"model": model_src, "strength": 1.0}}
        g["6"]["inputs"]["model"] = ["17", 0]
        g["6"]["inputs"]["positive"] = ["14", 0]
        g["6"]["inputs"]["negative"] = ["15", 0]
    if getattr(a, "lora", None):  # 2026-10-07: --lora name.safetensors[:strength], repeatable (stacked in order)
        model = ["1", 0]
        for i, spec in enumerate(a.lora):
            name, _, st = spec.partition(":")
            nid = str(90 + i)
            g[nid] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": model, "lora_name": name, "strength_model": float(st or 1.0)}}
            model = [nid, 0]
        for nid, n in g.items():
            if not nid.startswith("9") or len(nid) != 2:
                if n["inputs"].get("model") == ["1", 0]:
                    n["inputs"]["model"] = model
    return g


def img25_size(w, h):
    """Image 2.5 size string: keep aspect ratio, long edge <= 2048, both sides multiples of 16."""
    s = min(1.0, 2048 / max(w, h))
    return f"{max(16, round(w * s / 16) * 16)}x{max(16, round(h * s / 16) * 16)}"


def gen_img25(a, prompt):
    """Generate with OpenAI Image 2.5. Returns True on success, False on failure (main() then stops, or falls back to
    local only when IMAGE_FALLBACK=1)."""
    import re
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import img25
    except SystemExit as e:                       # img25 exits at import when no API key is set
        print(f"[img25] unavailable: {e}", flush=True)
        return False
    prompt = re.sub(r"<image(\d+)>", r"Image \1", prompt)   # Qwen-Edit tag -> Image 2.5 wording
    size = img25_size(a.width, a.height)
    stem = Path(a.out or "img25_out") / "_img25" / f"{Path(a.prefix).name}_{int(time.time())}"
    t0 = time.time()
    print(f"[queued] backend=img25 {size} quality={img25.QUALITY} refs={len(a.ref or [])}", flush=True)
    try:
        files = img25.edit(prompt, a.ref, stem, size=size) if a.ref else img25.generate(prompt, stem, size=size)
    except Exception as e:
        print(f"[img25] error: {str(e)[:500]}", flush=True)
        return False
    if not files:
        print("[img25] no image returned", flush=True)
        return False
    print("[backend] img25", flush=True)
    for f in files:
        print(f"[out] {f}")
        if a.out:                                 # same layout as the local path: finished PNG copied into --out
            dest = Path(a.out) / f.name
            shutil.copy2(f, dest)
            print(f"[copy] {dest}")
    print(f"[done] total {time.time() - t0:.1f}s")
    return True


def has_openai_key():
    """True when img25.py finds a key (OPENAI_API_KEY / OPENAI_KEY_FILE / ~/.openai.env); img25 exits at import otherwise."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import img25  # noqa: F401
        return True
    except SystemExit:
        return False


def codex_available():
    """(codex path, None) or (None, reason) - see tools/codex_image.py."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import codex_image
    return codex_image.available()


def gen_codex(a, prompt, cx=None):
    """Generate through the Codex CLI (ChatGPT subscription). Returns True on success, False on failure (main() stops)."""
    import re
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import codex_image
    prompt = re.sub(r"<image(\d+)>", r"Image \1", prompt)
    size = img25_size(a.width, a.height)
    dst = Path(a.out or "codex_out") / "_codex" / f"{Path(a.prefix).name}_{int(time.time())}.png"
    t0 = time.time()
    print(f"[queued] backend=codex {size} refs={len(a.ref or [])}", flush=True)
    try:
        f = codex_image.generate(prompt, a.ref, dst, size=size, cx=cx)
    except Exception as e:
        print(f"[codex] error: {str(e)[:800]}", flush=True)
        return False
    print("[backend] codex", flush=True)
    print(f"[out] {f}")
    if a.out:
        shutil.copy2(f, Path(a.out) / f.name)
        print(f"[copy] {Path(a.out) / f.name}")
    print(f"[done] total {time.time() - t0:.1f}s")
    return True


def main():
    ap = argparse.ArgumentParser(description="Generate an image locally via ComfyUI.")
    ap.add_argument("--prompt", default=None)
    ap.add_argument("--prompt-file", default=None)
    ap.add_argument("--negative", default="blurry, low quality, jpeg artifacts, extra limbs, watermark, text")
    ap.add_argument("--ref", action="append", default=None,
                    help="reference image (repeatable); use <image1>/<image2> in the prompt")
    ap.add_argument("--model", default="qwen21", choices=sorted(PRESETS), help="model preset")
    ap.add_argument("--uncensored", action="store_true", help="shorthand for --model qwen21-unc")
    ap.add_argument("--width", type=int, default=None, help="default: preset size (qwen21 2688x1536) else 1024")
    ap.add_argument("--height", type=int, default=None)
    ap.add_argument("--resolution", type=int, default=1024, help="reference-image resize budget (qwen21 only)")
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--cfg", type=float, default=None)
    ap.add_argument("--sampler", default=None)
    ap.add_argument("--scheduler", default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--prefix", default="images/gen")
    ap.add_argument("--unet", default=None)
    ap.add_argument("--clip", default=None)
    ap.add_argument("--vae", default=None)
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--out", default=None, help="optional folder to copy the finished image into")
    ap.add_argument("--lora", action="append", default=None, help="LoRA file[:strength], repeatable (e.g. afu_qwen21.safetensors:1.0)")
    ap.add_argument("--backend", choices=("auto", "codex", "img25", "local"), default=os.environ.get("IMAGE_BACKEND", "auto"),
                    help="auto = Codex CLI if usable, else Image 2.5 API if a key is found (default); codex; img25; local = ComfyUI")
    a = ap.parse_args()

    name = "qwen21-unc" if a.uncensored else a.model
    p = dict(PRESETS[name])
    if a.unet: p["unet"] = a.unet
    if a.clip: p["clip"] = a.clip
    if a.vae: p["vae"] = a.vae
    dw, dh = p.get("size", (1024, 1024))
    a.width, a.height = a.width or dw, a.height or dh
    a.steps = a.steps if a.steps is not None else p["steps"]
    a.cfg = a.cfg if a.cfg is not None else p["cfg"]
    a.sampler = a.sampler or p["sampler"]
    a.scheduler = a.scheduler or p["scheduler"]

    if a.prompt_file:
        prompt = Path(a.prompt_file).read_text(encoding="utf-8").strip()
    elif a.prompt:
        prompt = a.prompt
    else:
        raise SystemExit("need --prompt or --prompt-file")

    local_only = bool(a.lora) or a.uncensored or name.startswith("krea") or name.endswith("-unc")
    cx = None
    if a.backend == "auto" and not local_only:
        cx, why = codex_available()
        if cx:
            a.backend = "codex"
        elif has_openai_key():
            print(f"[auto] Codex CLI not usable ({why}) -> Image 2.5 API", flush=True)
            a.backend = "img25"
        else:
            raise SystemExit(f"[auto] no OpenAI image backend: Codex CLI not usable ({why}) and no API key (OPENAI_API_KEY / "
                             f"OPENAI_KEY_FILE / ~/.openai.env). Or rerun the whole film with IMAGE_BACKEND=local")
    elif a.backend == "codex" and not local_only:
        cx, why = codex_available()
        if why:
            raise SystemExit(f"[codex] not usable: {why}")
    if a.backend == "codex" and not local_only:
        if gen_codex(a, prompt, cx):
            return
        raise SystemExit("[codex] failed - stopped (no automatic switch to the API or local Qwen). Check `codex login status` "
                         "/ subscription quota, or rerun the whole film with IMAGE_BACKEND=img25 or local")
    if a.backend == "img25" and not local_only:
        if gen_img25(a, prompt):
            return
        if os.environ.get("IMAGE_FALLBACK", "0") != "1":
            raise SystemExit("[img25] failed - stopped (no automatic switch to local Qwen). Fix the key/API, "
                             "or rerun the whole film with IMAGE_BACKEND=local (IMAGE_FALLBACK=1 = old auto fall-back)")
        print("[img25] falling back to local ComfyUI", flush=True)
    print("[backend] local", flush=True)
    ensure_server(a.host)
    graph = build(a, p, prompt)
    res = _req(a.host, "/prompt", {"prompt": graph})
    pid = res["prompt_id"]
    print(f"[queued] prompt_id={pid} model={name} {a.width}x{a.height} steps={a.steps} cfg={a.cfg} "
          f"seed={a.seed} refs={len(a.ref or [])}", flush=True)

    t0 = time.time()
    while True:
        time.sleep(2)
        h = _req(a.host, f"/history/{pid}")
        if pid in h:
            entry = h[pid]
            status = entry.get("status", {})
            print(f"[status] {status.get('status_str')} wall={time.time() - t0:.1f}s", flush=True)
            if status.get("status_str") == "error":
                print(json.dumps(status, ensure_ascii=False, indent=2)[:4000])
                return
            for node_id, o in entry.get("outputs", {}).items():
                for f in o.get("images", []) or []:
                    path = comfy_paths.output_dir(a.host) / f.get("subfolder", "") / f.get("filename", "")
                    print(f"[out] {path}")
                    if a.out:
                        dest = Path(a.out)
                        dest.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, dest / path.name)
                        print(f"[copy] {dest / path.name}")
            print(f"[done] total {time.time() - t0:.1f}s")
            return


if __name__ == "__main__":
    main()
