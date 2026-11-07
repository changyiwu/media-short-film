"""做片環境核對（只讀，不安裝、不下載）。只用 Python 標準函式庫，幾十秒跑完。

用法（任何 Python 3.10 以上都行，不必先跑 profile）：
  python setup/check_env.py                    依架構自動選 configs/profile.cmd 或 profile_rtxspark.cmd
  python setup/check_env.py --profile configs\\profile_rtxspark.cmd
  python setup/check_env.py --full-lock        Comfy Desktop 也比對整份 requirements_h3_venv.txt（只供參考）

核對內容（依據 AGENT_SETUP.md §2a、§2b、§2d、§3 與 setup/ 底下的清單）：
  1. H3 環境（PY_H3）：Comfy Desktop 只比 §2a 補裝的 7 個套件（其他歸 Desktop 管）；自建 C:\\AI\\H3 比整份鎖定清單
  2. 語音環境（PY_VOICE）：整份 requirements_voice_venv.txt
  3. Ming（MING_DIR，預設 %AI_ROOT%\\Ming）：ComfyUI 版本、節點 commit、torch 版本
  4. 自訂節點（setup/custom_nodes.txt）與 setup/comfy_nodes/whitemodel_color
  5. 模型：工具實際會載入的檔案，以及每份 setup/downloads*.json 的檔案大小（不算雜湊，要驗雜湊就跑 download.py）
  6. ComfyUI 版本（Desktop 會自動更新，可能洗掉補裝的套件或 FlashVSR）
ARM64（RTX Spark）改比 setup/env/arm64/ 的清單；筆電未測的項目（Ming、RTX VSR）算選用。

每項標「符合／不符合／未裝（選用）／略過」；必要項目有任何不符合時結束碼為 1。
Desktop 自動更新後先跑這支，有問題再照 AGENT_SETUP §2a 補，最後跑 smoke_test.py。
"""
import argparse
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SETUP = Path(__file__).resolve().parent
REPO = SETUP.parent
ARM = platform.machine().upper() in ("ARM64", "AARCH64")

# AGENT_SETUP §2a 第 1 步補進 Comfy Desktop .venv 的套件（版本照鎖定清單）
DESKTOP_ADDONS = ["nvidia-vfx", "gguf", "accelerate", "triton-windows", "numba", "llvmlite", "diffusers"]
DESKTOP_MIN_COMFY = (0, 37, 0)   # H3、Qwen-Image、Music 3、EasyCache 是 0.37.0 起的核心節點（custom_nodes.txt）
MING_COMFY = "v0.43.2"           # AGENT_SETUP §2d
MING_TORCH = "2.12.1"            # AGENT_SETUP §2d
H3_IMPORTS = "torch, nvvfx, gguf"                                            # §2a 的確認指令
VOICE_IMPORTS = "voxcpm, faster_whisper, audio_separator, stable_whisper, edge_tts"   # §2b 的確認指令

