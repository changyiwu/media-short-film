"""RTX Spark（Windows on Arm＋統一記憶體）相容性檢查。只用 Python 標準函式庫。

兩種用法：
  python setup/spark_check.py --wheels     任何電腦都能跑：到 PyPI 查 setup/env/ 每個鎖定套件有沒有 Windows ARM64 可用的 wheel
  python setup/spark_check.py              在 RTX Spark 筆電上跑：再加上系統、Python 架構、顯卡驅動、PyTorch CUDA 檢查
  （加 --torch-python C:\\AI\\H3\\venv\\Scripts\\python.exe 可指定要檢查 PyTorch 的 venv）

wheel 分類：
  ok        有 win_arm64 wheel 或純 Python wheel（py3-none-any）
  build     只有原始碼（sdist），要在 ARM64 上自己編，可能失敗
  missing   PyPI 上沒有這個版本可用於 Windows ARM64（例如只有 win_amd64 wheel）
  special   torch 家族等要從 NVIDIA 預覽索引另外裝，或是本機 x64 專用工具，見 docs/hardware_rtxspark.md
"""
import argparse
import json
import platform
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
ENV = ROOT / "env"
NV_TORCH_INDEX = "https://pypi.nvidia.com/nvtorch_oot_nightly"
# 要從 NVIDIA 預覽索引裝、或在 ARM64 上有替代做法的套件
SPECIAL = {
    "torch": "從 NVIDIA 預覽索引裝（" + NV_TORCH_INDEX + "）",
    "torchvision": "同 torch",
    "torchaudio": "同 torch",
    "triton-windows": "3.8.0.post28 起 PyPI 有 win_arm64 wheel（2026-10-14 查），但 NVIDIA 預覽版 CUDA 上未驗證；先不裝（ComfyUI 不用 torch.compile 即可），上機穩定後再試",
    "onnxruntime-gpu": "沒有 ARM64 CUDA 版時改裝 onnxruntime（CPU）",
    "opencv-python-headless": "PyPI 沒有 win_arm64 wheel（2026-10-31 查）；先不裝，只影響 tools/face_count.py，make_film.py 會提醒改人工看",
}
# NVIDIA 有些套件在 PyPI 只放 wheel-stub 空殼（sdist），真正的 wheel 在這個索引（例：nvidia-vfx 0.2.0.0 起有 win_arm64）
NV_INDEX = "https://pypi.nvidia.com"


