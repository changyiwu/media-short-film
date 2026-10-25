"""配音候選試聽與人工改挑（Voice venv）。2026-10-20 建立，試聽做法參考 media-video-specs 的 tools/fix_voice.py。

voice_pick.py 自動挑不到（needs_review）或使用者聽了不滿意時用：
  1. 試聽：把某一句的所有候選串成一個檔，每支前面用語音念出代號（s1、s2…；連不上 edge-tts 就用嗶聲），
     目前選中的那支排第一個、念「目前」。同時印出每支的聽寫、腔調分、響度、高頻比，給人對照。
  2. 改挑：指定一支候選，照 voice_pick 的方式去頭尾靜音寫成 <name>.wav，picks.json 記 manual，
     needs_review 清掉——之後重跑 voices，voice_pick 也不會改掉人挑的這支（已挑過的句子不改）。

用法（同一個 cmd 視窗先 call <repo>\\configs\\profile.cmd）：
  "%PY_VOICE%" <repo>\\tools\\audition.py <片子資料夾 或 out\\voice\\bv> line3
  "%PY_VOICE%" <repo>\\tools\\audition.py <片子資料夾 或 out\\voice\\bv> line3 --pick s5
試聽檔：out\\voice\\bv\\audition_<name>.wav。改挑後若新候選比原本長，H3 已照原長度拍好的鏡頭要確認鏡長還夠（重跑 edl 會告訴你）。
"""
import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

LABEL_VOICE = "zh-TW-YunJheNeural"
GAP_S = 0.6
LISTEN_LUFS = -20.0      # 試聽時每支候選先調到這個響度（同範本 mix.voice_lufs）：原始候選常只有 -40 LUFS，跟代號比起來聽不清楚


def voice_dir(p):
    p = Path(p).resolve()
    for d in (p, p / "output" / "voice" / "bv", p / "voice" / "bv", p / "bv"):
        if (d / "picks.json").is_file():
            return d
    sys.exit(f"找不到 picks.json：給片子資料夾或 out\\voice\\bv（試過 {p}）")


def mono(x):
    return x.mean(axis=1) if x.ndim > 1 else x


def label(text, sr, tmp):
    """念出代號（edge-tts）；連不上就回一段嗶聲"""
    try:
        import edge_tts
        mp3, wav = Path(tmp) / f"{text}.mp3", Path(tmp) / f"{text}.wav"
        asyncio.run(edge_tts.Communicate(text, LABEL_VOICE, rate="+10%").save(str(mp3)))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-ar", str(sr), "-ac", "1", str(wav)], check=True)
        return mono(sf.read(str(wav), dtype="float32")[0])
    except Exception:
        t = np.arange(int(0.25 * sr)) / sr
        return (0.3 * np.sin(2 * np.pi * 880 * t)).astype(np.float32)


def audition(vd, name, picks):
    p = picks[name]
    cands = {r["file"]: r for r in p["cands"]}
    order = [p["pick"]] + [f for f in sorted(cands) if f != p["pick"]]
    print(f"{name}「{p['text']}」　目前選 {p['pick']}" + ("（needs_review：" + str(p.get("review_reason")) + "）" if p.get("needs_review") else ""))
    print(f"  {'代號':<6}{'聽寫對':<6}{'腔調分':>6}{'響度':>8}{'高頻比':>7}  聽寫")
    parts, sr = [], None
    with tempfile.TemporaryDirectory() as tmp:
        for i, f in enumerate(order):
            r = cands[f]
            x, rate = sf.read(str(vd / "cand" / f), dtype="float32")
            sr = sr or rate
            if rate != sr:
                sys.exit(f"{f} 的取樣率 {rate} 和其他候選 {sr} 不同")
            tag = f.rsplit("_", 1)[-1].replace(".wav", "")          # line3_s5.wav → s5
            say = f"目前，{tag}" if i == 0 else tag
            x = mono(x)
            if r.get("lufs") is not None:                           # 只調試聽音量，響度欄照舊印原始值（音量離群照樣看得出來）
                x = x * 10 ** ((LISTEN_LUFS - r["lufs"]) / 20)
                peak = float(np.abs(x).max()) if len(x) else 0.0
                if peak > 0.98:
                    x = x * (0.98 / peak)
            parts += [label(say, sr, tmp), np.zeros(int(0.2 * sr), np.float32), x.astype(np.float32), np.zeros(int(GAP_S * sr), np.float32)]
            flag = "" if r.get("sound_ok", True) else "　⚠ 音量或嘶聲異常"
            lufs = "—" if r.get("lufs") is None else f"{r['lufs']:.1f}"
            print(f"  {tag + ('＊' if i == 0 else ''):<6}{'✓' if r.get('asr_ok') else '✗':<6}{r.get('tw_score', 0):>6.2f}{lufs:>8}"
                  f"{r.get('hf_4k', 0):>7.2f}  {r.get('asr', '')}{flag}")
    out = vd / f"audition_{name}.wav"
    sf.write(str(out), np.concatenate(parts), sr, subtype="PCM_16")
    print(f"→ {out}")
    print(f"選好後：audition.py {vd} {name} --pick <代號>")


def pick(vd, name, tag, picks, picks_path):
    import librosa                                   # 跟 voice_pick.write_trimmed 同一套去靜音
    p = picks[name]
    f = f"{name}_{tag}.wav" if not tag.endswith(".wav") else tag
    rows = {r["file"]: r for r in p["cands"]}
    if f not in rows:
        sys.exit(f"{name} 沒有候選 {f}；有：{'、'.join(sorted(rows))}")
    x, sr = sf.read(str(vd / "cand" / f), dtype="float32")
    _, (a, b) = librosa.effects.trim(mono(x), top_db=40)
    a = max(0, a - int(0.08 * sr)); b = min(len(x), b + int(0.15 * sr))
    old = p.get("trim_s", [0, 0])[1]
    sf.write(str(vd / f"{name}.wav"), x[a:b], sr, subtype="PCM_16")
    r = rows[f]
    p.update(pick=f, trim_s=[round(a / sr, 3), round((b - a) / sr, 3)], lufs=r.get("lufs"), hf_4k=r.get("hf_4k"),
             needs_review=False, review_reason=None, manual=True)
    picks_path.write_text(json.dumps(picks, ensure_ascii=False, indent=1), encoding="utf-8")
    new = p["trim_s"][1]
    print(f"{name} 改用 {f}（人工）：{old:.2f}s → {new:.2f}s，picks.json 已記 manual")
    if new > old + 0.05:
        print(f"注意：比原本長 {new - old:.2f}s。H3 已照原長度拍好的鏡頭，重跑 edl 確認鏡長還夠，不夠就要重拍那一鏡")


def main():
    ap = argparse.ArgumentParser(description="配音候選試聽與人工改挑")
    ap.add_argument("where", help="片子資料夾，或 out\\voice\\bv")
    ap.add_argument("name", help="句子代號，例如 line3（picks.json 的 key）")
    ap.add_argument("--pick", help="改用這支候選（s5 或完整檔名）")
    a = ap.parse_args()
    vd = voice_dir(a.where)
    picks_path = vd / "picks.json"
    picks = json.loads(picks_path.read_text(encoding="utf-8"))
    if a.name not in picks:
        sys.exit(f"picks.json 沒有 {a.name}；有：{'、'.join(picks)}")
    if a.pick:
        pick(vd, a.name, a.pick, picks, picks_path)
    else:
        audition(vd, a.name, picks)


if __name__ == "__main__":
    main()
