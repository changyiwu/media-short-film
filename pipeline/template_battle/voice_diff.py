"""人聲不重複檢查（上游使用者 2026-11-02：不要老是用同類的幾個人聲）：候選的聲紋（CAM++）和音高，比對前面每一場用過的人聲。
改寫自上游 pipeline/template_battle/voice_diff.py（上游 e634cce）。與上游不同：前場找 output/饒舌對決/*/battle.json 旁的 work/song/align_<A|B>.json；
CAM++ 用 Ming 節點附的 campplus.onnx（CAMPP_ONNX 可指定）；音高走 tools/pron_check.py 的 f0_track（沒有 parselmouth 時改 librosa）。

用法（Voice venv，片子資料夾）："%PY_VOICE%" voice_diff.py 候選檔 [候選檔…]
  → 每個候選列出 F0 中位數、最像的 3 個前場人聲（相似度 1＝同一個聲音）；給兩個以上候選時另列候選之間的相似度。
  BATTLE_FILMS＝放各場對決的資料夾（預設 output/饒舌對決/）。"""
import json
import os
import sys
import tempfile
from pathlib import Path

import librosa
import numpy as np
import onnxruntime as ort
import soundfile as sf
import torch
import torchaudio

sys.stdout.reconfigure(encoding="utf-8")
if len(sys.argv) < 2:
    sys.exit(__doc__)
HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "battle.json").read_text(encoding="utf-8"))
sys.path.insert(0, str((HERE / CFG.get("repo_dir", "../../..") / "tools").resolve()))
from pron_check import f0_track  # noqa: E402

AI = Path(os.environ.get("AI_ROOT", r"C:\AI"))
FILMS = Path(os.environ.get("BATTLE_FILMS") or HERE.parent)
onnx = os.environ.get("CAMPP_ONNX") or next(iter(sorted((AI / "Ming").glob("ComfyUI/custom_nodes/*/assets/campplus.onnx"))), None)
if not onnx or not Path(onnx).exists():
    sys.exit("找不到 campplus.onnx（Ming 節點附的，見 AGENT_SETUP.md §2d）；或用 CAMPP_ONNX 指定")
sess = ort.InferenceSession(str(onnx), providers=["CPUExecutionProvider"])


def embed(x):
    feat = torchaudio.compliance.kaldi.fbank(torch.from_numpy(x).unsqueeze(0), num_mel_bins=80, dither=0, sample_frequency=16000)
    feat = feat - feat.mean(dim=0, keepdim=True)
    e = sess.run(None, {sess.get_inputs()[0].name: feat.unsqueeze(0).numpy()})[0].flatten()
    return e / np.linalg.norm(e)


def voiced(path, rows=None):
    v, _ = librosa.load(str(path), sr=16000)
    if rows:                                                   # 有對齊：只取聽寫分數夠、不太長的句子
        r = [x for x in rows if x.get("ok", 1) >= 0.6 and x["end"] - x["start"] < 6] or rows
        v = np.concatenate([v[int(a["start"] * 16000):int(a["end"] * 16000)] for a in r])
    else:                                                      # 沒對齊：只取人聲能量夠的段落
        hop = 1600
        e = np.array([np.sqrt(np.mean(v[i:i + hop] ** 2)) for i in range(0, len(v) - hop, hop)])
        keep = e > 0.02
        v = np.concatenate([v[i * hop:(i + 1) * hop] for i in np.nonzero(keep)[0]]) if keep.any() else v
    return v[:16000 * 40].astype(np.float32)


def f0(x):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.wav"; sf.write(str(p), x, 16000)
        f = np.asarray(f0_track(str(p))[1], dtype=float)
    f = f[f > 0]
    return round(float(np.median(f)), 1) if f.size else 0.0


hist = {}
for cfg in FILMS.glob("*/battle.json"):
    if cfg.parent == HERE:
        continue
    d = json.loads(cfg.read_text(encoding="utf-8"))
    for k, r in d.get("rappers", {}).items():
        al = cfg.parent / "work" / "song" / f"align_{k}.json"
        if not al.exists():
            continue
        j = json.loads(al.read_text(encoding="utf-8"))
        if Path(j.get("vocals", "")).exists():
            x = voiced(j["vocals"], j.get("rows"))
            hist[f"{d.get('title')}/{r.get('name')}"] = (embed(x), f0(x))
print("前場人聲（F0）", {k: v[1] for k, v in hist.items()} or "沒有", flush=True)
out = {}
for f in sys.argv[1:]:
    x = voiced(f)
    e = embed(x); out[f] = e
    top = sorted(((float(e @ v[0]), k) for k, v in hist.items()), reverse=True)[:3]
    print(Path(f).name[:44], "F0", f0(x), "最像", [(round(s, 2), k) for s, k in top], flush=True)
names = list(out)
if len(names) > 1:
    print("候選之間：")
    for a in names:
        print(" ", Path(a).name[:30], [round(float(out[a] @ out[b]), 2) for b in names])
