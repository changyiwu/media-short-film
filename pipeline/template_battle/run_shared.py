"""跟別的工作共用本機 GPU 時跑 make_battle.py 的階段：不呼叫 ComfyUI /free（別人的模型不卸載）。
SHARED_CPU=1：聽寫、對齊、分人聲都改用 CPU（慢很多，但完全不碰顯存）。
改寫自上游 pipeline/template_battle/run_shared.py（上游 e634cce）：上游換的是 stable-ts，本分支換 tools/stt.py 的 Qwen3 聽寫與對齊。

用法（Voice venv，片子資料夾）："%PY_VOICE%" run_shared.py songs dj audio [--ver 2] [--battle battle.json]"""
import os
import sys

if os.environ.get("SHARED_CPU"):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
import make_battle as mb  # noqa: E402

mb.free_comfy = lambda: None
if os.environ.get("SHARED_CPU"):
    sys.path.insert(0, str(mb.T)); import stt  # noqa: E401,E402
    _asr, _al = stt.load_song_asr, stt.load_song_aligner
    stt.load_song_asr = lambda device="cpu": _asr("cpu")
    stt.load_song_aligner = lambda device="cpu": _al("cpu")
want = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] not in ("--ver", "--battle")]
bad = [a for a in want if a not in mb.ALL]
if not want or bad:
    sys.exit(f"要給 stage（不認得：{bad}）；可用：{' '.join(mb.ALL)}")
for st in want:
    mb.ALL[st]()
