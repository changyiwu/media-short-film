"""歌詞送歌曲模型前的處理：套讀音替換表、繁轉簡、數字轉中文，段落標籤與空行不動（原始歌詞檔不改）。
工具直接 from song_lyrics import song_lyrics；ComfyUI 的 Python 沒有 opencc，會改叫語音環境轉換，轉不了就停下，不送繁體。
命令列：python song_lyrics.py < 歌詞.txt（UTF-8，結果印到標準輸出）。
環境變數：PY_VOICE（預設 %AI_ROOT%\\Voice\\venv\\Scripts\\python.exe）。"""
import contextlib, importlib.util, os, subprocess, sys
from pathlib import Path

from tts_lexicon import load_lexicon
from voxcpm_batch import make_t2s, prep

REPO = Path(__file__).resolve().parents[1]


def is_tag(line):
    s = line.strip()
    return not s or (s.startswith("[") and s.endswith("]"))


def convert(text):
    t2s, lex = make_t2s(), load_lexicon(REPO)
    return "\n".join(l if is_tag(l) else prep(l, t2s, lex) for l in text.splitlines())


def song_lyrics(text):
    if all(is_tag(l) for l in text.splitlines()):         # 純配樂只有段落標籤，不用轉
        return text
    if importlib.util.find_spec("opencc"):
        return convert(text)
    py = os.environ.get("PY_VOICE") or str(Path(os.environ.get("AI_ROOT", r"C:\AI")) / "Voice" / "venv" / "Scripts" / "python.exe")
    r = subprocess.run([py, __file__], input=text.encode("utf-8"), stdout=subprocess.PIPE, check=True)
    return r.stdout.decode("utf-8")


if __name__ == "__main__":
    with contextlib.redirect_stdout(sys.stderr):          # 標準輸出只留歌詞
        out = convert(sys.stdin.buffer.read().decode("utf-8-sig"))
    sys.stdout.buffer.write(out.encode("utf-8"))