# 每份模型清單的用途。required: True＝做片必要；字串＝情境需要（缺了只在該情境會壞）；None＝選用
# Desktop 與自建分開（AGENT_SETUP §3）；"music3" 在 Desktop 由 MUSIC3_DIT 決定，見 manifest_need()
MANIFESTS = {
    "downloads.json":                 ("H3 主模型、NVFP4 文字編碼器、影音 VAE", {"desktop": "Desktop 範本可能已提供，以〈工具會載入的模型〉為準", "own": True}),
    "downloads_uncensored.json":      ("H3 文字編碼器 int8", {"desktop": None, "own": True}),
    "downloads_dmad.json":            ("DMAD 4 步 LoRA（原檔）", {"desktop": True, "own": True}),
    "downloads_qwen_image.json":      ("Qwen-Image 2.1（本機備選生圖；smoke_test、run_demo 會用）", {"desktop": "smoke_test.py、run_demo.py、IMAGE_BACKEND=local", "own": True}),
    "downloads_qwen_image_edit.json": ("Qwen-Image-Edit 2511（本機備選首幀）", {"desktop": "IMAGE_BACKEND=local 的首幀", "own": True}),
    "downloads_music3.json":          ("MiniMax Music 3（配樂）", {"desktop": True, "own": True}),
    "downloads_voxcpm2.json":         ("VoxCPM2（參考音設計、voxcpm2 配音）", {"desktop": True, "own": True}),
    "downloads_flashvsr.json":        ("FlashVSR v1.1（UPSCALE=flashvsr）", {"desktop": True, "own": True}),
    "downloads_ming.json":            ("Ming-3.0-TTS（旁白、fixed 台詞）", {"desktop": True, "own": True}),
    "downloads_qwen_asr.json":        ("Qwen3-ASR＋對齊模型", {"desktop": "饒舌對決（make_battle.py、pick_song.py）", "own": "饒舌對決（make_battle.py、pick_song.py）"}),
    "downloads_yue2.json":            ("YuE2 唱詞歌", {"desktop": "饒舌對決的歌", "own": "饒舌對決的歌"}),
    "downloads_funcontrol.json":      ("舞蹈骨架控制", {"desktop": "換角重製的骨架鏡", "own": "換角重製的骨架鏡"}),
    "downloads_whitemodel.json":      ("白模動作參考", {"desktop": "make_whitemodel.py", "own": "make_whitemodel.py"}),
    "downloads_acestep.json":         ("ACE-Step 1.5 XL 歌曲備案", {"desktop": None, "own": None}),
    "downloads_action_loras.json":    ("動作 LoRA", {"desktop": None, "own": None}),
    "downloads_unpruned.json":        ("H3 未剪枝主模型（A/B 測試）", {"desktop": None, "own": None}),
    "downloads_vae_int8.json":        ("H3 影片 VAE int8（A/B 測試）", {"desktop": None, "own": None}),
}

OK, BAD, OPT, SKIP = "符合", "不符合", "未裝（選用）", "略過"
results = []   # (區段, 項目, 狀態, 說明, 必要?)


def report(section, item, status, note="", required=True):
    results.append((section, item, status, note, required))
    mark = {OK: "  ok ", BAD: "  ✗  " if required else "  -  ", OPT: "  -  ", SKIP: "  ·  "}.get(status, "  ·  ")
    if status == BAD and not required:
        status = "不符合（非必要）"
    print(f"{mark}{item}：{status}" + (f"　{note}" if note else ""), flush=True)


def head(title):
    print(f"\n== {title} ==", flush=True)


# ---------- 環境變數 ----------
def load_profile(profile):
    """跑 profile.cmd，取回它設的環境變數（不是 Windows 就直接用目前環境）。"""
    if os.name != "nt":
        return dict(os.environ)
    r = subprocess.run(f'cmd /d /s /c "chcp 65001 >nul && call "{profile}" >nul && set"',
                       capture_output=True, shell=False)
    env = {}
    for line in r.stdout.decode("utf-8", errors="replace").splitlines():
        if "=" in line and not line.startswith("="):
            k, v = line.split("=", 1)
            env[k] = v
    if "PY_H3" not in env:
        sys.exit(f"跑 {profile} 沒有取得 PY_H3：{r.stderr.decode('utf-8', errors='replace')[-500:]}")
    return env


# ---------- 套件 ----------
DUMP = r'''
import json, sys, importlib, importlib.metadata as md
out = {"python": sys.version.split()[0], "dists": {}, "direct": {}, "imports": {}}
for d in md.distributions():
    n = d.metadata["Name"]
    if not n:
        continue
    k = n.lower().replace("_", "-")
    out["dists"][k] = d.version
    try:
        t = d.read_text("direct_url.json")
        if t:
            out["direct"][k] = json.loads(t).get("url")
    except Exception:
        pass
try:
    import torch
    out["torch"] = torch.__version__
    out["cuda"] = torch.cuda.is_available()
except Exception as e:
    out["torch_err"] = repr(e)
for m in [x.strip() for x in sys.argv[1].split(",") if x.strip()]:
    try:
        importlib.import_module(m)
        out["imports"][m] = None
    except Exception as e:
        out["imports"][m] = repr(e)[:200]
print("@@JSON@@" + json.dumps(out))
'''


