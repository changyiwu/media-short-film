"""嗡嗡聲（持續窄頻音）偵測。2026-11-14〈畢達哥拉斯的三個正方形〉建立。
Ming-3.0-TTS 一次念好幾句時，常有幾秒鐘「壞掉」：人聲底下疊一串固定頻率的持續音（約 940 Hz 的整數倍，
1.9／2.8／3.7／4.7／6.6 kHz…），頻譜上是一條條水平線，聽起來像高頻嗡嗡聲、音質很差；聽寫照樣全對，自動挑音擋不到。
正常人聲的共振峰會一直移動，不會在同一個頻率停好幾秒。

做法：每 1.5 秒一個窗，算 2.5～9 kHz 的平均頻譜，看最高的窄頻峰比鄰近頻段（前後各約 160 Hz 的中位數）高幾 dB；
取所有窗的最大值當 peak_db，並數有幾秒超過門檻（buzz_s）。
實測：乾淨的旁白 peak_db 約 5～7 dB；壞掉的 13～24 dB。門檻 BUZZ_DB＝10。

用法：python tone_check.py a.wav b.wav …（印每個檔的 peak_db、buzz_s）
在程式裡：from tone_check import buzz; peak_db, buzz_s = buzz(path)
"""
import sys

import numpy as np
import soundfile as sf

BUZZ_DB = 10.0      # 窄頻峰高出鄰近頻段超過這麼多 dB 算嗡嗡聲
WIN_S = 1.5
LO, HI = 2500, 9000


def _median_filter(x, k):
    pad = k // 2
    xp = np.pad(x, pad, mode="edge")
    from numpy.lib.stride_tricks import sliding_window_view
    return np.median(sliding_window_view(xp, k), axis=1)


def buzz(path, win_s=WIN_S, thr=BUZZ_DB):
    """回傳 (peak_db, buzz_s)：最嚴重那一窗的窄頻峰高度（dB），與超過門檻的總秒數。太安靜的窗（靜音）不算。"""
    x, sr = sf.read(str(path), dtype="float32")
    x = x.mean(axis=1) if x.ndim > 1 else x
    n = 4096
    fr = np.fft.rfftfreq(n, 1 / sr)
    band = (fr >= LO) & (fr <= HI)
    k = max(5, int(320 / (sr / n)) | 1)              # 鄰近頻段寬約 320 Hz
    hop = int(win_s * sr)
    level = np.sqrt((x ** 2).mean()) + 1e-9
    peaks = []
    for a in range(0, max(1, len(x) - n), hop):
        seg = x[a:a + hop]
        if len(seg) < n or np.sqrt((seg ** 2).mean()) < level * 0.2:
            continue
        fr_ = seg[: len(seg) // n * n].reshape(-1, n) * np.hanning(n)
        db = 20 * np.log10(np.abs(np.fft.rfft(fr_, axis=1)).mean(axis=0) + 1e-9)
        pk = (db - _median_filter(db, k))[band]
        peaks.append(float(pk.max()))
    if not peaks:
        return 0.0, 0.0
    peaks = np.array(peaks)
    return round(float(peaks.max()), 1), round(float((peaks > thr).sum() * win_s), 1)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        pk, s = buzz(p)
        print(f"{p}\tpeak_db={pk}\tbuzz_s={s}\t{'BUZZ' if pk > BUZZ_DB else 'ok'}")
