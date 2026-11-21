"""本機＋區網其他電腦＋Colab 一起跑 H3（H3_REMOTES／H3_BACKEND=both）。

區網工作機（H3_REMOTES="http://192.168.1.20:8188 ..."，2026-11-21 起）：
  另一台同規格電腦只要開著 ComfyUI（COMFY_LISTEN=0.0.0.0 跑 tools\\start_comfy.cmd、防火牆放行 8188），不用同步片子資料夾。
  每台一個工人，和本機一樣從佇列前面一支一支拿；h3_shot.py 對遠端位址自動改成「上傳素材、跑完下載逐格 PNG 回本機壓 clip.mp4」。
  開跑前檢查每台連得到、模型（H3 主模型、文字編碼器、DMAD LoRA）都在，缺了就不派給它。
  同一台連續失敗 2 次就不再派（多半是對方 ComfyUI 關了或當機），失敗的鏡頭放回佇列。

2026-10-11 第一次實戰（〈收假圖鑑〉直式 34 鏡、3370 格、DMAD 4 步，本機 RTX 5090＋Colab G4，HYBRID_CHUNK=8）：
  **17.9 分鐘**完成（本機 15 支、雲端 19 支、失敗 0），推算全部本機 32.6 分鐘 → **省 45%**；Colab 花 1.97 單元（含開機、關機）。
  Colab 開機 216 秒（這段時間本機先做了 4 支）；每批 8 支約 304–314 秒，其中上傳、解壓、輪詢、下載約 70 秒。
  依這次踩的坑改了：每批預設 8 支、輪詢 15 秒（colab_h3.py）、佇列快空時依兩邊速度估算雲端該拿幾支（避免本機做完還在等雲端）、
  關機放背景不算進等待、本機工具路徑可用 HYBRID_TOOLS 指定。

做法：所有鏡頭放進同一個佇列，兩個工人同時拿：
  - 本機：從佇列「前面」一支一支拿，用本機 ComfyUI（h3_shot.py）跑。開跑不用等。
  - 雲端：先開 Colab G4（只裝 ComfyUI＋H3，約 3.5 分鐘，這段時間本機已經在跑），開好後每次從佇列「後面」拿一批交給
    colab_h3.py batch（上傳 → 跑 → 下載回每個鏡頭的資料夾），做完再拿下一批。
    批次大小：佇列還多時拿 HYBRID_CHUNK 支；快空時用實測速度估算——讓「雲端這批做完」和「本機做完剩下的」差不多同時，
    算出來少於 2 支就不再派雲端（只剩 0–1 支時本機做比較快）。
  - 雲端失敗的鏡頭放回佇列給本機重跑；佇列空了就在背景關掉 Colab（HYBRID_KEEP=1 則不關，審片後要重抽可以接著用）。
接力鏡頭（spec 有 first_clip，要用上一鏡的結尾）等兩邊都做完、上一鏡一定已經在了，才由本機照順序跑。
鏡頭太少（< HYBRID_MIN，預設 8）不值得等雲端開機 → 全部本機跑。

用法：python cloud/hybrid_h3.py work/h3/S01 work/h3/S02 …   （每個資料夾要有 spec.json；成品 clip.mp4 寫回同一個資料夾）
      加 --no-cloud 只用本機＋區網；--check 只檢查 H3_REMOTES 每台能不能用。
      三個範本設 H3_BACKEND=both（含 Colab），或本機模式下有設 H3_REMOTES（不含 Colab），會自動呼叫 run_hybrid()。
環境變數：H3_REMOTES（區網 ComfyUI 位址，空白或逗號分隔，可省略 http:// 與 :8188）、HYBRID_CHUNK（雲端每批最多幾支，預設 8）、HYBRID_MIN（少於幾支就不開雲端，預設 8）、HYBRID_KEEP=1（做完不關 Colab）、
          HYBRID_TOOLS（本機 h3_shot.py 所在資料夾，預設 repo 的 tools/）、COLAB_NAME（Colab session 名稱，預設 h3）。
中途要停：本機要連 h3_shot.py 子程序與 ComfyUI 佇列一起清（POST /queue {"clear": true} 與 POST /interrupt）；
          停掉這支程式後 Colab 上的批次還在算，要另外 python cloud/colab_h3.py stop。"""
import collections
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AI_ROOT = Path(os.environ.get("AI_ROOT", "C:/AI"))
PYH3_DEFAULT = os.environ.get("PY_H3") or AI_ROOT / "H3" / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
LOCAL_SEC, CLOUD_SEC, CLOUD_OVERHEAD = 62.0, 30.0, 70.0     # 起始估計（2026-10-11 實測：本機每支約 62 秒；雲端 2 個 ComfyUI 平均每支約 30 秒＋每批約 70 秒耗損）


def _log(msg):
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


def _relay(d):
    try:
        return "first_clip" in json.loads((Path(d) / "spec.json").read_text(encoding="utf-8"))
    except Exception:
        return False