def nv_index_wheels(name):
    """pypi.nvidia.com 上這個套件的 wheel 檔名（查不到回傳空清單）。"""
    try:
        with urllib.request.urlopen(f"{NV_INDEX}/{name.lower().replace('_', '-')}/", timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception:
        return []
    return sorted(set(re.findall(r"[A-Za-z0-9_.\-]+\.whl", html)))


def parse_req(path):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = re.match(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?\s*==\s*([^\s;]+)", line)
        if m:
            out.append((m.group(1), m.group(2)))
        elif " @ " in line:
            out.append((line.split(" @ ", 1)[0].strip(), "url"))
    return out


def arm64_fits(fn, py):
    """win_arm64 wheel 檔名是否符合這個 Python 版本（cpXY、abi3 或 py3）。"""
    return fn.endswith("win_arm64.whl") and (f"-cp{py.replace('.', '')}-" in fn or "-abi3-" in fn or "-py3-" in fn)


def classify(name, ver, py="3.12"):
    key = name.lower().replace("_", "-")
    if key in SPECIAL:
        return "special", SPECIAL[key]
    if ver == "url":
        return "build", "直接指向原始碼網址，要在 ARM64 上建置"
    base = ver.split("+", 1)[0]
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{base}/json", timeout=30) as r:
            files = json.load(r)["urls"]
    except Exception as e:
        return "missing", f"PyPI 查不到 {base}（{type(e).__name__}）"
    wheels = [f["filename"] for f in files if f["filename"].endswith(".whl")]
    if any(arm64_fits(w, py) for w in wheels):
        return "ok", "win_arm64 wheel"
    if any(w.endswith("-none-any.whl") for w in wheels):
        return "ok", "純 Python wheel"
    stem = name.lower().replace("-", "_") + "-" + base + "-"
    if any(w.lower().startswith(stem) and arm64_fits(w, py) for w in nv_index_wheels(name)):
        return "ok", f"win_arm64 wheel（{NV_INDEX}；PyPI 上的 sdist 會自動去那裡抓）"
    if any("win_arm64" in w for w in wheels):
        return "missing", f"有 win_arm64 wheel 但沒有 Python {py} 版：" + ", ".join(sorted({w.split("-")[2] for w in wheels if "win_arm64" in w}))
    if any(f["packagetype"] == "sdist" for f in files):
        return "build", "只有原始碼，要在 ARM64 上編譯"
    tags = sorted({w.rsplit("-", 1)[-1][:-4] for w in wheels})
    return "missing", "只有 " + ", ".join(tags[:4])


def arm64_version(name, py, orig=None):
    """PyPI 上有 win_arm64（且符合 Python 版本）或純 Python wheel 的最新正式版。
    給 orig 時只接受同一個大版號（避免跳到 pydantic-core 0.0.1 這種古早空殼版；2026-10-14 實際發生過）。"""
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=30) as r:
            rel = json.load(r)["releases"]
    except Exception:
        return None
    def key(v):
        return [int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", v)]
    tag = "cp" + py.replace(".", "")
    major = orig.split(".", 1)[0] if orig and orig != "url" else None
    for v in sorted((v for v in rel if re.fullmatch(r"[\d.]+", v) and (major is None or v.split(".", 1)[0] == major)), key=key, reverse=True):
        for f in rel[v]:
            fn = f["filename"]
            if fn.endswith("-none-any.whl") or (fn.endswith("win_arm64.whl") and (f"-{tag}-" in fn or "-abi3-" in fn)):
                return v
    return None


def emit(report):
    out = ENV / "arm64"; out.mkdir(exist_ok=True)
    for req, r in report.items():
        py = "3.12"
        fix = {}
        for p in r["problems"]:
            if p["status"] == "special":
                fix[p["pkg"].lower()] = f"# {p['pkg']}：{p['note']}"
            else:
                v = None if p["ver"] == "url" else arm64_version(p["pkg"], py, p["ver"].split("+", 1)[0])   # 指向原始碼網址的照原樣建置
                if v:
                    fix[p["pkg"].lower()] = f"{p['pkg']}=={v}  # ARM64：原本 {p['ver']}"
                elif p["status"] == "build":   # 沒有 ARM64 wheel：保留原釘選，安裝時現場建置（純 Python 套件通常沒問題）
                    fix[p["pkg"].lower()] = None
                else:
                    fix[p["pkg"].lower()] = f"# TODO {p['pkg']}=={p['ver']}：{p['note']}"
        lines = [f"# 由 setup/spark_check.py --emit 從 {req} 產生（Python {py}，Windows ARM64）。不要手改，改原清單後重產。"]
        for line in (ENV / req).read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([A-Za-z0-9_.\-]+)", line.strip())
            k = m.group(1).lower() if m else None
            lines.append(fix.get(k) or line)
        (out / req.replace(".txt", "_arm64.txt")).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[emit] {out / req.replace('.txt', '_arm64.txt')}", file=sys.stderr)


def wheel_scan():
    report = {}
    for req in sorted(ENV.glob("requirements_*.txt")):
        pkgs = parse_req(req)
        py = "3.12"     # 與 emit() 相同
        with ThreadPoolExecutor(16) as ex:
            res = list(ex.map(lambda p: (p[0], p[1], *classify(p[0], p[1], py)), pkgs))
        bad = [r for r in res if r[2] != "ok"]
        report[req.name] = dict(total=len(res), ok=len(res) - len(bad),
                                problems=[dict(pkg=n, ver=v, status=s, note=t) for n, v, s, t in bad])
    return report


def system_check(torch_python):
    info = dict(os=platform.platform(), machine=platform.machine(),
                python=f"{platform.python_version()} ({platform.machine()})")
    if platform.machine().upper() not in ("ARM64", "AARCH64"):
        info["warning"] = "這不是 ARM64 電腦（或目前的 Python 是 x64 模擬版）。RTX Spark 上要用原生 ARM64 Python。"
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        info["nvidia_smi"] = out or "沒有輸出"
    except Exception as e:
        info["nvidia_smi"] = f"無法執行：{e}"
    if torch_python:
        code = ("import torch,json;ok=torch.cuda.is_available();"
                "p=torch.cuda.get_device_properties(0) if ok else None;"
                "f,t=torch.cuda.mem_get_info() if ok else (0,0);"
                "print(json.dumps(dict(torch=torch.__version__,cuda=ok,device=p.name if p else None,"
                "capability=f'{p.major}.{p.minor}' if p else None,"
                "gpu_total_gb=round(t/2**30,1),gpu_free_gb=round(f/2**30,1))))")
        r = subprocess.run([torch_python, "-c", code], capture_output=True, text=True, timeout=300)
        info["torch"] = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else (r.stderr.strip()[-500:] or "失敗")
    try:
        ff = subprocess.run(["ffmpeg", "-hide_banner", "-buildconf"], capture_output=True, text=True, timeout=20).stdout
        info["ffmpeg"] = "aarch64／arm64 原生" if re.search(r"aarch64|arm64", ff) else ("x64（模擬執行，可用但較慢）" if ff else "找不到")
    except Exception:
        info["ffmpeg"] = "找不到"
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wheels", action="store_true", help="只做 PyPI wheel 檢查")
    ap.add_argument("--torch-python", help="要檢查 PyTorch CUDA 的 python.exe")
    ap.add_argument("--out", help="把結果另存成 JSON")
    ap.add_argument("--emit", action="store_true", help="產生 setup/env/arm64/ 的 ARM64 需求清單")
    a = ap.parse_args()
    result = {}
    if not a.wheels:
        result["system"] = system_check(a.torch_python)
    result["wheels"] = wheel_scan()
    if a.emit:
        emit(result["wheels"])
    text = json.dumps(result, ensure_ascii=False, indent=1)
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
