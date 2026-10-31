"""Ming-3.0-TTS 0.5B（inclusionAI，MIT）批次生成：旁白與 fixed 台詞的預設引擎（film.json 的 voice_engine，2026-10-31 起預設 "ming"），挑音照舊用 voice_pick.py。
改寫自上游 tools/make_ming.py（2026-10-29）。Ming 裝在獨立的 ComfyUI（預設 %AI_ROOT%\\Ming，8189 埠），不動 Comfy Desktop，見 AGENT_SETUP.md §2d。

執行（Voice venv）："%PY_VOICE%" <repo>\\tools\\ming_batch.py jobs.json，或 <repo>\\tools\\make_ming.cmd jobs.json（連挑音一起跑）
jobs.json 跟 voxcpm_batch.py 相同，差別是一定要有 ref_audio 與 ref_text（參考音逐字稿）：
{"out_dir": "voice/bv", "seeds": 8, "extra_seeds": 4,
 "jobs": [{"name": "line0", "text": "台詞", "ref_audio": "voice/ref_zhe.wav", "ref_text": "參考音念的字", "seeds": 8 (選填)}]}

送進模型前的文字處理同 voxcpm_batch.py（讀音替換表、數字轉國字、繁轉簡；Ming 餵繁體會念錯）。[Sigh]、[Laughter] 等行內標籤可寫在台詞裡。
聲音設計（角色參考音、旁白參考音）仍用 VoxCPM2；克隆模式不能下語氣指令。
Ming 會太早收尾：最後 60 ms 振幅太大的候選移到 cand_trunc/；整句都被截斷時句尾改「……」多抽 extra_seeds 支（檔名 _s101 起）。
跑完叫 ComfyUI 釋放顯存，讓 H3 可以接著跑。"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from hashlib import md5
from pathlib import Path

import numpy as np
import soundfile as sf

from tts_lexicon import load_lexicon
from voxcpm_batch import make_t2s, prep

AI = Path(os.environ.get("AI_ROOT", r"C:\AI"))
MING = Path(os.environ.get("MING_DIR", AI / "Ming"))
COMFY_DIR = MING / "ComfyUI"
PY = MING / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PORT = os.environ.get("MING_COMFY_PORT", "8189")
HOST = f"http://127.0.0.1:{PORT}"
TAIL = 0.05       # 最後 60 ms 最大振幅／全句峰值，超過算句尾被截斷


def api(path, data=None, timeout=30):
    r = urllib.request.Request(HOST + path, data=None if data is None else json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=timeout).read() or b"{}")


def ensure_comfy():
    try:
        api("/system_stats", timeout=4); return
    except Exception:
        pass
    if not PY.exists():
        sys.exit(f"找不到 Ming 環境 {PY}：照 AGENT_SETUP.md §2d 安裝，或 film.json 設 \"voice_engine\": \"voxcpm2\"")
    print(f"[ming] 啟動 ComfyUI（{COMFY_DIR}，{PORT} 埠）…", flush=True)
    log = open(MING / "comfy.log", "ab")
    flags = dict(creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else dict(start_new_session=True)
    subprocess.Popen([str(PY), "-X", "utf8", str(COMFY_DIR / "main.py"), "--listen", "127.0.0.1", "--port", PORT, "--disable-auto-launch",
                      "--preview-method", "none", "--cache-none", "--fast", "fp16_accumulation", "--reserve-vram", "1.5"],
                     cwd=str(COMFY_DIR), stdout=log, stderr=log, stdin=subprocess.DEVNULL, **flags)
    for i in range(90):
        time.sleep(2)
        try:
            api("/system_stats", timeout=4); print(f"[ming] ComfyUI 啟動完成（{(i + 1) * 2} 秒）", flush=True); return
        except Exception:
            pass
    sys.exit(f"[ming] ComfyUI 三分鐘內沒起來，看 {MING / 'comfy.log'}")


def gen_one(text, ref_name, ref_text, seed, dst):
    g = {"1": {"class_type": "MingLoadModel", "inputs": {"model": "Ming-3.0-tts-0.5b", "precision": "auto", "device": "auto", "download_if_missing": False}},
         "2": {"class_type": "LoadAudio", "inputs": {"audio": ref_name}},
         "3": {"class_type": "MingGenerate", "inputs": {"model": ["1", 0], "text": text, "task": "clone", "task.reference_audio": ["2", 0], "task.reference_text": ref_text,
                                                        "task.language": "Chinese", "seed": seed, "cfg": 2.0, "flow_steps": 10, "sigma": 0.25, "temperature": 0.0,
                                                        "max_steps": 250, "trim": True}},
         "4": {"class_type": "SaveAudio", "inputs": {"audio": ["3", 0], "filename_prefix": f"ming_batch/{dst.stem}"}}}
    pid = api("/prompt", {"prompt": g})["prompt_id"]
    while True:
        h = api(f"/history/{pid}")
        if pid in h:
            st = h[pid].get("status", {})
            if st.get("status_str") == "error":
                sys.exit(f"[ming] {dst.stem} 失敗：{json.dumps(st, ensure_ascii=False)[:1500]}")
            if st.get("completed"):
                break
        time.sleep(0.5)
    a = h[pid]["outputs"]["4"]["audio"][0]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(COMFY_DIR / "output" / a["subfolder"] / a["filename"]), str(dst)], check=True)


def truncated(p):
    a, sr = sf.read(p); a = a if a.ndim == 1 else a.mean(1)
    return float(np.abs(a[-int(0.06 * sr):]).max() / max(1e-9, np.abs(a).max())) > TAIL


def generate(j, text, ref_name, ref_text, out, seeds):
    n = 0
    for k in seeds:
        dst = out / "cand" / f"{j['name']}_s{k}.wav"; bad = out / "cand_trunc" / dst.name
        if dst.exists() or bad.exists():
            continue
        gen_one(text, ref_name, ref_text, k, dst); n += 1
        if truncated(dst):
            shutil.move(str(dst), bad)
    return n


def main():
    spec_path = Path(sys.argv[1]).resolve(); spec = json.loads(spec_path.read_text(encoding="utf-8-sig")); base = spec_path.parent
    out = (base / spec.get("out_dir", "voice")).resolve(); (out / "cand").mkdir(parents=True, exist_ok=True); (out / "cand_trunc").mkdir(exist_ok=True)
    t2s, lex = make_t2s(), load_lexicon(base)
    ensure_comfy(); t0 = time.time(); n = 0
    for j in spec["jobs"]:
        ref = Path(j["ref_audio"]) if Path(j["ref_audio"]).is_absolute() else (base / j["ref_audio"]).resolve()
        ref_name = f"ming_{md5(str(ref).encode()).hexdigest()[:10]}{ref.suffix}"
        shutil.copy(ref, COMFY_DIR / "input" / ref_name)
        text, ref_text = prep(j["text"], t2s, lex), prep(j["ref_text"], t2s, lex)
        n += generate(j, text, ref_name, ref_text, out, range(1, int(j.get("seeds", spec.get("seeds", 8))) + 1))
        if not list((out / "cand").glob(f"{j['name']}_s*.wav")):
            print(f"[ming] {j['name']} 全部被截斷 → 句尾改「……」多抽", flush=True)
            n += generate(j, text.rstrip("。！？!?，,. ") + "……", ref_name, ref_text, out, range(101, 101 + int(spec.get("extra_seeds", 4))))
        print(f"[ming] {j['name']} 完成（{time.time() - t0:.0f} 秒）：{text}", flush=True)
    try:
        api("/free", {"unload_models": True, "free_memory": True})
    except Exception:
        pass
    print(f"[done] 新生成 {n} 支，共 {time.time() - t0:.0f} 秒", flush=True)


if __name__ == "__main__":
    main()