def remotes_from_env():
    """H3_REMOTES → ['http://192.168.1.20:8188', ...]（補 http:// 與預設埠 8188）。"""
    out = []
    for h in re.split(r"[\s,]+", os.environ.get("H3_REMOTES", "").strip()):
        if not h:
            continue
        h = h.rstrip("/")
        if "://" not in h:
            h = "http://" + h
        if not re.search(r":\d+$", h):
            h += ":8188"
        out.append(h)
    return out


def _get(host, path, timeout=8):
    with urllib.request.urlopen(host + path, timeout=timeout) as f:
        return json.loads(f.read().decode())


def check_remote(host, dirs=()):
    """回傳 None＝可以用，否則回傳原因。檢查連線與這批鏡頭要用到的模型（名稱跟 h3_shot.py 同一套環境變數）。"""
    try:
        st = _get(host, "/system_stats")
    except Exception as e:
        return f"連不上（{e}）：對方要用 COMFY_LISTEN=0.0.0.0 跑 tools\\start_comfy.cmd，並在防火牆放行 8188"
    need = {"diffusion_models": {os.environ.get("H3_UNET", "minimax_h3_ref2va_pruned_int8_convrot.safetensors")},
            "text_encoders": {os.environ.get("H3_CLIP", "qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors")}, "loras": set()}
    for d in dirs:
        try:
            sp = json.loads((Path(d) / "spec.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        if sp.get("draft"):
            need["loras"].add("dmad_h3_4step_lora_critic_comfy.safetensors")
        for lr in (sp.get("lora") if isinstance(sp.get("lora"), list) else [sp["lora"]] if sp.get("lora") else []):
            need["loras"].add(lr["name"])
    miss = []
    for folder, names in need.items():
        if not names:
            continue
        try:
            have = {n.replace("\\", "/") for n in _get(host, f"/models/{folder}")}
        except Exception as e:
            return f"讀不到模型清單 /models/{folder}（{e}）"
        miss += [f"{folder}/{n}" for n in names if n.replace("\\", "/") not in have]
    if miss:
        return "缺模型：" + "、".join(miss) + "（兩台的 configs\\profile.cmd 要選同一種文字編碼器）"
    vram = (st.get("devices") or [{}])[0].get("vram_total", 0) / 2**30
    if vram and vram < 15:
        return f"顯存只有 {vram:.1f}GB，跑不動 H3"
    return None


def cloud_take(rem, chunk, local_sec, cloud_sec, overhead=CLOUD_OVERHEAD):
    """佇列剩 rem 支時雲端這批該拿幾支：讓 max(本機做完剩下的, 雲端這批做完) 最小。回傳 0／1 代表不值得派雲端。"""
    best_n, best_t = 0, rem * local_sec
    for n in range(1, min(chunk, rem) + 1):
        t = max((rem - n) * local_sec, overhead + n * cloud_sec)
        if t < best_t:
            best_n, best_t = n, t
    return best_n


def run_hybrid(dirs, pyh3=None, tools=None, cloud=True):
    """dirs：鏡頭資料夾（各有 spec.json）。cloud=False 不開 Colab（只用本機＋H3_REMOTES）。
    回傳沒做出 clip.mp4 的資料夾清單（空＝全部成功）。"""
    pyh3 = str(pyh3 or PYH3_DEFAULT); tools = Path(tools or os.environ.get("HYBRID_TOOLS") or REPO / "tools")
    dirs = [Path(d) for d in dirs]
    if not dirs:
        return []
    chunk = int(os.environ.get("HYBRID_CHUNK", "8")); nmin = int(os.environ.get("HYBRID_MIN", "8"))
    name = os.environ.get("COLAB_NAME", "h3"); keep = os.environ.get("HYBRID_KEEP") == "1"
    relay = [d for d in dirs if _relay(d)]                          # 最後才由本機照順序跑
    shared = collections.deque(d for d in dirs if d not in relay)
    remotes = []
    for h in remotes_from_env():
        why = check_remote(h, dirs)
        _log(f"[hybrid] 區網 {h}：" + (why or "可以用"))
        if not why:
            remotes.append(h)
    remotes = remotes[:max(0, len(shared) - 1)]                     # 鏡頭比工人少時不必每台都派
    lock = threading.Lock(); stats = collections.Counter(); cloud_on = cloud and len(shared) >= nmin
    speed = {"local": [], "cloud": []}                              # 實測秒數，用來估算尾巴該怎麼分
    lan_alive = [len(remotes)]                                      # 還在接單的區網工作機台數（估算雲端該拿幾支用）
    t0 = time.time()
    who = "本機" + (f"＋區網 {len(remotes)} 台" if remotes else "") + ("＋Colab" if cloud_on else "")
    _log(f"[hybrid] {len(dirs)} 鏡（接力鏡 {len(relay)} 支只在本機）；{who}一起跑"
         + ("" if cloud_on or not cloud else f"（少於 {nmin} 支不開 Colab）"))

    def avg(k, default):
        v = speed[k]
        return sum(v) / len(v) if v else default

    def local_worker(do_relay=False):
        while True:
            with lock:
                d = shared.popleft() if shared else (relay.pop(0) if do_relay and relay else None)
            if d is None:
                return
            if (d / "clip.mp4").exists():
                continue
            ts = time.time()
            r = subprocess.run([pyh3, str(tools / "h3_shot.py"), str(d / "spec.json"), "--out", str(d)])
            ok = r.returncode == 0 and (d / "clip.mp4").exists()
            with lock:
                stats["local"] += ok
                if ok:
                    speed["local"].append(time.time() - ts)
            _log(f"[hybrid] 本機 {d.name}: {'OK' if ok else 'FAIL'} {time.time() - ts:.0f}s")

    def remote_worker(host):
        fails = 0
        env = {**os.environ, "COMFY_HOST": host, "H3_REMOTE": "1"}
        try:
            while True:
                with lock:
                    d = shared.popleft() if shared else None
                if d is None:
                    return
                if (d / "clip.mp4").exists():
                    continue
                ts = time.time()
                r = subprocess.run([pyh3, str(tools / "h3_shot.py"), str(d / "spec.json"), "--out", str(d)], env=env)
                ok = r.returncode == 0 and (d / "clip.mp4").exists()
                with lock:
                    stats[host] += ok
                    if not ok:
                        shared.append(d)                            # 放回佇列後面（自己下一支先拿別的），本機或別台會接手
                _log(f"[hybrid] {host} {d.name}: {'OK' if ok else 'FAIL（放回佇列）'} {time.time() - ts:.0f}s")
                fails = 0 if ok else fails + 1
                if fails >= 2:
                    _log(f"[hybrid] {host} 連續失敗 2 次，不再派給它")
                    return
        finally:
            with lock:
                lan_alive[0] -= 1

    def colab(*args, wait=True):
        cmd = [sys.executable, str(REPO / "cloud" / "colab_h3.py"), "--name", name, *map(str, args)]
        return subprocess.run(cmd) if wait else subprocess.Popen(cmd)

    def cloud_worker():
        _log("[hybrid] 雲端開機中（只裝 H3，約 3.5 分鐘，本機先跑）")
        if colab("start", "--h3-only").returncode != 0:
            _log("[hybrid] Colab 開不起來 → 剩下的全部本機跑"); return
        try:
            while True:
                with lock:
                    rem = len(shared)
                    n = min(chunk, rem) if rem > 2 * chunk else cloud_take(rem, chunk, avg("local", LOCAL_SEC) / (1 + lan_alive[0]),
                                                                            avg("cloud", CLOUD_SEC))
                    if n < 2:                                       # 剩下的本機做比較快（不用上傳下載、不用等雲端）
                        return
                    batch = [shared.pop() for _ in range(n)]
                todo = [d for d in batch if not (d / "clip.mp4").exists()]
                if not todo:
                    continue
                _log(f"[hybrid] 雲端拿 {len(todo)} 支（佇列剩 {rem - n}）：{' '.join(d.name for d in todo)}")
                ts = time.time()
                colab("batch", *[d / "spec.json" for d in todo])
                back = [d for d in todo if not (d / "clip.mp4").exists()]
                done = len(todo) - len(back)
                with lock:
                    stats["cloud"] += done
                    shared.extend(back)                             # 失敗的放回佇列，本機會拿去做
                    if done:
                        speed["cloud"].append(max(1.0, (time.time() - ts - CLOUD_OVERHEAD) / done))
                if back:
                    _log(f"[hybrid] 雲端失敗 {len(back)} 支，放回佇列：{' '.join(d.name for d in back)}")
        finally:
            if keep:
                _log("[hybrid] HYBRID_KEEP=1：Colab 不關（閒置約 20 分鐘會被收回；用完記得 colab_h3.py stop）")
            else:
                _log("[hybrid] 背景關閉 Colab（不用等）")
                colab("stop", wait=False)

    th = ([threading.Thread(target=local_worker)] + [threading.Thread(target=remote_worker, args=(h,)) for h in remotes]
          + ([threading.Thread(target=cloud_worker)] if cloud_on else []))
    for t in th:
        t.start()
    for t in th:
        t.join()
    local_worker(do_relay=True)                                     # 雲端／區網最後放回來的失敗鏡頭＋接力鏡頭
    miss = [d for d in dirs if not (d / "clip.mp4").exists()]
    parts = [f"本機 {stats['local']} 支"] + [f"{h} {stats[h]} 支" for h in remotes] + ([f"雲端 {stats['cloud']} 支"] if cloud_on else [])
    _log(f"[hybrid] 完成 {time.time() - t0:.0f} 秒：{'、'.join(parts)}、失敗 {len(miss)} 支")
    return miss


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--check" in args:
        hs = remotes_from_env()
        if not hs:
            sys.exit("沒有設 H3_REMOTES")
        bad = 0
        for h in hs:
            why = check_remote(h, [a for a in args if a != "--check"])
            print(f"{h}：{why or '可以用'}"); bad += bool(why)
        sys.exit(1 if bad else 0)
    no_cloud = "--no-cloud" in args
    args = [a for a in args if a != "--no-cloud"]
    if not args:
        sys.exit(__doc__)
    sys.exit(1 if run_hybrid(args, cloud=not no_cloud) else 0)
