"""同一首歌換字：唱錯一兩個字（或一整句），從「同一首歌別處唱對的地方」拿人聲換掉，伴奏不動、全曲時間不變。
本分支新寫（上游只有手動做法：〈向日葵之戰〉副歌第二遍唱錯，用第一遍同一句整句蓋過去）。
不能從別首歌拿：音色、調性、拍子都不同，接起來一定聽得出來。YuE2 換 seed 也是別首歌。

兩種模式：
  整句（不給 --chars）：副歌第二遍唱錯 → 用第一遍同一句整句蓋。時間差先用對齊估，再用伴奏低頻包絡在 ±150 ms 內找準
    （上游踩過：週期估錯 0.26 秒，那句早了、使用者聽成跳拍），不拉長、不移調。
  單字（--chars 目標字 [來源字]）：同一個字（或詞）在別句唱對了 → 拿來放到唱錯的位置：起點對齊目標字的開口、
    長度拉到跟目標一樣（±15% 內）、音高移到目標的中位數（±3 半音內，--no-pitch 不移）。
接法：只換人聲（新混音＝原混音＋〔新人聲－舊人聲〕，伴奏完全不動）；兩端接點各在 ±0.12 秒內找兩版人聲都最安靜的 20 ms，
等功率交叉 30 ms；新人聲音量對齊被換掉的那段。

用法（Voice venv，片子資料夾，先跑過 make_battle.py songs；句號＝align_<A|B>.json 的 rows 順序，從 0 算，同 lyric_audit.py 的「句」）：
  "%PY_VOICE%" song_swap.py <A|B> <目標句> <來源句>                         整句
  "%PY_VOICE%" song_swap.py <A|B> <目標句> <來源句> --chars 巨人             單字（兩句都找「巨人」，取第一次出現）
  "%PY_VOICE%" song_swap.py <A|B> 18 0 --chars 巨人@2 巨人                   「字@n」＝那句第 n 次出現（從 1 算）
  選項：--song 檔案（接著換第二處：用上一次的輸出當底；預設 battle.json 的 rappers.<A|B>.song）、--out 檔名、--no-pitch、
        --force（長度差超過 ±15%、移調超過 ±3 半音時預設停下，硬做才加）
輸出：預設 song/<原檔名>_swap.wav（不覆蓋原檔）＋ work/song/swap/<輸出檔名>.md（接點、時間差、移調、換之前／之後的聽寫）。
接完：battle.json 的 rappers.<A|B>.song 改成新檔 → 重跑 songs audio → lyric_audit.py、gap_check.py <A|B> <原檔>，**一定要人聽接點**；
換到的句子有對嘴鏡就重拍那一鏡（h3 之前換就不用）。"""
import json
import re
import sys
import warnings
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

import make_battle as mb
from lyric_audit import NOTCH, load_hear, miss

sys.stdout.reconfigure(encoding="utf-8")
warnings.filterwarnings("ignore", category=FutureWarning); warnings.filterwarnings("ignore", category=RuntimeWarning)
args = sys.argv[1:]


def opt(name, n=1):
    if name not in args:
        return None
    i = args.index(name); v = args[i + 1:i + 1 + n]; del args[i:i + 1 + n]
    return v


song_opt, out_opt = opt("--song"), opt("--out")
no_pitch, force = "--no-pitch" in args, "--force" in args
for f_ in ("--no-pitch", "--force"):
    if f_ in args:
        args.remove(f_)
chars = None
if "--chars" in args:
    i = args.index("--chars"); rest = args[i + 1:]; del args[i:]
    if not rest:
        sys.exit("--chars 後面要給字")
    chars = (rest[0], rest[1] if len(rest) > 1 else rest[0])
if len(args) != 3:
    sys.exit(__doc__)
who, ti, si = args[0], int(args[1]), int(args[2])
AL = json.loads((mb.OUT / "song" / f"align_{who}.json").read_text(encoding="utf-8"))
rows = AL["rows"]
if not (0 <= ti < len(rows) and 0 <= si < len(rows)):
    sys.exit(f"句號要在 0–{len(rows) - 1}")
