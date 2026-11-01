"""Local speech-to-text with faster-whisper (GPU). Global tool.

Prereqs: faster-whisper installed in C:/AI/Voice/venv; models cached in C:/AI/Voice/models/whisper.
Fallback (2026-10-14): when faster-whisper / ctranslate2 cannot be imported (e.g. Windows on Arm, no ARM64 wheel),
load_asr() switches to openai-whisper (pure PyTorch; slower; downloads its own large-v3 .pt to models/whisper/openai on first use).
Force a backend with ASR_BACKEND=faster|openai. voice_pick.py and review.py use load_asr() too.

Usage (cmd, after call <repo>\\configs\\profile.cmd):
  "%PY_VOICE%" <repo>\\tools\\stt.py --audio in.wav --outdir out [--model large-v3] [--language zh|auto]

Writes <outdir>/transcript.txt, transcript.srt and transcript.json.
"""
import argparse
import json
import sys
import os
from pathlib import Path

MODEL_CACHE = Path(os.environ.get("AI_ROOT", r"C:\AI")) / "Voice" / "models" / "whisper"  # AI_ROOT = install root (default C:\AI)
QWEN_ASR = MODEL_CACHE.parent / "Qwen3-ASR-1.7B-hf"
DEFAULT_PROMPT = "繁體中文，教學、AI 影片製作、ComfyUI、MiniMax H3、Blender。"


def _add_cuda_dll_dirs():
    """ctranslate2 needs CUDA 12 runtime DLLs (cublas/cudnn). Make them discoverable."""
    import os
    import site
    roots = []
    for sp in site.getsitepackages() + [site.getusersitepackages()]:
        roots.append(Path(sp) / "nvidia")
    if os.name != "nt":  # Linux/Colab: LD_LIBRARY_PATH is only read at start-up, so preload the pip CUDA 12 libs (2026-10-10)
        import ctypes
        libs = [so for root in roots if root.is_dir()
                for pat in ("cublas/lib/libcublasLt.so.*", "cublas/lib/libcublas.so.*", "cuda_nvrtc/lib/libnvrtc.so.*", "cudnn/lib/libcudnn*.so.*")
                for so in sorted(root.glob(pat))]
        for _ in range(3):  # cudnn sub-libraries depend on each other: retry until no progress
            left = []
            for so in libs:
                try:
                    ctypes.CDLL(str(so), mode=ctypes.RTLD_GLOBAL)
                except OSError:
                    left.append(so)
            if len(left) in (0, len(libs)):
                break
            libs = left
        return
    for root in roots:
        if not root.is_dir():
            continue
        for sub in root.iterdir():
            bindir = sub / "bin"
            if bindir.is_dir():
                os.environ["PATH"] = str(bindir) + os.pathsep + os.environ.get("PATH", "")
                try:
                    os.add_dll_directory(str(bindir))
                except Exception:
                    pass



class _OpenAIWhisper:
    """openai-whisper behind the faster-whisper interface: transcribe() -> (segments with .start/.end/.text, info)."""
    backend = "openai"

    def __init__(self, model, device):
        import whisper
        self.m = whisper.load_model(model, device=device, download_root=str(MODEL_CACHE / "openai"))
        self.fp16 = device == "cuda"

    def transcribe(self, audio, language=None, beam_size=5, initial_prompt=None, condition_on_previous_text=False, **_ignored):
        from types import SimpleNamespace
        import whisper
        r = self.m.transcribe(str(audio), language=language, beam_size=beam_size, initial_prompt=initial_prompt,
                              condition_on_previous_text=condition_on_previous_text, fp16=self.fp16)
        segs = [SimpleNamespace(start=s["start"], end=s["end"], text=s["text"]) for s in r["segments"]]
        dur = len(whisper.load_audio(str(audio))) / whisper.audio.SAMPLE_RATE
        return segs, SimpleNamespace(language=r.get("language", language), language_probability=None, duration=dur)