def dump_env(py, imports=""):
    if not py or not Path(py).exists():
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(DUMP)
    try:
        r = subprocess.run([py, f.name, imports], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    finally:
        os.unlink(f.name)
    for line in r.stdout.splitlines():
        if line.startswith("@@JSON@@"):
            return json.loads(line[8:])
    return {"error": (r.stderr or r.stdout)[-800:]}


def norm(n):
    return n.lower().replace("_", "-")


def parse_req(path):
    req = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.split("#", 1)[0].strip() if " @ " not in line else line.strip()
        if not line:
            continue
        if " @ " in line:
            n, url = line.split(" @ ", 1)
            req[norm(n.strip())] = "@" + url.split("#")[0].strip()
        elif "==" in line:
            n, v = line.split("==", 1)
            req[norm(n.strip())] = v.split(";")[0].strip()
    return req


def req_file(kind):
    return SETUP / "env" / ("arm64" if ARM else "") / (f"requirements_{kind}_venv{'_arm64' if ARM else ''}.txt")


def compare_pkgs(section, env, req, names=None, required=True):
    """逐套件比版本；回傳 (符合數, 不符合列表)。"""
    names = names or sorted(req)
    good, bad = 0, []
    for k in names:
        if k not in req:
            report(section, k, SKIP, "鎖定清單沒有（ARM64 清單可能刻意不裝）", required)
            continue
        want, have = req[k], env["dists"].get(k)
        if want.startswith("@"):
            url = (env["direct"].get(k) or "").split("#")[0]
            if have is None:
                bad.append(f"{k}：沒裝（要 {want[1:]}）")
            elif url != want[1:]:
                bad.append(f"{k}：要 {want[1:]}，實際 {have}（{url or '不是從網址裝的'}）")
            else:
                good += 1
        elif have is None:
            bad.append(f"{k}：沒裝（要 {want}）")
        elif have != want:
            bad.append(f"{k}：要 {want}，實際 {have}")
        else:
            good += 1
    return good, bad


def env_summary(section, env, imports, required=True, cuda_required=True):
    if env is None:
        report(section, "Python", BAD, "找不到 python.exe", required)
        return False
    if "error" in env:
        report(section, "Python", BAD, "執行失敗：" + env["error"].strip().splitlines()[-1], required)
        return False
    note = f"python {env['python']}，torch {env.get('torch', '沒裝')}，cuda {env.get('cuda')}"
    if env.get("torch_err"):
        note += "，" + env["torch_err"]
    report(section, "torch／CUDA", OK if env.get("cuda") or not cuda_required else BAD, note, required)
    failed = {m: e for m, e in env["imports"].items() if e}
    if imports:
        report(section, f"import {imports}", BAD if failed else OK,
               "；".join(f"{m}: {e}" for m, e in failed.items()), required)
    return True


def check_h3(E, desktop, full_lock):
    sec = "H3 環境"
    head(f"{sec}（PY_H3 = {E.get('PY_H3')}）")
    imports = "torch, gguf" if ARM else H3_IMPORTS     # 筆電 RTX VSR 未測（profile_rtxspark 用 lanczos）
    env = dump_env(E.get("PY_H3"), imports)
    if not env_summary(sec, env, imports):
        return env
    req = parse_req(req_file("h3"))
    if desktop:
        good, bad = compare_pkgs(sec, env, req, DESKTOP_ADDONS)
        report(sec, f"§2a 補裝的 {len(DESKTOP_ADDONS)} 個套件", BAD if bad else OK, "；".join(bad) or f"{good} 個都等於鎖定版本")
        if full_lock:
            good, bad = compare_pkgs(sec, env, req)
            report(sec, "整份鎖定清單", "參考" if bad else OK,
                   f"{good} 個相同、{len(bad)} 個不同：" + "；".join(bad) if bad else "全部相同", required=False)
        hub = env["dists"].get("huggingface-hub")
        if hub and req.get("huggingface-hub") and hub != req["huggingface-hub"]:
            print(f"     （Desktop 的 huggingface_hub {hub} ≠ 鎖定 {req['huggingface-hub']}：AGENT_SETUP §2a 說不要自己升級，無害）")
        print(f"     （Desktop 的 torch {env.get('torch')} 由 Desktop 管，不跟鎖定清單比）")
    else:
        good, bad = compare_pkgs(sec, env, req)
        report(sec, f"整份鎖定清單 {req_file('h3').name}", BAD if bad else OK, "；".join(bad) or f"{good} 個都相同")
    return env


def check_voice(E):
    sec = "語音環境"
    head(f"{sec}（PY_VOICE = {E.get('PY_VOICE')}）")
    imports = VOICE_IMPORTS.replace("faster_whisper, ", "") if ARM else VOICE_IMPORTS   # ARM64 沒有 ctranslate2
    env = dump_env(E.get("PY_VOICE"), imports)
    if not env_summary(sec, env, imports):
        return
    req = parse_req(req_file("voice"))
    good, bad = compare_pkgs(sec, env, req)
    report(sec, f"鎖定清單 {req_file('voice').name}", BAD if bad else OK, "；".join(bad) or f"{good} 個都相同")
    extra = sorted(set(env["dists"]) - set(req))
    if extra:
        print("     清單外多裝的套件：" + "、".join(f"{k}=={env['dists'][k]}" for k in extra))


# ---------- ComfyUI 與節點 ----------
def git(path, *args):
    try:
        r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def comfy_version(path):
    f = Path(path) / "comfyui_version.py"
    if f.exists():
        m = re.search(r'"([^"]+)"', f.read_text(encoding="utf-8", errors="replace"))
        if m:
            return m.group(1)
    return git(path, "describe", "--tags", "--always").lstrip("v") or "?"


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def custom_nodes():
    rows = []
    for line in (SETUP / "custom_nodes.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            rows.append([x.strip() for x in line.split("|", 3)])
    return rows


def check_node(sec, base, name, commit, required, note_missing):
    p = Path(base) / "custom_nodes" / name
    if not p.exists():
        report(sec, name, BAD if required else OPT, note_missing, required)
        return
    h = git(p, "rev-parse", "--short=7", "HEAD")
    dirty = git(p, "status", "--porcelain", "--untracked-files=no")
    status = OK if h and h.startswith(commit[:7]) else BAD
    report(sec, name, status, f"要 {commit}，實際 {h or '不是 git 資料夾'}" + ("，有改過的檔案" if dirty else ""), required)


def check_comfy(E, desktop):
    sec = "ComfyUI 與節點"
    cd = Path(E["COMFY_DIR"])
    head(f"{sec}（COMFY_DIR = {cd}）")
    if not cd.exists():
        report(sec, "ComfyUI", BAD, "COMFY_DIR 不存在")
        return
    v = comfy_version(cd)
    report(sec, "Desktop ComfyUI 版本" if desktop else "ComfyUI 版本",
           OK if vtuple(v) >= DESKTOP_MIN_COMFY else BAD,
           f"{v}（需 ≥ {'.'.join(map(str, DESKTOP_MIN_COMFY))}）" + ("；Desktop 會自動更新，更新後重跑本檔" if desktop else ""))
    for name, _repo, commit, use in custom_nodes():
        if "Ming" in name:
            continue
        if "FlashVSR" in name:
            check_node(sec, cd, name, commit, True, "沒裝：UPSCALE=flashvsr 會壞（AGENT_SETUP §2a 第 2 步）")
        else:
            check_node(sec, cd, name, commit, False, use)
    src = SETUP / "comfy_nodes" / "whitemodel_color"
    dst = cd / "custom_nodes" / "whitemodel_color"
    if not dst.exists():
        report(sec, "whitemodel_color", OPT, "白模多人上色才要（make_whitemodel.py --colors）", False)
    else:
        same = all((dst / f.relative_to(src)).exists() and (dst / f.relative_to(src)).read_bytes() == f.read_bytes()
                   for f in src.rglob("*") if f.is_file() and "__pycache__" not in f.parts)
        report(sec, "whitemodel_color", OK if same else BAD, "與 repo 相同" if same else "與 repo 的版本不同，重新複製", False)


def check_ming(E):
    sec = "Ming"
    md = Path(E.get("MING_DIR") or Path(E.get("AI_ROOT", r"C:\AI")) / "Ming")
    head(f"{sec}（{md}）")
    required = not ARM    # 筆電未測：片子先設 voice_engine voxcpm2（AGENT_SETUP §2d）
    comfy = md / "ComfyUI"
    if not comfy.exists():
        report(sec, "Ming ComfyUI", BAD if required else OPT, "沒裝：旁白與 fixed 台詞（voice_engine 預設 ming）會停下", required)
        return
    v = comfy_version(comfy)
    report(sec, "ComfyUI 版本", OK if "v" + v.lstrip("v") == MING_COMFY else BAD, f"要 {MING_COMFY}，實際 v{v.lstrip('v')}", required)
    for name, _repo, commit, _use in custom_nodes():
        if "Ming" in name:
            check_node(sec, comfy, name, commit, required, "沒裝：Ming 節點不存在")
    env = dump_env(str(md / "venv" / "Scripts" / "python.exe") if os.name == "nt" else str(md / "venv" / "bin" / "python"))
    if env_summary(sec, env, "", required):
        t = (env.get("torch") or "").split("+")[0]
        report(sec, "torch 版本", OK if t == MING_TORCH else BAD, f"要 {MING_TORCH}，實際 {env.get('torch')}", required)


# ---------- 模型 ----------
def check_models(E, desktop):
    os.environ.update({k: E[k] for k in ("AI_ROOT", "COMFY_MODELS_DIR", "COMFY_DIR") if E.get(k)})
    for k in ("COMFY_MODELS_DIR", "COMFY_DIR"):
        if k not in E:
            os.environ.pop(k, None)
    sys.path.insert(0, str(SETUP))
    import download   # destination() 跟 download.py 同一套規則
    sec = "模型"

    def find(sub, name):
        cands = [download.destination({"destination": f"C:/AI/H3/models/{sub}/{name}"}),
                 download.destination({"destination": f"C:/AI/H3/ComfyUI-0.36.0/models/{sub}/{name}"})]
        return next((c for c in cands if c.exists()), None)

    head("工具會載入的模型（依 profile 的環境變數）")
    load = [("H3_UNET", "diffusion_models", E.get("H3_UNET", "minimax_h3_ref2va_pruned_int8_convrot.safetensors")),
            ("H3_CLIP", "text_encoders", E.get("H3_CLIP", "qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors")),
            ("H3_VIDEO_VAE", "vae", E.get("H3_VIDEO_VAE", "minimax_h3_video_vae_fp16.safetensors")),
            ("H3 音訊 VAE", "vae", "minimax_h3_audio_vae_fp32.safetensors"),
            ("DMAD LoRA（轉檔後）", "loras", "dmad_h3_4step_lora_critic_comfy.safetensors"),
            ("MUSIC3_DIT", "diffusion_models", E.get("MUSIC3_DIT", "minimax_music3_dit_int8_convrot.safetensors")),
            ("Music 3 文字編碼器", "text_encoders", "minimax_music3_text_encoder_pruned_int8_convrot.safetensors"),
            ("Music 3 VAE", "vae", "minimax_music3_dav.safetensors")]
    for label, sub, name in load:
        p = find(sub, name)
        report(sec, f"{label} = {name}", OK if p else BAD, f"{p.stat().st_size / 1e9:.2f} GB" if p else f"在 {sub} 找不到")
    vroot = Path(E.get("AI_ROOT", r"C:\AI")) / "Voice" / "models"
    report(sec, "VoxCPM2 設定檔（config.json）", OK if (vroot / "VoxCPM2" / "config.json").exists() else BAD,
           "" if (vroot / "VoxCPM2" / "config.json").exists() else "缺：跑 AGENT_SETUP §3 的 VoxCPM2 小檔 snapshot_download")
    if ARM:
        report(sec, "faster-whisper large-v3", SKIP, "ARM64 改用 openai-whisper", False)
    else:
        w = vroot / "whisper"
        has = w.exists() and any(w.rglob("model.bin"))
        report(sec, "faster-whisper large-v3", OK if has else BAD, "" if has else f"{w} 沒有 model.bin：跑 AGENT_SETUP §3 的 WhisperModel 下載")
    sep = vroot / "separator"
    report(sec, "BS-RoFormer 分軌模型", OK if sep.exists() and any(sep.iterdir()) else OPT,
           "" if sep.exists() else "第一次跑 audio-separator 會自動下載", False)

    head(f"模型清單 setup/downloads*.json（只比大小；{'Comfy Desktop' if desktop else '自建 C:/AI/H3'}）")
    for mf in sorted(SETUP.glob("downloads*.json")):
        desc, need = MANIFESTS.get(mf.name, ("（未分類）", {"desktop": None, "own": None}))
        need = need["desktop" if desktop else "own"]
        if mf.name == "downloads_music3.json" and desktop and E.get("MUSIC3_DIT"):
            need = f"已改用 Desktop 範本的 {E['MUSIC3_DIT']}（見上面）"
        if ARM and mf.name == "downloads_ming.json":
            need = "筆電未測，片子先設 voice_engine voxcpm2"
        items = json.loads(mf.read_text(encoding="utf-8-sig"))
        missing, wrong = [], []
        for it in items:
            p = download.destination(it)
            if not p.exists():
                part = p.with_name(p.name + ".verified-tmp").exists()
                missing.append(f"{it['name']}（{it['size'] / 1e9:.2f} GB）" + ("，有下載到一半的 .verified-tmp" if part else ""))
            elif p.stat().st_size != it["size"]:
                wrong.append(f"{it['name']} 大小 {p.stat().st_size} ≠ {it['size']}")
        label = f"{mf.name}（{desc}）"
        ok_n = len(items) - len(missing) - len(wrong)
        if not missing and not wrong:
            report(sec, label, OK, f"{ok_n}/{len(items)}", need is True)
        elif need is True:
            report(sec, label, BAD, f"{ok_n}/{len(items)}；缺 " + "、".join(missing + wrong))
        elif need is None and not wrong:
            report(sec, label, OPT, f"{ok_n}/{len(items)}", False)
        else:
            report(sec, label, BAD, f"{ok_n}/{len(items)}；缺 " + "、".join(missing + wrong) + f"；用途：{need}", False)


def main():
    ap = argparse.ArgumentParser(description="做片環境核對（只讀）")
    ap.add_argument("--profile", help="configs 底下的 profile（預設依架構自動選）")
    ap.add_argument("--full-lock", action="store_true", help="Comfy Desktop 也比對整份 H3 鎖定清單（只供參考）")
    a = ap.parse_args()
    profile = Path(a.profile) if a.profile else REPO / "configs" / ("profile_rtxspark.cmd" if ARM else "profile.cmd")
    if not profile.is_absolute() and not profile.exists():
        profile = REPO / profile
    E = load_profile(profile.resolve())
    cd, py = E.get("COMFY_DIR", ""), E.get("PY_H3", "")
    desktop = bool(E.get("COMFY_MODELS_DIR")) and py.lower().startswith(cd.lower())
    print(f"repo：{REPO}\nprofile：{profile.name}（{'ARM64' if ARM else 'x64'}，{'Comfy Desktop' if desktop else '自建 C:/AI/H3'}）")
    print("圖例：ok 符合　✗ 不符合（必要）　- 選用或情境需要　· 略過")
    check_h3(E, desktop, a.full_lock)
    check_voice(E)
    check_ming(E)
    check_comfy(E, desktop)
    check_models(E, desktop)

    head("結論")
    bad_req = [r for r in results if r[2] == BAD and r[4]]
    bad_opt = [r for r in results if r[2] == BAD and not r[4]]
    if bad_req:
        print(f"必要項目有 {len(bad_req)} 個不符合：")
        for s, i, _st, n, _r in bad_req:
            print(f"  - [{s}] {i}：{n}")
    else:
        print("做片必要項目全部符合。")
    if bad_opt:
        print(f"情境需要或選用、目前不符合的 {len(bad_opt)} 個（只有用到時才要補）：")
        for s, i, _st, n, _r in bad_opt:
            print(f"  - [{s}] {i}")
    sys.exit(1 if bad_req else 0)


if __name__ == "__main__":
    main()