if ti == si and chars is None:
    print("⚠ 目標句跟來源句同一句（只當測試用：結果應該跟原曲幾乎一樣）", flush=True)
src_song = Path(song_opt[0]).resolve() if song_opt else (mb.HERE / mb.R[who]["song"]).resolve()
D = mb.OUT / "song" / "swap"; D.mkdir(parents=True, exist_ok=True)
out = (mb.HERE / "song" / out_opt[0]) if out_opt else src_song.with_name(src_song.stem + "_swap.wav")
if out.resolve() == src_song:
    sys.exit("輸出不能跟來源同一個檔")

voc_p, ins_p = mb.sep_stems(src_song, mb.OUT / "song" / "sep")   # 跟 songs 共用快取（依檔名）
voc, SR = sf.read(str(voc_p), dtype="float32", always_2d=True)
ins, _ = sf.read(str(ins_p), dtype="float32", always_2d=True)
mix = librosa.load(str(src_song), sr=SR, mono=False)[0]
mix = (mix[None] if mix.ndim == 1 else mix).T.astype(np.float32)
if mix.shape[1] == 1:
    mix = np.repeat(mix, 2, 1)
n = min(len(voc), len(ins), len(mix)); voc, ins, mix = voc[:n], ins[:n], mix[:n]
S = lambda t: int(round(t * SR))
rms = lambda a: float(np.sqrt(np.mean(a ** 2)) + 1e-9)


def find_chars(row, spec):
    """row 的 words 裡找 spec（「巨人」或「巨人@2」）→ (開始秒, 結束秒)。"""
    m = re.fullmatch(r"(.+?)(?:@(\d+))?", spec); txt, k = m.group(1), int(m.group(2) or 1)
    ws = [w for w in row["words"] if NOTCH.sub("", w["w"])]
    seq = "".join(NOTCH.sub("", w["w"])[:1] for w in ws)
    hits = [i for i in range(len(seq)) if seq.startswith(txt, i)]
    if len(hits) < k:
        sys.exit(f"句 {rows.index(row)}「{row['text']}」裡找不到第 {k} 個「{txt}」（對齊的字：{seq}）")
    if k == 1 and len(hits) > 1:
        print(f"⚠ 句 {rows.index(row)} 有 {len(hits)} 個「{txt}」，用第一個（要別的寫「{txt}@2」）", flush=True)
    a = hits[k - 1]
    return ws[a]["s"], ws[a + len(txt) - 1]["e"]


