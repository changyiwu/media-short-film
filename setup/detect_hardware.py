"""偵測這台電腦的顯卡、記憶體、硬碟，告訴你該用上游四個硬體版本 repo 的哪一個（本專案＝16GB VRAM + 64GB RAM 版；RTX Spark 等 Windows on Arm 筆電另有設定），以及每個元件建議在本機還是雲端（Colab）跑。
只用 Python 標準函式庫，任何 Python 3.10+ 都能跑（Windows／Linux／macOS）。
python setup/detect_hardware.py"""
import ctypes
import json
import platform
import shutil
import subprocess
import sys
for _s in (sys.stdout, sys.stderr):                 # 中文輸出在非 UTF-8 主控台不變亂碼
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPOS = [
    ("shanshiba-workflow-32gvram-64gram", 30, 60, "32GB VRAM + 64GB RAM（完整版）"),
    ("shanshiba-workflow-16gvram-64gram", 15, 60, "16GB VRAM + 64GB RAM"),
    ("shanshiba-workflow-16gvram-32gram", 15, 30, "16GB VRAM + 32GB RAM"),
]
COLAB = "shanshiba-workflow-colab（本機跑不動 H3：H3 送 Google Colab G4 跑；需要 Google AI 方案或 Colab 運算單元）"


def gpu():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=20).stdout.strip().splitlines()
        name, mib, drv = [x.strip() for x in out[0].split(",")]
        if not mib.isdigit():                       # 統一記憶體（RTX Spark）nvidia-smi 可能回 [N/A]
            return dict(name=name, vram_gb=0, driver=drv, unified=True)
        return dict(name=name, vram_gb=round(int(mib) / 1024, 1), driver=drv)
    except Exception as e:
        return dict(error=f"nvidia-smi not available: {e}")