def load_asr(model="large-v3", device="cuda", compute_type="float16", local_files_only=False):
    """faster-whisper if importable (default), else openai-whisper. ASR_BACKEND=faster|openai forces one. Result has .backend."""
    want = os.environ.get("ASR_BACKEND", "auto")
    if want != "openai":
        try:
            _add_cuda_dll_dirs()
            from faster_whisper import WhisperModel
            m = WhisperModel(model, device=device, compute_type=compute_type, download_root=str(MODEL_CACHE), local_files_only=local_files_only)
            m.backend = "faster"
            return m
        except ImportError as e:
            if want == "faster":
                raise
            print(f"[asr] faster-whisper unavailable ({e}); falling back to openai-whisper", file=sys.stderr, flush=True)
    return _OpenAIWhisper(model, device)


def load_song_asr(device="cuda"):
    """Song/rap dictation with Qwen3-ASR 1.7B: returns hear(audio, sr) -> text (no timestamps; Whisper stays for speech and forced alignment)."""
    if not (QWEN_ASR / "model.safetensors").exists():
        raise SystemExit(f"找不到 Qwen3-ASR 權重：{QWEN_ASR}（照 setup/downloads_qwen_asr.json 下載）")
    import librosa
    import torch
    from transformers import AutoProcessor, Qwen3ASRForConditionalGeneration
    proc = AutoProcessor.from_pretrained(QWEN_ASR)
    model = Qwen3ASRForConditionalGeneration.from_pretrained(QWEN_ASR, dtype=torch.bfloat16, device_map=device)

    def hear(audio, sr):
        x = librosa.resample(audio, orig_sr=sr, target_sr=16000) if sr != 16000 else audio
        inp = proc.apply_transcription_request(audio=[x], language="zh").to(model.device, model.dtype)
        ids = model.generate(**inp, max_new_tokens=1024, do_sample=False)
        return proc.decode(ids[0][inp.input_ids.shape[1]:], return_format="transcription_only")
    return hear


def fmt_ts(seconds: float, comma: bool = False) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    sep = "," if comma else "."
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Transcribe audio locally with faster-whisper.")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--language", default="zh", help="'auto' to detect")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--beam-size", type=int, default=5)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute-type", default="float16")
    a = ap.parse_args()

    audio = Path(a.audio)
    if not audio.is_file():
        print(f"audio not found: {audio}", file=sys.stderr)
        return 2
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    try:
        model = load_asr(a.model, device=a.device, compute_type=a.compute_type, local_files_only=True)
    except ImportError:
        print("Neither faster-whisper nor openai-whisper found. Run with the Voice venv (%PY_VOICE%, default C:\\AI\\Voice\\venv\\Scripts\\python.exe)", file=sys.stderr)
        return 3

    segments, info = model.transcribe(
        str(audio),
        language=None if a.language == "auto" else a.language,
        beam_size=a.beam_size,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False,
        initial_prompt=a.prompt,
    )

    rows = []
    for seg in segments:
        rows.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip()})
        print(f"[{fmt_ts(seg.start)} -> {fmt_ts(seg.end)}] {seg.text.strip()}", flush=True)

    (outdir / "transcript.json").write_text(json.dumps(
        {"audio": str(audio), "model": a.model, "backend": model.backend, "language": info.language,
         "language_probability": info.language_probability, "duration": info.duration, "segments": rows},
        ensure_ascii=False, indent=2), encoding="utf-8")
    (outdir / "transcript.txt").write_text("\n".join(r["text"] for r in rows) + "\n", encoding="utf-8")
    srt = [f"{i}\n{fmt_ts(r['start'], True)} --> {fmt_ts(r['end'], True)}\n{r['text']}\n" for i, r in enumerate(rows, 1)]
    (outdir / "transcript.srt").write_text("\n".join(srt), encoding="utf-8")

    print(f"[done] segments={len(rows)} duration={info.duration:.1f}s language={info.language} -> {outdir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