def quiet_point(t, sigs, span=0.12):
    """t 附近 ±span 秒內，幾條人聲加起來最安靜的 20 ms 中心（秒）。"""
    w = S(0.02); best, bt = 1e9, t
    for c in np.arange(t - span, t + span + 1e-9, 0.005):
        i = S(c)
        if i - w // 2 < 0 or i + w // 2 >= n:
            continue
        e = sum(rms(s[i - w // 2:i + w // 2]) for s in sigs)
        if e < best:
            best, bt = e, c
    return bt


def low_env(x, a, b):
    """伴奏 200 Hz 以下的包絡（1 ms 一格），找整句的時間差用。"""
    from scipy.signal import butter, sosfilt
    seg = x[max(0, S(a)):S(b)].mean(1)
    e = np.abs(sosfilt(butter(4, 200, "lp", fs=SR, output="sos"), seg))
    h = SR // 1000; e = e[:len(e) // h * h].reshape(-1, h).mean(1)
    return (e - e.mean()) / (e.std() + 1e-9)


def median_f0(x):
    y = librosa.resample(x.mean(1), orig_sr=SR, target_sr=16000)
    f, v, _ = librosa.pyin(y, fmin=70, fmax=700, sr=16000, frame_length=1024, hop_length=160)
    f = f[v & ~np.isnan(f)]
    return float(np.median(f)) if f.size >= 5 else None


T, Sr = rows[ti], rows[si]
rep = [f"# {who} 換字：句 {ti} ← 句 {si}" + (f"（{chars[0]} ← {chars[1]}）" if chars else "（整句）"), "",
       f"- 底：{src_song.name}", f"- 目標句 {ti}：{T['text']}", f"- 來源句 {si}：{Sr['text']}"]
newv = voc.copy()
if chars is None:
    if NOTCH.sub("", T["text"]) != NOTCH.sub("", Sr["text"]):
        print(f"⚠ 兩句歌詞不一樣（{T['text']}／{Sr['text']}）：整句換會把目標句唱成來源句的詞", flush=True)
    t0, t1 = T["start"] - 0.15, T["end"] + 0.2
    guess = T["start"] - Sr["start"]
    a, b = Sr["start"] - 1.5, Sr["end"] + 1.5
    es = low_env(ins, a, b); L = len(es); best, lag = -1e9, 0
    for d in range(-150, 151):
        et = low_env(ins, a + guess + d / 1000, b + guess + d / 1000)
        m_ = min(L, len(et))
        if m_ < 500:
            continue
        c = float(np.dot(es[:m_], et[:m_]) / m_)
        if c > best:
            best, lag = c, d
    shift = guess + lag / 1000
    edge = abs(lag) >= 145
    print(f"時間差：對齊估 {guess:.3f} 秒，伴奏包絡修正 {lag:+d} ms → {shift:.3f} 秒（相關 {best:.2f}）"
          + ("  ⚠ 貼在搜尋邊界，兩句可能不在同樣的拍位，不要用" if edge else ""), flush=True)
    rep.append(f"- 時間差 {shift:.3f} 秒（對齊估 {guess:.3f}，伴奏修正 {lag:+d} ms，相關 {best:.2f}）" + ("　⚠ 貼邊界" if edge else ""))
    if T["start"] - 0.5 - shift < 0 or T["end"] + 0.5 - shift > n / SR:
        sys.exit("來源句太靠近歌頭或歌尾，取不到完整的一段")
    moved = np.roll(voc, S(shift), 0)                        # 來源人聲搬到目標的時間
    c0 = quiet_point(t0, [voc, moved]); c1 = quiet_point(t1, [voc, moved])
    seg = moved[S(c0):S(c1)].copy(); i0 = S(c0)
else:
    ta, tb = find_chars(T, chars[0]); sa, sb = find_chars(Sr, chars[1])
    pad = 0.06
    tgt = voc[S(ta - pad):S(tb + pad)]
    seg = voc[S(sa - pad):S(sb + pad)].copy()
    rate = len(seg) / max(1, len(tgt))
    rep.append(f"- 目標字 {ta:.2f}–{tb:.2f} 秒、來源字 {sa:.2f}–{sb:.2f} 秒，長度比 {rate:.2f}")
    if abs(rate - 1) > 0.15:
        msg = f"來源長度是目標的 {rate:.2f} 倍（超過 ±15%，拉長會聽得出來）：換一個來源，或連前後字一起換"
        if not force:
            sys.exit(msg + "；確定要硬做加 --force")
        print("⚠ " + msg, flush=True)
    if abs(rate - 1) > 0.01:
        seg = np.stack([librosa.effects.time_stretch(seg[:, c], rate=rate) for c in range(2)], 1)
    st = 0.0
    if not no_pitch:
        fs_, ft = median_f0(seg), median_f0(tgt)
        if fs_ and ft:
            st = float(12 * np.log2(ft / fs_))
            if abs(st) > 3:
                msg = f"要移 {st:+.1f} 半音（超過 ±3，會變聲）：換來源，或用 --no-pitch"
                if not force:
                    sys.exit(msg + "；確定要硬做加 --force")
                print("⚠ " + msg, flush=True)
            if abs(st) >= 0.3:
                seg = np.stack([librosa.effects.pitch_shift(seg[:, c], sr=SR, n_steps=st) for c in range(2)], 1)
        else:
            print("⚠ 量不到音高（氣音、太短），不移調", flush=True)
    rep.append(f"- 移調 {st:+.2f} 半音" + ("（--no-pitch）" if no_pitch else ""))
    i0 = S(ta - pad)
    seg = seg[:len(tgt)] if len(seg) >= len(tgt) else np.concatenate([seg, np.zeros((len(tgt) - len(seg), 2), np.float32)])
    print(f"單字：{chars[0]} {ta:.2f}–{tb:.2f} ← {chars[1]} {sa:.2f}–{sb:.2f}，長度比 {rate:.2f}，移調 {st:+.2f} 半音", flush=True)
seg = seg.astype(np.float32) * (rms(voc[i0:i0 + len(seg)]) / rms(seg))       # 音量對齊被換掉的那段
x = S(0.03); w = np.ones((len(seg), 1), np.float32)
w[:x, 0] = np.sin(np.linspace(0, np.pi / 2, x)); w[-x:, 0] = np.cos(np.linspace(0, np.pi / 2, x))
newv[i0:i0 + len(seg)] = voc[i0:i0 + len(seg)] * (1 - w) + seg * w
new_mix = mix + (newv - voc)
pk = float(np.abs(new_mix).max())
if pk > 0.999:
    new_mix *= 0.999 / pk; print(f"峰值 {pk:.2f}，整首壓到 0.999", flush=True)
sf.write(str(out), new_mix, SR, subtype="PCM_16")
sf.write(str(D / f"{out.stem}_vocals.wav"), newv, SR, subtype="PCM_16")
c0s, c1s = i0 / SR, (i0 + len(seg)) / SR
print(f"接點 {c0s:.3f}–{c1s:.3f} 秒（歌曲時間）→ {out}", flush=True)
rep.append(f"- 接點 {c0s:.3f}–{c1s:.3f} 秒（歌曲時間），交叉 30 ms；輸出 `{out.name}`")

# 驗證：目標句前後各多 0.3 秒，換之前／之後的混音各聽寫一次（不給提示，拼音比）
hear = load_hear(mb.HERE)
want = NOTCH.sub("", __import__("opencc").OpenCC("s2twp").convert(T["text"]))
a16 = lambda m_: librosa.resample(m_[S(T["start"] - 0.3):S(T["end"] + 0.35)].mean(1), orig_sr=SR, target_sr=16000)
h0, h1 = hear(a16(mix)), hear(a16(new_mix))
m0, m1 = "".join(miss(want, h0)), "".join(miss(want, h1))
print(f"歌詞　{want}\n換之前 {h0}（缺：{m0 or '無'}）\n換之後 {h1}（缺：{m1 or '無'}）", flush=True)
gone = [c for c in (re.sub(r"@\d+$", "", chars[0]) if chars else "") if c in m1]
if gone:
    print(f"⚠ 換上去的「{''.join(gone)}」換完還是聽不到：不要用這個檔，換來源句或換別的修法", flush=True)
elif len(m1) > len(m0):
    print("⚠ 換完聽寫比換之前更差：不要用這個檔，換來源句或換別的修法（局部重唱、改 sing 重生）", flush=True)
elif not m0:
    print("⚠ 換之前聽寫就全對：先人耳確認原本真的唱錯（聽寫只是輔助）", flush=True)
rep += ["", "| | 聽寫 | 沒聽到的字 |", "|:--|:--|:--|", f"| 歌詞 | {want} | |", f"| 換之前 | {h0} | {m0} |", f"| 換之後 | {h1} | {m1} |", "",
        f"接完：`rappers.{who}.song` 改成 `song/{out.name}` → 重跑 `songs audio` → `lyric_audit.py`、`gap_check.py {who} {src_song.name}`；**一定要人聽接點**。"]
(D / f"{out.stem}.md").write_text("\n".join(rep) + "\n", encoding="utf-8")
print(f"→ {D / (out.stem + '.md')}\n下一步：rappers.{who}.song 改成 song/{out.name}，重跑 songs audio，再跑 lyric_audit.py、gap_check.py；一定要人聽接點", flush=True)
