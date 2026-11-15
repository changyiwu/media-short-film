"""H3 自己念的台詞（voice_mode h3_ref）：從 H3 成片抓出那句台詞，比對原文。移植自上游 make_film.py 的 harvest_lines()（2026-10-23），
改成獨立工具、在 Voice venv 跑（要 audio-separator、faster-whisper／openai-whisper、pypinyin），並改用拼音比對。

做的事：clip.mp4 的音軌 → BS-RoFormer 分離人聲 → 聽寫（tools/stt.py 的 load_asr）找開口與收尾 → 切出那句存成 wav →
拼音（聲調）比對原文：聽寫常寫成簡體字或同音字（「阿禾」→「阿和」），比字會誤判，比拼音才準。
聽寫不帶提示詞（2026-11-15，移植上游 `121f435` 的發現：提示詞會把念錯的字拉回正確字）。
H3 會改用詞（例：二十四號→二十四日）、偶爾晚開口 1.5–2.1 秒；相似度低於門檻就標 needs_review，由 make_film.py 停下來。

用法（Voice venv）：
  "%PY_VOICE%" tools\\h3_line_harvest.py --clip h3\\S2\\clip.mp4 --text "你是那隻台灣黑熊？" --out voice\\h3\\line3.wav [--work 暫存資料夾]
印出一行 JSON：{"heard", "at", "end", "match", "tone_match", "needs_review"}（at／end 是在 clip 裡的秒數）。"""
import argparse
import difflib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

T = Path(__file__).resolve().parent
sys.path.insert(0, str(T))
AI_ROOT = Path(os.environ.get("AI_ROOT", r"C:\AI"))
SEP_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
SR = 48000
MATCH_MIN = 0.7          # 拼音（不計聲調）相似度低於這個就要人處理（上游以字比對用 0.7）


def syllables(text, tone):
    from pron_check import expected                 # 已套台灣讀音、數字轉國字；回傳（字、拼音、本調、變調）
    return [f"{p}{t}" if tone else p for _, p, t, _ in zip(*expected(text))]


def ratio(a, b):
    return round(difflib.SequenceMatcher(None, a, b).ratio(), 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", required=True); ap.add_argument("--text", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--work"); ap.add_argument("--min", type=float, default=MATCH_MIN)
    a = ap.parse_args()
    clip, out = Path(a.clip), Path(a.out)
    work = Path(a.work) if a.work else out.parent / f"{out.stem}_work"; work.mkdir(parents=True, exist_ok=True)
    mix = work / "mix.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip), "-vn", "-ac", "2", "-ar", "44100", str(mix)], check=True)

    from audio_separator.separator import Separator
    for f in work.glob("mix_(*"):
        f.unlink()
    sep = Separator(model_file_dir=str(AI_ROOT / "Voice" / "models" / "separator"), output_dir=str(work), output_format="WAV",
                    log_level=40)
    sep.load_model(model_filename=SEP_MODEL)
    sep.separate(str(mix))
    voc = next(work.glob("mix_(Vocals)*.wav"))

    import opencc
    from stt import load_asr
    model = load_asr(local_files_only=True)
    # 不帶 initial_prompt：提示詞會把念錯的字拉回正確字（上游 2026-11-14「抓」念成「多」就這樣漏掉），比對原文的聽寫一律不帶提示
    segs, _ = model.transcribe(str(voc), language="zh", beam_size=5, vad_filter=True,
                               vad_parameters={"min_silence_duration_ms": 500}, condition_on_previous_text=False)
    s2t = opencc.OpenCC("s2t")                       # 沒有「繁體中文」提示時聽寫常出簡體；只轉字，s2twp 會連詞換（局部→區域性）
    segs = [dict(start=s.start, end=s.end, text=s2t.convert(s.text.strip())) for s in segs]
    heard = "".join(s["text"] for s in segs)
    want, got = syllables(a.text, False), syllables(heard, False)
    match = ratio(want, got) if want else 0.0
    tone = ratio(syllables(a.text, True), syllables(heard, True)) if want else 0.0
    if segs:
        st, en = max(0.0, segs[0]["start"] - 0.05), segs[-1]["end"] + 0.15
    else:
        st, en = 0.0, 0.0
    out.parent.mkdir(parents=True, exist_ok=True)
    if en > st:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(voc), "-ss", f"{st:.3f}", "-to", f"{en:.3f}",
                        "-ar", str(SR), "-ac", "1", str(out)], check=True)
    print(json.dumps(dict(heard=heard, at=round(st, 3), end=round(en, 3), match=match, tone_match=tone,
                          needs_review=(not segs) or match < a.min), ensure_ascii=False))


if __name__ == "__main__":
    main()