def ram_gb():
    if platform.system() != "Windows":
        try:
            if platform.system() == "Darwin":
                total = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout)
                avail = total
            else:
                info = dict(l.split(":", 1) for l in open("/proc/meminfo"))
                total = int(info["MemTotal"].split()[0]) * 1024; avail = int(info["MemAvailable"].split()[0]) * 1024
            return dict(total_gb=round(total / 2**30, 1), available_now_gb=round(avail / 2**30, 1), commit_limit_gb=round(total / 2**30, 1))
        except Exception:
            return dict(total_gb=0, available_now_gb=0, commit_limit_gb=0)

    class M(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    m = M(); m.dwLength = ctypes.sizeof(M)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return dict(total_gb=round(m.ullTotalPhys / 2**30, 1), available_now_gb=round(m.ullAvailPhys / 2**30, 1),
                commit_limit_gb=round(m.ullTotalPageFile / 2**30, 1))


def is_arm64():
    """原生 ARM64，或 x64 Python 在 Windows on Arm 上模擬執行（此時 platform.machine() 會回 AMD64）。"""
    import os
    m = platform.machine().upper()
    ident = (os.environ.get("PROCESSOR_IDENTIFIER", "") + os.environ.get("PROCESSOR_ARCHITEW6432", "")).upper()
    return m in ("ARM64", "AARCH64") or "ARM" in ident


def spark_plan(g, r):
    """RTX Spark（Windows on Arm＋統一記憶體）：見 docs/hardware_rtxspark.md。"""
    emulated = platform.machine().upper() not in ("ARM64", "AARCH64")
    info = {
        "recommendation": "本專案的 RTX Spark 設定：call configs/profile_rtxspark.cmd（未實測，先讀 docs/hardware_rtxspark.md）",
        "plan": {
            "劇本／剪接／字幕（CPU）": "本機",
            "首幀": "OpenAI Image 2.5（預設，雲端，不吃筆電記憶體）；備選本機 Qwen-Image（要先裝好 NVIDIA 預覽版 PyTorch）",
            "H3 影片": "本機先試；失敗或太慢 → H3_BACKEND=colab",
            "配音（VoxCPM2，預設引擎：聲音設計＋台詞）": "先試本機（soxr 要現場編譯、附參考音克隆有 torchcodec 風險）；不行改雲端或桌機",
            "聽寫校對（ASR）": "本機 openai-whisper（ctranslate2 沒有 Windows ARM64 版，stt.py 會自動改用）；不行改雲端或桌機",
            "放大": "先用 UPSCALE=lanczos；RTX VSR（nvidia-vfx 0.2.0.0 有 win_arm64 版）照 docs/hardware_rtxspark.md 第一次上機 6b 驗證後改 rtxvsr",
        },
        "notes": ["下一步：python setup/spark_check.py（檢查 Python 架構、驅動、PyTorch CUDA、各套件 ARM64 wheel）"],
    }
    if emulated:
        info["notes"].insert(0, "目前的 Python 是 x64 模擬版：請改裝原生 ARM64 Python 3.12（python.org 的 ARM64 installer 或 uv python install cpython-3.12-windows-aarch64）")
    # 64GB 機種可在驅動／BIOS 切出固定的 GPU 專用記憶體（例如 32＋32）：Windows 只回報剩下的系統部分，要加回 nvidia-smi 的專用 VRAM
    vram = g.get("vram_gb", 0)
    total = round(r["total_gb"] + vram, 1)
    info["memory"] = dict(system_gb=r["total_gb"], gpu_dedicated_gb=vram, total_gb=total)
    if vram:
        info["notes"].append(f"記憶體切分：系統 {r['total_gb']}GB＋GPU 專用 {vram}GB＝{total}GB（見 docs/hardware_rtxspark.md〈記憶體切分〉）")
    if total < 60:
        info["notes"].append(f"總記憶體只有 {total}GB（系統＋GPU）：H3 需要約 45–50GB，建議 64GB 以上")
    return info


def main():
    g, r = gpu(), ram_gb()
    disk = shutil.disk_usage("C:\\" if platform.system() == "Windows" else "/")
    info = dict(os=platform.platform(), gpu=g, ram=r, disk_C_free_gb=round(disk.free / 2**30))
    if is_arm64() or g.get("unified") or any(k in g.get("name", "") for k in ("Spark", "N1X", "GB10")):
        info.update(spark_plan(g, r))
        print(json.dumps(info, ensure_ascii=False, indent=1))
        return
    vram = g.get("vram_gb", 0); ram = r["total_gb"]
    pick = next((x for x in REPOS if vram >= x[1] and ram >= x[2]), None)
    info["recommendation"] = f"{pick[0]}（{pick[3]}）" if pick else COLAB
    # 每個元件在哪跑（cloud/colab_h3.py；make_film.py 的 H3_BACKEND 不設時也用同一個判斷）
    nv = "error" not in g
    info["plan"] = {
        "劇本／剪接／字幕（CPU）": "本機",
        "首幀": "OpenAI Image 2.5（預設，不用顯卡，要 OPENAI_API_KEY）" + ("" if vram < 12 else "；備選本機 Qwen-Image"),
        "配音（VoxCPM2／whisper）":"本機" if nv and vram >= 8 else "雲端（cloud/colab_h3.py full-setup）",
        "H3 影片": "本機" if pick else "雲端 G4（cloud/colab_h3.py batch …）",
        "全部都跑不動時": "全雲端：python cloud/colab_h3.py full-setup，再 film／smoke",
    }
    notes = []
    if vram >= 30 and ram < 60:
        notes.append("32GB 顯卡但記憶體不到 64GB：用 16gvram-32gram 的設定（--reserve-vram 不需要，但記憶體規則照它）")
    if r["available_now_gb"] < ram - 14:
        notes.append(f"目前常駐程式已用掉 {ram - r['available_now_gb']:.0f}GB；生成影片時請關掉瀏覽器等大程式")
    if disk.free / 2**30 < 250:
        notes.append("C 槽剩不到 250GB：模型約 145GB，加上工作檔與分頁檔會不夠")
    if "error" not in g and not any(k in g["name"] for k in ("RTX 50", "RTX 40", "RTX 30")):
        notes.append("顯卡不是 RTX 30／40／50 系列：comfy kitchen、RTX VSR 可能不支援，未驗證")
    info["notes"] = notes
    print(json.dumps(info, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
