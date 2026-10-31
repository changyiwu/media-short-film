"""多鏡短片範本：讀 film.json，從角色定妝一路做到成片＋自審。做新片只改 film.json，這支程式不用改。
用 tools/new_film.py <類型> <片名> 建成 output/<類型>/<片名>/ 再跑；生圖預設 OpenAI（IMAGE_BACKEND=local 改本機 Qwen），其餘都是本機模型。
H3 venv 執行（同一個 cmd 視窗先 call <repo>\\configs\\profile.cmd → <repo>\\tools\\start_comfy.cmd）：
  "%PY_H3%" make_film.py [stage ...] [--film 別的設定.json]
stage（不給＝全部依序）：chars masters frames voices inserts h3 amb edl music ending cut review
旁白、後製插入鏡、疊字（narrator、shot 的 vo／insert／overlay）見本資料夾的 README.md。
每一步的輸出都在 work/，已存在的檔案會跳過，所以可以中斷後續跑、或刪掉某個檔重做：
  - 重生某一鏡首幀：刪 work/first/<鏡>.png，在 film.json 的 seeds 加 "frame_<鏡>": 新 seed，再跑 frames
  - 重拍某一鏡 H3：刪 work/h3/<鏡>/clip.mp4（或加 "h3_<鏡>": 新 seed），再跑 h3（環境變數 ONLY="S2 S5" 只跑指定鏡）
  - 改了台詞：H3 自己念的句子（預設）刪 work/h3/<鏡>/clip.mp4 再跑 h3；fixed 的句子與旁白刪 work/voice/bv 裡那句的檔，再跑 voices
台詞聲音 voice_mode（film.json 全片設，單句可在 line 裡設）："h3_ref"（預設）＝H3 拿角色參考音自己念（h3 階段結尾
tools/h3_line_harvest.py 分離人聲、聽寫、拼音比對原文，差太多就停）；"fixed"＝VoxCPM2 配音當 H3 固定音軌。旁白 vo 一律 fixed。
  - 改了剪接（cut_in、tail…）：跑 edl cut review 即可
人工關卡：frames 之後看 work/first/_sheet.jpg；h3 之後看 work/review/clips_*.jpg；review 之後一定要看成片。
完整流程見 docs/02_端到端流程.md，film.json 欄位見本資料夾的 README.md。"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path

for _s in (sys.stdout, sys.stderr):                 # 中文輸出在非 UTF-8 主控台不變亂碼
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
ARGS = [a for a in sys.argv[1:]]
FILM = HERE / (ARGS[ARGS.index("--film") + 1] if "--film" in ARGS else "film.json")
CFG = json.loads(FILM.read_text(encoding="utf-8"))
OUT = HERE / "work"; OUT.mkdir(exist_ok=True)
REPO = (HERE / CFG.get("repo_dir", "../..")).resolve()
T = Path(os.environ.get("AI_TOOLS", REPO / "tools"))     # 預設直接用 repo 的 tools/
AI_ROOT = Path(os.environ.get("AI_ROOT", r"C:\AI"))   # 安裝根目錄（profile.cmd 有設 PY_* 時以 PY_* 為準）
PYH3 = os.environ.get("PY_H3", str(AI_ROOT / "H3" / "venv" / "Scripts" / "python.exe"))
PYV = os.environ.get("PY_VOICE", str(AI_ROOT / "Voice" / "venv" / "Scripts" / "python.exe"))
SEP = str(Path(PYV).parent / ("audio-separator.exe" if os.name == "nt" else "audio-separator"))
HOST = os.environ.get("COMFY_HOST", "http://127.0.0.1:8188")
SR, FPS = 48000, 24
sys.path.insert(0, str(REPO / "tools"))
from fonts import font, SUB_FONT_NAME  # noqa: E402  (Windows 字型／Linux 用 Noto CJK)
UPSCALE = os.environ.get("UPSCALE", "rtxvsr" if os.name == "nt" else "lanczos")   # rtxvsr（只有 Windows）｜flashvsr｜lanczos


def local_h3_ok():
    """本機能不能跑 H3：NVIDIA 顯卡 ≥15GB 且記憶體 ≥30GB（桌機 16GB VRAM＋64GB RAM 剛好過）。"""
    try:
        vram = int(subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                                  capture_output=True, text=True, timeout=20).stdout.split()[0]) / 1024
    except Exception:
        return False
    try:
        if os.name == "nt":
            import ctypes
            class M(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong)] + [(f"x{i}", ctypes.c_ulonglong) for i in range(6)]
            m = M(); m.l = ctypes.sizeof(M); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)); ram = m.total / 2**30
        else:
            ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    except Exception:
        ram = 0
    return vram >= 15 and ram >= 30


# H3 在哪跑：local＝本機 ComfyUI；colab＝整批送到 Google Colab G4（cloud/colab_h3.py）；
# both＝本機＋Colab 一起跑（共用佇列，cloud/hybrid_h3.py，⚠ 尚未實測）。不設就自動判斷（local／colab）。
H3_BACKEND = os.environ.get("H3_BACKEND") or ("local" if local_h3_ok() else "colab")


def render_h3(dirs):
    """dirs 裡每個資料夾都有 spec.json；成品寫回同一個資料夾（clip.mp4、meta.json…）。"""
    if not dirs:
        return
    if H3_BACKEND == "both":
        sys.path.insert(0, str(REPO / "cloud")); from hybrid_h3 import run_hybrid   # noqa: E402
        miss = run_hybrid(dirs, PYH3, T)
        if miss:
            sys.exit(f"[h3] 這些鏡頭沒做出來：{' '.join(d.name for d in miss)}")
    elif H3_BACKEND == "colab":
        print(f"[h3] {len(dirs)} 鏡送到 Colab（cloud/colab_h3.py batch）", flush=True)
        run([sys.executable, REPO / "cloud" / "colab_h3.py", "batch"] + [d / "spec.json" for d in dirs])
    elif os.environ.get("H3_PARALLEL") == "2":           # 全雲端模式（colab_h3.py film 設定）：H3 這一步改用 2 個 ComfyUI 錯開跑
        run([PYH3, REPO / "cloud" / "vm" / "parallel_h3.py"] + dirs)
    else:
        for d in dirs:
            run([PYH3, T / "h3_shot.py", d / "spec.json", "--out", d])
CHARS, SHOTS = CFG["chars"], CFG["shots"]
# 會發聲的人：角色＋旁白（narrator，只有聲音：不生定妝、不進 H3，代號固定 "vo"）
VOICES = dict(CHARS)
if CFG.get("narrator"):
    if "vo" in CHARS:
        sys.exit('chars 不能有代號 "vo"（保留給旁白 narrator）')
    VOICES["vo"] = CFG["narrator"]
LINES = []                                                           # (鏡, {who, text, tts?, at, kind})；kind＝line（角色台詞）｜vo（旁白）
for _s in SHOTS:
    if _s.get("line"):
        LINES.append((_s["id"], {**_s["line"], "kind": "line"}))
    if _s.get("vo"):
        if "vo" not in VOICES:
            sys.exit(f"{_s['id']} 有旁白 vo，但 film.json 沒有 narrator")
        LINES.append((_s["id"], {**_s["vo"], "who": "vo", "kind": "vo"}))
INSERTS = {s["id"] for s in SHOTS if s.get("insert")}               # 後製插入鏡：不生首幀、不走 H3，inserts 階段直接做 1080p 影片
# 台詞聲音（移植自上游 2026-10-23；2026-10-24 使用者決定預設 h3_ref）：h3_ref＝H3 拿角色參考音自己念（預設；嘴型與聲音一起生成，
# 表演較生動；h3 階段結尾用 h3_line_harvest.py 抓出台詞、比對原文）｜fixed＝VoxCPM2 配音當 H3 固定音軌（要念對的名詞、數字日期、念錯抽不出來的句子）。
# 全片設 film.json 的 voice_mode，單句可在 line 裡設 "voice_mode"。旁白（vo）不進 H3，一律 fixed。讀音替換表對 h3_ref 無效（H3 照字念）。
VOICE_MODE = CFG.get("voice_mode", "h3_ref")
VOICE_ENGINE = CFG.get("voice_engine", "ming")   # 旁白與 fixed 台詞的引擎：ming（預設）｜voxcpm2；參考音設計一律 VoxCPM2
H3_CPS, H3_PAD, H3_MIN = 3.0, 2.0, 3.0                              # h3_ref 鏡長＝max(3, 字數 ÷ 3＋2 秒)：同 tools/table_read.py


def h3_says(ln):
    """這句是不是讓 H3 自己念（h3_ref）。"""
    return ln["kind"] == "line" and ln.get("voice_mode", VOICE_MODE) == "h3_ref"


def nchars(t):
    return len(re.findall(r"[一-鿿A-Za-z0-9]", t or ""))


def load_picks():
    """work/voice_picks.json：每句實際用的聲音檔（VoxCPM2 挑的，或 h3_ref 從 H3 成片分離出的人聲，source＝"h3"）。"""
    p = OUT / "voice_picks.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


MIX = CFG.get("mix", {})
TIMING = OUT / "timing.json"
timing = json.loads(TIMING.read_text(encoding="utf-8")) if TIMING.exists() else {}


def seed(key, default):
    return int(CFG.get("seeds", {}).get(key, default))


def comfy_ok():
    try:
        urllib.request.urlopen(HOST + "/system_stats", timeout=5); return True
    except Exception:
        return False


def free_comfy():
    try:
        r = urllib.request.Request(HOST + "/free", data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
                                   headers={"Content-Type": "application/json"})
        urllib.request.urlopen(r, timeout=30)
    except Exception:
        pass
    time.sleep(5)


def run(cmd, cwd=OUT, check=True, **kw):
    print("$", " ".join(map(str, cmd))[:200], flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}, stdin=subprocess.DEVNULL, **kw)
    if check and r.returncode != 0:
        raise SystemExit(f"FAILED: {' '.join(map(str, cmd))[:200]}\n{(r.stdout + r.stderr)[-2500:]}")
    return r


def newest(d, ext=".png"):
    fs = sorted(Path(d).glob(f"*{ext}"), key=lambda f: f.stat().st_mtime)
    return fs[-1] if fs else None


IMG_LOG = OUT / "image_backends.json"
IMG_BACKEND = os.environ.get("IMAGE_BACKEND", "auto")   # auto（預設：Image 2.5 API 優先、Codex CLI 次之，失敗就停）｜codex｜img25｜local（千問備選）；一支片固定一個


def gen_img(cmd):
    """跑一次 gen_image.py（預設 Image 2.5 API 優先、Codex CLI 次之，失敗就停、不自動改用千問），記下實際用的後端，片尾名單照實際寫。"""
    r = run(cmd)
    used = next((b for b in ("img25", "codex") if f"[backend] {b}" in r.stdout), "local")
    log = json.loads(IMG_LOG.read_text(encoding="utf-8")) if IMG_LOG.exists() else {}
    log[used] = log.get(used, 0) + 1
    IMG_LOG.write_text(json.dumps(log), encoding="utf-8")
    return r


def image_credit():
    """片尾的生圖工具名：依 work/image_backends.json 實際用到的後端。"""
    log = json.loads(IMG_LOG.read_text(encoding="utf-8")) if IMG_LOG.exists() else {"img25": 1}
    names = ((["OpenAI Image 2.5"] if log.get("img25") else []) + (["OpenAI 生圖（Codex）"] if log.get("codex") else [])
             + (["Qwen-Image 2.1／Edit 2511"] if log.get("local") else []))
    return "／".join(names)


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout)


def frames_for(d):
    n = 0
    while 17 * n + 5 < d * FPS:
        n += 1
    return 17 * n + 5


def stage(name):
    def deco(fn):
        def wrap():
            t0 = time.time(); a = time.strftime("%H:%M:%S"); fn()
            timing[name] = dict(sec=round(time.time() - t0, 1), start=a, end=time.strftime("%H:%M:%S"))
            TIMING.write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[stage] {name} {timing[name]['sec']}s", flush=True)
        return wrap
    return deco


def line_index(sid, kind="line"):
    return next(i for i, (s, ln) in enumerate(LINES) if s == sid and ln["kind"] == kind)


def shot_lines(s):
    """這一鏡的聲音：[(LINES 的索引, 台詞或旁白)]，角色台詞在前。"""
    return [(i, ln) for i, (sid, ln) in enumerate(LINES) if sid == s["id"]]


def insert_file(s):
    return OUT / "insert" / f"{s['id']}.mp4"


# ------------------------------------------------------------------------------------------------ 圖
SHEETS = {"turn": "turnaround sheet", "expr": "expression sheet", "face": "close-up face sheet"}
DEFAULT_SHEETS = ["turn", "expr"]


def char_refs(k, names=None):
    """首幀要附的角色參考圖：Image 2.5／Codex 依 names 從轉面圖、表情表、臉部近照挑 1–3 張（預設轉面圖＋表情表）；
    本機 Qwen 一律單張半身（Qwen 會把多格版面照抄成拼貼）。"""
    if IMG_BACKEND == "local":
        return [OUT / "chars" / f"{k}.png"]
    return [OUT / "chars" / f"{k}_{n}.png" for n in (names or DEFAULT_SHEETS)]


def shot_sheets(s, k):
    """這一鏡角色 k 要附哪幾張定妝：shot 的 "sheets" 可寫清單（所有角色共用）或 {角色: 清單}，沒寫就用 DEFAULT_SHEETS。"""
    v = s.get("sheets") or DEFAULT_SHEETS
    names = v.get(k, DEFAULT_SHEETS) if isinstance(v, dict) else v
    bad = [n for n in names if n not in SHEETS]
    if bad or not 1 <= len(names) <= 3 or len(set(names)) != len(names):
        sys.exit(f"[frames] {s['id']} 的 sheets（{k}）只能是 turn／expr／face 中 1–3 個不重複的：{names}")
    return names


@stage("chars")
def chars():
    """角色定妝（docs/07 §0；千問備選 §1）。不滿意就在 seeds 加 char_<角色> 換 seed、刪檔重跑。
    預設（Image 2.5 或 Codex）：先生轉面圖 <角色>_turn.png（純文字，角色的基準），再附它生表情表 <角色>_expr.png（同一張臉），
    最後附這兩張生臉部近照 <角色>_face.png（正面＋3/4 兩格，給特寫鏡看清五官）。
    IMAGE_BACKEND=local（千問備選）：單張、灰底、正面半身 <角色>.png。
    同時用 VoxCPM2 設計角色參考音 voice/ref_<角色>.wav（念 voice_sample）：定案後存進 output/角色/<角色>/，之後每支片複製沿用、
    不再重新設計，H3 每鏡拿同一個檔當音色參考，聲音才不會漂移。沒寫 voice_design 的角色（例：沿用原片聲音的換角）跳過。"""
    char_voices()
    for k, c in CHARS.items():
        if IMG_BACKEND == "local":
            dst = OUT / "chars" / f"{k}.png"
            if dst.exists():
                continue
            p = ("Studio character reference photo, single person only, one image (not a collage), medium close-up bust portrait facing the camera, "
                 "plain light grey seamless background, soft even studio light, sharp focus, realistic photograph. " + c["look"] + ", gentle natural expression. "
                 "No text, no watermark.")
            gen_img([PYH3, T / "gen_image.py", "--prompt", p, "--width", "1024", "--height", "1024", "--seed", seed("char_" + k, 11),
                 "--prefix", f"film/char_{k}", "--out", "chars"])
            newest(OUT / "chars").rename(dst)
            continue
        turn, expr, face = char_refs(k, ["turn", "expr", "face"])
        if not turn.exists():
            p = ("Character turnaround reference sheet of ONE single person, realistic photograph: four full-body views of the same person "
                 "side by side in one row, left to right: front view, three-quarter view, side profile, back view. Same outfit, same hairstyle, "
                 "standing in a relaxed neutral pose, head to shoes fully visible in every view, evenly spaced, plain light grey seamless background, "
                 "soft even studio light, sharp focus. " + c["look"] + ". No text, no labels, no numbers, no watermark.")
            gen_img([PYH3, T / "gen_image.py", "--prompt", p, "--width", "1536", "--height", "1024", "--seed", seed("char_" + k, 11),
                 "--prefix", f"film/char_{k}_turn", "--out", "chars"])
            newest(OUT / "chars").rename(turn)
        if not expr.exists():
            p = ("Expression reference sheet of exactly the same person as <image1> (same face, hairstyle and clothes): a 3 x 2 grid of six "
                 "head-and-shoulders close-ups facing the camera, realistic photograph. Top row: neutral, warm smile, angry. Bottom row: surprised, "
                 "sad, thinking. Natural, believable acting, not cartoonish. Plain light grey seamless background, soft even studio light, sharp focus. "
                 + c["look"] + ". No text, no labels, no numbers, no watermark.")
            gen_img([PYH3, T / "gen_image.py", "--prompt", p, "--ref", turn, "--width", "1536", "--height", "1024", "--seed", seed("char_" + k, 11),
                 "--prefix", f"film/char_{k}_expr", "--out", "chars"])
            newest(OUT / "chars").rename(expr)
        if not face.exists():
            p = ("Close-up face reference sheet of exactly the same person as <image1> and <image2> (same face, hairstyle and clothes): two "
                 "head-and-shoulders close-ups side by side, realistic photograph. Left: front view looking straight into the camera. Right: "
                 "three-quarter view, head turned about 45 degrees from the camera. Each face is large and fills most of its half, with every "
                 "facial detail sharp. Same calm neutral expression, same hairstyle and parting, same light in both. Plain light grey seamless "
                 "background, soft even studio light. " + c["look"] + ". No text, no labels, no numbers, no watermark.")
            gen_img([PYH3, T / "gen_image.py", "--prompt", p, "--ref", turn, "--ref", expr, "--width", "1536", "--height", "1024",
                 "--seed", seed("char_" + k, 11), "--prefix", f"film/char_{k}_face", "--out", "chars"])
            newest(OUT / "chars").rename(face)


def char_voices():
    """角色參考音 voice/ref_<角色>.wav：已存在（從 output/角色/ 複製來的）就沿用，只補缺的。旁白不是角色，留在 voices 階段。"""
    vd = OUT / "voice"; vd.mkdir(exist_ok=True)
    jobs = [dict(name=f"ref_{k}", text=c["voice_sample"], seed=seed("voice_" + k, 7), control=c["voice_design"])
            for k, c in CHARS.items() if c.get("voice_design") and not (vd / f"ref_{k}.wav").exists()]
    if not jobs:
        return
    free_comfy()
    (OUT / "vox_chars.json").write_text(json.dumps(dict(out_dir="voice", jobs=jobs), ensure_ascii=False, indent=1), encoding="utf-8")
    run([PYV, T / "voxcpm_batch.py", "vox_chars.json"])
    print("→ 人工試聽 work/voice/ref_<角色>.wav，定案後連同 voice_sample 存進 output/角色/<角色>/（之後不換）：",
          ", ".join(j["name"] for j in jobs), flush=True)


@stage("masters")
def masters():
    """場景母版（空景 2K），再依每鏡的 scene 框裁成該鏡景別，當首幀的場景參考（docs/07 §4）。"""
    from PIL import Image
    for k, p in CFG.get("masters", {}).items():
        dst = OUT / "masters" / f"{k}.png"
        if not dst.exists():
            gen_img([PYH3, T / "gen_image.py", "--prompt", p, "--seed", seed("master_" + k, 21), "--prefix", f"film/master_{k}", "--out", "masters"])
            newest(OUT / "masters").rename(dst)
    for s in SHOTS:
        if not s.get("scene"):
            continue
        m, box = s["scene"]; im = Image.open(OUT / "masters" / f"{m}.png").convert("RGB"); W, H = im.size
        crop = im.crop((int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)))
        crop.thumbnail((1344, 1344)); crop.save(OUT / "masters" / f"crop_{s['id']}.png")


@stage("frames")
def frames():
    """首幀：OpenAI 生圖（預設 Image 2.5 API 優先、Codex 次之）附「每個角色 1–3 張定妝（shot 的 sheets，預設轉面圖＋表情表）＋場景裁切（最後一張）」；
    IMAGE_BACKEND=local 時 Qwen-Image-Edit 附「角色單張半身＋場景裁切」。每鏡都照抄角色完整外觀描述，否則會掉眼鏡、換髮型。"""
    for s in SHOTS:
        dst = OUT / "first" / f"{s['id']}.png"
        if dst.exists() or s["id"] in INSERTS:
            continue
        refs, keep, first = [], [], {}
        for j, k in enumerate(s["refs"], start=1):
            names = shot_sheets(s, k); rs = char_refs(k, names); i = len(refs) + 1; refs += rs; first[j] = i
            missing = [r.name for r in rs if not r.exists()]
            if missing:
                sys.exit(f"[frames] {s['id']} 缺定妝 {missing}：先跑 chars")
            if IMG_BACKEND == "local":
                keep.append(f"Keep exactly the same person as <image{i}>: same face, hairstyle and clothes ({CHARS[k]['look']}).")
            else:
                pics = " and ".join(f"<image{i + j}> ({SHEETS[n]})" for j, n in enumerate(names))
                keep.append(f"{pics} {('shows', 'both show', 'all show')[len(names) - 1]} the same person "
                            f"({CHARS[k]['look']}); keep exactly that face, hairstyle and clothes.")
        if refs and IMG_BACKEND != "local":
            keep.append("The reference sheets are only for the person's identity: do NOT copy their grid layout, grey background, "
                        "labels or poses; the result is one single photo.")
        keep = " ".join(keep)
        set_s = (" " + CFG["set_sentence"].format(n=len(refs) + 1)) if s.get("scene") else ""
        # frame 裡的 <imageN> 照「第 N 個角色、最後一個是場景」寫；每個角色附的張數不同，這裡換成實際的圖號
        first[len(s["refs"]) + 1] = len(refs) + 1
        fr = re.sub(r"<image(\d+)>", lambda m: f"<image{first.get(int(m.group(1)), int(m.group(1)))}>", s["frame"])
        p = keep + set_s + " New photo: " + CFG["cine"] + fr + CFG.get("frame_suffix", " No text, no watermark, no captions.")
        cmd = [PYH3, T / "gen_image.py", "--model", "qwen-edit", "--width", "1344", "--height", "768", "--prompt", p,
               "--seed", seed("frame_" + s["id"], 5101), "--prefix", f"film/{s['id']}", "--out", "first"]
        for r in refs:
            cmd += ["--ref", r]
        if s.get("scene"):
            cmd += ["--ref", OUT / "masters" / f"crop_{s['id']}.png"]
        gen_img(cmd)
        newest(OUT / "first").rename(dst)
    sheet([OUT / "first" / f"{s['id']}.png" for s in SHOTS if s["id"] not in INSERTS], OUT / "first" / "_sheet.jpg")
    expect = [f"{s['id']}={len(s['refs'])}" for s in SHOTS if s["id"] not in INSERTS and s.get("refs")]   # 空景不查
    if expect:
        r = run([PYV, T / "face_count.py", OUT / "first", *expect], check=False)        # 只是提醒，偵測失敗不擋流程
        print(r.stdout[-1500:] if r.returncode == 0 else f"⚠ 首幀臉數檢查失敗（{r.returncode}），改人工看：\n{r.stderr[-800:]}", flush=True)
    print("→ 人工檢查 work/first/_sheet.jpg：臉、服裝、多手多腳、背景有沒有字、窗戶方向", flush=True)


def sheet(files, dst, cols=3):
    from PIL import Image, ImageDraw, ImageFont
    fs = [p for p in files if Path(p).exists()]
    if not fs:
        return
    W, H = 672, 384; rows = (len(fs) + cols - 1) // cols
    im = Image.new("RGB", (W * cols, H * rows)); f = ImageFont.truetype(font("jhbd"), 28)
    for i, p in enumerate(fs):
        t = Image.open(p).convert("RGB").resize((W, H)); ImageDraw.Draw(t).text((8, 6), Path(p).stem, font=f, fill=(255, 255, 0), stroke_width=3, stroke_fill=0)
        im.paste(t, ((i % cols) * W, (i // cols) * H))
    Path(dst).parent.mkdir(parents=True, exist_ok=True); im.save(dst, quality=85)


# ------------------------------------------------------------------------------------------------ 聲音
@stage("voices")
def voices():
    """設計角色聲音（一次）→ edge-tts 台灣國語答案卷 → 每句 8 候選 → 自動挑（聽寫拼音聲調全對＋腔調分數，已去頭尾靜音）。
    角色台詞（line）和旁白（vo）走同一套；旁白的聲音設計在 film.json 的 narrator。聲音設計與念台詞都用 VoxCPM2。
    送進 TTS 的文字會先套讀音替換表（tts-lexicon.md，由 voxcpm_batch／gen_voice／voice_pick 各自套用），字幕照原文。
    角色參考音（voice/ref_<角色>.wav，給 H3 當音色參考）在 chars 階段就做好或從 output/角色/ 複製來，這裡只補旁白的；
    h3_ref 的台詞在 h3 階段由 H3 自己念。"""
    char_voices()
    free_comfy()
    vd = OUT / "voice"; vd.mkdir(exist_ok=True)
    jobs = [dict(name=f"ref_{k}", text=c["voice_sample"], seed=seed("voice_" + k, 7), control=c["voice_design"])
            for k, c in VOICES.items() if k not in CHARS]
    fixed = [(i, sid, ln) for i, (sid, ln) in enumerate(LINES) if not h3_says(ln)]
    if not fixed:                                    # 全部 h3_ref：只要參考音
        if jobs:
            (OUT / "vox_design.json").write_text(json.dumps(dict(out_dir="voice", jobs=jobs), ensure_ascii=False, indent=1), encoding="utf-8")
            run([PYV, T / "voxcpm_batch.py", "vox_design.json"])
        print("[voices] voice_mode h3_ref：角色參考音在 work/voice/ref_<角色>.wav，台詞由 H3 在 h3 階段自己念", flush=True)
        return
    for i, sid, ln in fixed:                         # 答案卷：只拿來比腔調，不進成片
        w = vd / f"tw_{i}.wav"
        if w.exists():
            continue
        mp3 = vd / f"tw_{i}.mp3"
        r = run([PYV, T / "gen_voice.py", "--engine", "edge", "--text", ln["text"], "--voice", VOICES[ln["who"]].get("edge_voice", "zh-TW-YunJheNeural"),
                 "--out", mp3], check=False)
        if r.returncode == 0 and mp3.exists():
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", mp3, "-ar", "48000", "-ac", "1", w])
        else:                                        # 沒網路：改用設計出來的播報聲音產生答案卷（可靠度較低）
            jobs.append(dict(name=f"tw_{i}", text=ln["text"], seed=11,
                             control="A clear, neutral standard Taiwanese Mandarin news-reading voice, calm, precise tones."))
    bv = [dict(name=f"line{i}", text=ln.get("tts", ln["text"]), ref_audio=f"voice/ref_{ln['who']}.wav", ref_text=VOICES[ln["who"]]["voice_sample"],
               tw_ref=f"voice/tw_{i}.wav", seeds=8) for i, sid, ln in fixed]
    (OUT / "bv.json").write_text(json.dumps(dict(out_dir="voice/bv", jobs=bv), ensure_ascii=False, indent=1), encoding="utf-8")
    if jobs:
        (OUT / "vox_design.json").write_text(json.dumps(dict(out_dir="voice", jobs=jobs), ensure_ascii=False, indent=1), encoding="utf-8")
        run([PYV, T / "voxcpm_batch.py", "vox_design.json"])
    run([PYV, T / ("ming_batch.py" if VOICE_ENGINE == "ming" else "voxcpm_batch.py"), "bv.json"])
    run([PYV, T / "voice_pick.py", "bv.json"])
    bp = json.loads((vd / "bv" / "picks.json").read_text(encoding="utf-8"))
    picks, bad, odd = {k: v for k, v in load_picks().items() if v.get("source") == "h3"}, [], []   # 保留 h3 階段抓到的 h3_ref 台詞
    for i, sid, ln in fixed:
        p = bp[f"line{i}"]; best = next(c for c in p["cands"] if c["file"] == p["pick"])
        if p["needs_review"] and p.get("review_reason") == "sound":
            odd.append(f"{sid}「{ln['text']}」響度差 {best.get('lufs_dev')} dB、4 kHz 以上能量比 {best.get('hf_4k')}")
        elif p["needs_review"]:
            bad.append(f"{sid}「{ln['text']}」聽成「{best['asr']}」")
        picks[str(i)] = dict(shot=sid, who=ln["who"], text=ln["text"], file=str(vd / "bv" / f"line{i}.wav"), heard=best["asr"],
                             tw_score=best.get("tw_score"), lufs=best.get("lufs"), hf_4k=best.get("hf_4k"), needs_review=p["needs_review"])
        print("pick", sid, ln["text"], "→", p["pick"], best["asr"], best.get("tw_score"), best.get("lufs"), "LUFS", flush=True)
    (OUT / "voice_picks.json").write_text(json.dumps(picks, ensure_ascii=False, indent=1), encoding="utf-8")
    picks = dict(sorted(picks.items(), key=lambda kv: int(kv[0])))
    ls = [p["lufs"] for p in picks.values() if p.get("lufs") is not None]
    if ls and max(ls) - min(ls) > 6 and MIX.get("voice_lufs") is None:
        print(f"[warn] 各句原始響度差 {max(ls) - min(ls):.1f} dB（不同角色聲音大小不同）：film.json 的 mix 加 \"voice_lufs\": -20，成片才不會忽大忽小", flush=True)
    if bad and os.environ.get("ALLOW_REVIEW") != "1":
        raise SystemExit("這幾句 8 個候選聽寫都不對：" + "；".join(bad) +
                         "\n念錯的詞以後也會遇到就加進 repo 根目錄的 tts-lexicon.md（只有這支片才在片子資料夾放一份）；"
                         "只是這句就在 film.json 該句加 \"tts\"，把念錯的字換成同音字（VoxCPM2 不支援注音標記）或換說法。改完刪掉 work/voice/bv 再跑 voices；"
                         "確定只是 ASR 聽錯（例如單字喊叫）就用 ALLOW_REVIEW=1 繼續。"
                         "\n想用耳朵挑：tools/audition.py <片子資料夾> <lineN> 把候選串成一個檔，選好用 --pick sK（會記成人工挑選，重跑 voices 不會被換掉）。")
    if odd and os.environ.get("ALLOW_REVIEW") != "1":
        raise SystemExit("這幾句聽寫正確的候選音量或音質全都異常（響度離群或嘶聲）：" + "；".join(odd) +
                         "\n先聽那句的候選（tools/audition.py <片子資料夾> <lineN> 串成一個檔，標出哪幾支音量或嘶聲異常）：有能用的就 --pick sK；"
                         "全都不行就在 film.json 該句加 \"tts\" 換說法，刪掉 work/voice/bv 再跑 voices；確定原本那支可以用就 ALLOW_REVIEW=1 繼續。")


# ------------------------------------------------------------------------------------------------ H3
def shot_secs(s, picks):
    """鏡長：至少 dur，有台詞或旁白就延長到「開口時間＋長度＋0.8 秒」；H3 鏡再湊成 H3 的格數。
    h3_ref 的台詞還沒有音檔，照字數估：max(3, 字數 ÷ 3＋2 秒)（上游實測 H3 自己念每秒 2.3–4.7 字、有時晚 1.5–2.1 秒開口）。"""
    d = s["dur"]
    for i, ln in shot_lines(s):
        if h3_says(ln):
            d = max(d, H3_MIN, nchars(ln["text"]) / H3_CPS + H3_PAD)
        else:
            d = max(d, ln["at"] + dur(picks[str(i)]["file"]) + 0.8)
    return d if s["id"] in INSERTS else frames_for(d) / FPS


def h3_spec(s, secs, dialogue):
    h = CFG["h3"]
    return dict(duration=round(secs - 0.02, 3), size=[1344, 768], seed=seed("h3_" + s["id"], h.get("default_seed", 20261007)), steps=14, draft=True,
                style=h["style"], setting=s.get("setting", h["setting"]), first_frame=str(OUT / "first" / f"{s['id']}.png"),
                subjects=[dict(key=k, desc=CHARS[k]["look"], voice=CHARS[k]["h3_voice"]) for k in s["refs"]],
                shots=[dict(camera=s.get("camera", h.get("camera", "The camera holds a static shot on a tripod.")), action=s["action"], dialogue=dialogue)],
                constraints=h.get("constraints", []) + s.get("extra_constraints", []), soundscape=s.get("soundscape", h["soundscape"]), music="N/A")


@stage("h3")
def h3():
    """每鏡 H3（DMAD 4 步、只給首幀）。看得到臉的鏡頭一律給固定音軌：有台詞放配音，沒台詞放靜音（否則角色會自己嘟囔）。
    h3_ref 的台詞改給角色參考音（audio.voice_ref），H3 自己念；跑完 harvest_lines() 抓出台詞、比對原文。
    旁白（vo）不放進引導音軌：畫面裡的人不能跟著旁白動嘴。後製插入鏡跳過（inserts 階段做）。"""
    picks = load_picks()
    only = os.environ.get("ONLY", "").split(); todo = []
    for s in SHOTS:
        if (only and s["id"] not in only) or s["id"] in INSERTS:
            continue
        od = OUT / "h3" / s["id"]
        if (od / "clip.mp4").exists():
            continue
        od.mkdir(parents=True, exist_ok=True)
        secs = shot_secs(s, picks); buf = bytearray(int(secs * SR) * 2); dlg = []
        if s.get("line") and h3_says({**s["line"], "kind": "line"}):
            ln = s["line"]
            dlg = [dict(subject=ln["who"], line=ln["text"], lang="Chinese", after="Right after the line the speaker's lips close and stay closed.")]
            spec = h3_spec(s, secs, dlg)
            spec["audio"] = {"voice_ref": {"subject": ln["who"], "file": str(OUT / "voice" / f"ref_{ln['who']}.wav")}}
            (od / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
            todo.append(od)
            continue
        if s.get("line"):
            ln = s["line"]; f = picks[str(line_index(s["id"], "line"))]["file"]
            pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", f, "-ar", str(SR), "-ac", "1", "-f", "s16le", "-"], capture_output=True).stdout
            st = int(ln["at"] * SR) * 2; seg = pcm[: len(buf) - st]; buf[st:st + len(seg)] = seg
            dlg = [dict(subject=ln["who"], line=ln["text"], lang="Chinese", after="Right after the line the speaker's lips close and stay closed.")]
        with wave.open(str(od / "guide.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(bytes(buf))
        spec = h3_spec(s, secs, dlg); spec["audio"] = {"fixed": {"file": str(od / "guide.wav")}}
        (od / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
        todo.append(od)
    render_h3(todo)
    harvest_lines()
    sheet_clips()


def harvest_lines():
    """h3_ref 的台詞：H3 成片 → tools/h3_line_harvest.py（分離人聲、聽寫、拼音比對原文、切出那句）→ work/voice/h3/line<i>.wav，
    寫進 voice_picks.json（source "h3"、at＝實際開口秒數）。H3 會改用詞、偶爾晚開口；聽寫和原文差太多就停下來換 seed。"""
    picks, bad = load_picks(), []
    hd = OUT / "voice" / "h3"; hd.mkdir(parents=True, exist_ok=True)
    for i, (sid, ln) in enumerate(LINES):
        clip = OUT / "h3" / sid / "clip.mp4"
        if not h3_says(ln) or not clip.exists():
            continue
        dst = hd / f"line{i}.wav"; p = picks.get(str(i), {})
        if p.get("source") == "h3" and dst.exists() and dst.stat().st_mtime >= clip.stat().st_mtime:
            if p.get("needs_review"):
                bad.append(f"{sid}「{ln['text']}」聽成「{p['heard']}」")
            continue                                 # 已抓過、而且鏡頭沒重拍
        free_comfy()
        r = run([PYV, T / "h3_line_harvest.py", "--clip", clip, "--text", ln["text"], "--out", dst, "--work", hd / f"{sid}_work"])
        h = json.loads(r.stdout.strip().splitlines()[-1])
        picks[str(i)] = dict(shot=sid, who=ln["who"], text=ln["text"], file=str(dst), heard=h["heard"], at=h["at"],
                             match=h["match"], tone_match=h["tone_match"], needs_review=h["needs_review"], source="h3")
        print(f"line {sid}: H3 念「{h['heard']}」（拼音相似 {h['match']:.2f}、含聲調 {h['tone_match']:.2f}，{h['at']:.2f}–{h['end']:.2f} 秒）", flush=True)
        if h["needs_review"]:
            bad.append(f"{sid}「{ln['text']}」聽成「{h['heard']}」")
    (OUT / "voice_picks.json").write_text(json.dumps(dict(sorted(picks.items(), key=lambda kv: int(kv[0]))), ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    if bad and os.environ.get("ALLOW_REVIEW") != "1":
        raise SystemExit("H3 念的台詞和原文差太多：" + "；".join(bad) +
                         "\n在 film.json 的 seeds 加 \"h3_<鏡>\": 新數字、刪 work/h3/<鏡>/clip.mp4，再 set ONLY=<鏡> 跑 h3；抽 2–3 次都不對就在該句 line 加 "
                         "\"voice_mode\": \"fixed\"（改用固定音軌，先跑 voices 再刪 clip 重跑 h3）。確定只是聽寫聽錯就用 ALLOW_REVIEW=1 繼續。")


@stage("inserts")
def inserts():
    """後製插入鏡（shot 有 insert）：不走首幀與 H3，直接做 1920×1080、24fps、無聲的影片 work/insert/<鏡>.mp4。
    insert 二選一：{"image": "圖.png"}＝靜態圖撐滿鏡長；{"script": "inserts/x.py", "args": [...]}＝用 PY_H3 跑片子資料夾裡的腳本，
    腳本會收到 args 之後再加 --out <mp4> --dur <秒> --fps 24 --size 1920x1080。鏡長＝dur，有旁白就延長到念完＋0.8 秒。
    改了腳本或參數：刪 work/insert/<鏡>.mp4 再跑 inserts。"""
    picks = load_picks()
    (OUT / "insert").mkdir(exist_ok=True)
    for s in SHOTS:
        if s["id"] not in INSERTS or insert_file(s).exists():
            continue
        ins, secs, dst = s["insert"], shot_secs(s, picks), insert_file(s)
        if ins.get("image"):
            run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", HERE / ins["image"], "-t", f"{secs:.3f}", "-r", str(FPS),
                 "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                 "-c:v", "libx264", "-crf", "14", dst])
        elif ins.get("script"):
            run([PYH3, HERE / ins["script"], *ins.get("args", []), "--out", dst, "--dur", f"{secs:.3f}", "--fps", FPS, "--size", "1920x1080"], cwd=HERE)
        else:
            sys.exit(f"{s['id']} 的 insert 要有 image 或 script")
        print(f"insert {s['id']}: {secs:.2f} 秒", flush=True)
    sheet_clips()


def clip_of(s):
    """這一鏡的原始影片：後製插入鏡是 work/insert/<鏡>.mp4，其他是 H3 的 work/h3/<鏡>/clip.mp4。"""
    return insert_file(s) if s["id"] in INSERTS else OUT / "h3" / s["id"] / "clip.mp4"


def sheet_clips():
    from PIL import Image
    rv = OUT / "review"; rv.mkdir(exist_ok=True)
    for s in SHOTS:
        c = clip_of(s)
        if not c.exists():
            continue
        d = dur(c); tiles = []
        for q in (0.08, 0.3, 0.5, 0.7, 0.85, 0.97):
            raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{d * q:.2f}", "-i", str(c), "-frames:v", "1", "-vf", "scale=448:256",
                                  "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
            if len(raw) == 448 * 256 * 3:
                tiles.append(Image.frombytes("RGB", (448, 256), raw))
        im = Image.new("RGB", (448 * 6, 256))
        for i, t in enumerate(tiles):
            im.paste(t, (448 * i, 0))
        im.save(rv / f"clips_{s['id']}.jpg", quality=82)
    print("→ 人工檢查 work/review/clips_*.jpg：換臉、多出人、多手多腳、鏡頭漂移、背景同學亂動", flush=True)


@stage("amb")
def amb():
    """有動作音效的鏡頭（amb: true）：用同一張首幀另拍一支「H3 原生音效」版，聽寫確認沒有人聲後，只取它的音軌當環境音。"""
    res = {}; todo = []
    picks = load_picks()
    for s in SHOTS:
        if not s.get("amb") or s["id"] in INSERTS:
            continue
        od = OUT / "h3" / f"{s['id']}_amb"; od.mkdir(parents=True, exist_ok=True)
        if not (od / "clip.mp4").exists():
            spec = h3_spec(s, shot_secs(s, picks), [])
            spec["seed"] = int(s.get("amb_seed", spec["seed"]))      # 不寫 audio 欄位＝H3 原生音效
            (od / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
            todo.append(od)
    render_h3(todo)
    for s in SHOTS:
        if not s.get("amb") or s["id"] in INSERTS:
            continue
        od = OUT / "h3" / f"{s['id']}_amb"
        run([PYV, T / "stt.py", "--audio", od / "clip.mp4", "--outdir", od / "stt"], check=False)
        heard = (od / "stt" / "transcript.txt").read_text(encoding="utf-8").strip() if (od / "stt" / "transcript.txt").exists() else ""
        speech = len(re.findall(r"[\u4e00-\u9fff]", heard))
        if speech <= 1:
            res[s["id"]] = str(od / "clip.mp4"); print(f"amb {s['id']}: OK（聽寫沒有人聲）", flush=True)
        else:
            print(f"amb {s['id']}: 有人聲「{heard}」→ 不用；換 amb_seed 再跑 amb，或改用 sfx/ 音效", flush=True)
    (OUT / "post").mkdir(exist_ok=True)
    (OUT / "post" / "amb.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


# ------------------------------------------------------------------------------------------------ 剪接、配樂、片尾、成片
def ending_on():
    """片尾是選用、預設不加（2026-10-17）：film.json 的 ending.enabled 為 true，或設 ENDING=1，才做片尾、接進成片。"""
    e = CFG.get("ending")
    return bool(e) and (e.get("enabled", False) or os.environ.get("ENDING") == "1")


def ending_secs():
    e = CFG.get("ending")
    return len(e["cards"]) * e.get("card_dur", 3.3) + e.get("title_dur", 7.5) if ending_on() else 0.0


@stage("edl")
def edl():
    """時間軸：依配音長度與 cut_in／cut_out／tail 算每鏡在成片中的位置，寫 work/post/edl.json（cut、review 都讀它）。
    cut_in＝裁掉鏡頭開頭幾秒（H3 常晚開口）；cut_out＝"full" 用到鏡尾，不寫＝最後一句台詞或旁白結束＋tail 秒（反應停頓）。
    後製插入鏡預設用到鏡尾（鏡長已經含旁白念完後的停留）。"""
    picks = load_picks()
    amb_files = json.loads((OUT / "post" / "amb.json").read_text(encoding="utf-8")) if (OUT / "post" / "amb.json").exists() else {}
    lead = MIX.get("say_lead", 0.2); t, rows = 0.0, []
    for s in SHOTS:
        ins = s["id"] in INSERTS
        # 修剪點一律對齊 1/24 秒：cut 階段每段用 -frames:v 取整數格，沒對齊的話每鏡多／少零點幾格、累積起來畫面會落後聲音
        cd = dur(clip_of(s)); a = round(float(s.get("cut_in", 0.0)) * FPS) / FPS; b = s.get("cut_out", "full" if ins else None); lines = []; end = None
        for i, ln in shot_lines(s):
            p = picks[str(i)]; d = dur(p["file"])
            # H3 自己念的（source h3）：用聽寫抓到的實際開口時間、不提前（嘴型和聲音本來就一起生成）；VoxCPM2 的照 at 並提前 say_lead
            at, ld = (float(p["at"]), 0.0) if p.get("source") == "h3" else (ln["at"], lead)
            lines.append(dict(id=f"line{i}", who=ln["who"], kind=ln["kind"], text=ln["text"], file=p["file"],
                              film_start=round(t + at - a - ld, 3), film_end=round(t + at - a - ld + d, 3)))
            end = max(end or 0, at + d)
        if b is None and end is not None:
            b = end + s.get("tail", MIX.get("default_tail", 0.55))
        b = cd if b in (None, "full") else min(float(b), cd)
        b = min(round(b * FPS), int(cd * FPS + 1e-6)) / FPS
        rows.append(dict(id=s["id"], start=round(t, 3), dur=round(b - a, 3), src_in=a, src_out=round(b, 3), lines=lines, amb=amb_files.get(s["id"]),
                         src=str(clip_of(s)), insert=ins, overlay=s.get("overlay", [])))
        t += b - a
    e = dict(shots=rows, story_end=round(t, 3), total=round(t + ending_secs(), 3))
    (OUT / "post").mkdir(exist_ok=True)
    (OUT / "post" / "edl.json").write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"本片 {t:.2f} 秒＋片尾 {ending_secs():.1f} 秒＝{e['total']:.2f} 秒", flush=True)


def load(p):
    import numpy as np
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(p), "-ar", str(SR), "-ac", "1", "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, np.float32).copy()


@stage("music")
def music():
    """配樂：Music 3 純器樂多 seed → BS-RoFormer 分離 → 挑人聲殘留最少、長度夠的那首的純器樂軌。
    乾淨的（人聲殘留 ≤ MUSIC_CLEAN）都不夠長時，拿最乾淨的那首用交叉淡入接長（extend_music），不靠多寫段數硬拉長。"""
    import numpy as np
    e = json.loads((OUT / "post" / "edl.json").read_text(encoding="utf-8")); secs = int(e["total"] + 4)
    m = CFG["music"]; md = OUT / "music"; md.mkdir(exist_ok=True)
    (md / "cap.txt").write_text(m["caption"], encoding="utf-8")
    # 14 個 [Instrumental]：少於 14 會太短；加 Verse 會冒人聲。實測多寫段數（20 段）也不保證變長（56～103 秒），
    # 反而開始唱歌（人聲殘留 0.0002 → 0.23～0.91，2026-10-19）→ 段數固定，長度不夠改用 extend_music 接長
    (md / "lyr.txt").write_text("[Intro]\n" + "[Instrumental]\n" * 14 + "[Outro]\n[Instrumental]\n", encoding="utf-8")
    for sd_ in m.get("seeds", [7, 23, 51]):
        sd = md / f"s{sd_}"; sd.mkdir(exist_ok=True)
        if not list(sd.glob("*.flac")):
            run([PYH3, T / "gen_music3.py", "--caption-file", md / "cap.txt", "--lyrics-file", md / "lyr.txt", "--seconds", secs, "--seed", sd_,
                 "--prefix", f"audio/MM3/film_{sd_}", "--out", sd])
    free_comfy(); rows = []
    for sd_ in m.get("seeds", [7, 23, 51]):
        sd = md / f"s{sd_}"; src = next(sd.glob("*.flac"))
        if not list(sd.glob("*Instrumental*.wav")):
            run([SEP, src, "--model_filename", "model_bs_roformer_ep_317_sdr_12.9755.ckpt", "--model_file_dir", AI_ROOT / "Voice" / "models" / "separator",
                 "--output_dir", sd, "--output_format", "WAV"])
        voc = load(next(sd.glob("*Vocals*.wav"))); ins = load(next(sd.glob("*Instrumental*.wav")))
        ratio = float(np.sqrt((voc ** 2).mean()) / (np.sqrt((ins ** 2).mean()) + 1e-9)); d = len(ins) / SR
        print(f"music s{sd_}: 人聲殘留 {ratio:.4f}，{d:.1f} 秒", flush=True)
        rows.append((ratio, d, next(sd.glob("*Instrumental*.wav"))))
    clean = [r for r in rows if r[0] <= MUSIC_CLEAN]
    long_clean = [r for r in clean if r[1] >= e["total"]]
    if long_clean:                                   # 乾淨又夠長：挑最乾淨的
        ratio, d, f = min(long_clean); pick = dict(file=str(f), vocal_ratio=ratio)
    elif clean:                                      # 乾淨的都不夠長：最乾淨的那首接長
        ratio, d, f = min(clean)
        pick = dict(file=str(extend_music(f, e["total"] + 4, OUT / "post" / "music_extended.wav")), vocal_ratio=ratio, extended_from=str(f))
        print(f"music：乾淨的都不夠長，把 {Path(f).parent.name}（{d:.1f} 秒）交叉淡入接長到 {e['total'] + 4:.0f} 秒，請聽接點", flush=True)
    else:
        long_any = [r for r in rows if r[1] >= e["total"]]
        if not long_any:
            raise SystemExit("沒有一首配樂夠長：把 music.seeds 換掉再跑 music")
        ratio, d, f = min(long_any); pick = dict(file=str(f), vocal_ratio=ratio)
        print(f"music：沒有一首人聲殘留 ≤ {MUSIC_CLEAN}，先用 {Path(f).parent.name}（{ratio:.4f}）；成片要聽有沒有歌聲，或換 music.seeds", flush=True)
    (OUT / "post" / "music_pick.json").write_text(json.dumps(pick, ensure_ascii=False), encoding="utf-8")


MUSIC_CLEAN = 0.01      # 人聲殘留比 ≤ 這個值才算乾淨（14 段的純器樂實測約 0.0002；開始唱歌的是 0.2 以上）


def extend_music(src, need_sec, dst, xfade=3.0, loop_from=0.15):
    """配樂不夠長時接長：先切掉曲尾淡出（不然會「音樂收掉→又開始」），再從曲子 15% 處（跳過前奏）接一次，
    接點 3 秒交叉淡入（等功率），接到 need_sec 為止。"""
    import numpy as np
    x = load(src); n_need = int(need_sec * SR); k = int(xfade * SR); start = int(len(x) * loop_from)
    w = SR // 2; rms = np.sqrt((x[: len(x) // w * w].reshape(-1, w) ** 2).mean(axis=1))
    quiet = rms < np.median(rms) * 0.316                         # 比典型音量小 10 dB 以上算安靜
    end = len(x)                                                  # 曲子最後四分之一裡，第一段連續安靜 ≥ 1 秒的地方就是結尾（停頓、收尾和弦、淡出都切掉）
    for i in range(int(len(rms) * 0.75), len(rms) - 1):
        if quiet[i] and quiet[i + 1]:
            end = i * w; break
    for i in range(start // w, len(rms) - 4):                     # 接回去的點也要避開安靜段：15% 之後第一段連續 2 秒有聲的地方
        if not quiet[i:i + 4].any():
            start = i * w; break
    out = x[:max(end, start + 2 * k)].copy()
    while len(out) < n_need:
        seg = x[start:]
        t = np.linspace(0, np.pi / 2, k, dtype=np.float32)
        out = np.concatenate([out[:-k], out[-k:] * np.cos(t) + seg[:k] * np.sin(t), seg[k:]])
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-c:a", "pcm_f32le", str(dst)],
                   input=out[:n_need].astype(np.float32).tobytes(), check=True)
    return dst


@stage("ending")
def ending():
    """片尾：特寫靜幀＋AI 工具名單＋片名（templates/ending）。MiniMax Music3 授權要求標示、公開內容要標示 AI 生成。"""
    e = CFG.get("ending")
    if not ending_on():
        return
    from PIL import Image
    ed = OUT / "ending"; (ed / "frames").mkdir(parents=True, exist_ok=True)
    cards = []
    up_name = {"flashvsr": "FlashVSR", "lanczos": "lanczos"}.get(UPSCALE)        # 片尾名單照實際做法寫（2026-10-10 新 agent 測試指出）
    for i, tools in enumerate(e["cards"]):
        sid = e["closeups"][i % len(e["closeups"])]
        Image.open(OUT / "first" / f"{sid}.png").convert("RGB").save(ed / "frames" / f"close{i + 1}.png")
        if up_name:
            tools = [[t[0].replace("RTX VSR", up_name), t[1]] for t in tools]
        tools = [[image_credit() if ("Image 2.5" in t[0] or t[0].startswith("Qwen-Image")) else t[0], t[1]] for t in tools]
        cards.append(dict(image=f"frames/close{i + 1}.png", tools=tools))
    header = e.get("header", "本片使用的 AI 工具")
    if "本機" in header and (os.name != "nt" or H3_BACKEND in ("colab", "both")):
        header = "本片使用的 AI 工具（" + ("在 Google Colab 執行" if os.name != "nt" else
                                       "影片在本機與 Google Colab 生成" if H3_BACKEND == "both" else "影片在 Google Colab 生成") + "）"
    cfg = {"_base": str(ed), "title": e.get("title", CFG["title"]), "header": header, "card_dur": e.get("card_dur", 3.3),
           "title_dur": e.get("title_dur", 7.5), "out": "ending.mp4", "cards": cards}
    (ed / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    run([PYH3, REPO / "templates" / "ending" / "render_ending.py", ed / "config.json"])


def ass_time(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def overlay_pngs(r, od):
    """這一鏡的後製疊字（shot 的 overlay）：每項畫成一張 1920×1080 透明 PNG，回傳 [(png, 開始秒, 結束秒)]（秒數以這一鏡在成片裡的開頭為 0）。
    overlay 每項：text（必填，可用 \\n 換行）、start（預設 0）、end（預設鏡尾）、pos（center｜top｜bottom｜top-left｜top-right｜bottom-left｜bottom-right，
    預設 center）、size（字級，預設 72）、color（預設白）、font（kai 標楷｜jh｜jhbd 粗黑，預設 jhbd）。字一律後製，不交給生成模型畫。"""
    from PIL import Image, ImageDraw, ImageFont
    res = []
    for j, o in enumerate(r.get("overlay") or []):
        im = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        size = int(o.get("size", 72)); f = ImageFont.truetype(font(o.get("font", "jhbd")), size); sw = max(2, size // 14)
        x0, y0, x1, y1 = d.multiline_textbbox((0, 0), o["text"], font=f, spacing=size // 3, stroke_width=sw, align="center")
        w, h = x1 - x0, y1 - y0; pos = o.get("pos", "center"); m = 80
        x = {"left": m, "right": 1920 - m - w}.get(pos.split("-")[-1], (1920 - w) // 2)
        y = m if pos.startswith("top") else (1080 - m - h if pos.startswith("bottom") else (1080 - h) // 2)
        d.multiline_text((x - x0, y - y0), o["text"], font=f, fill=o.get("color", "#FFFFFF"), spacing=size // 3, stroke_width=sw,
                         stroke_fill=(0, 0, 0, 200), align="center")
        od.mkdir(parents=True, exist_ok=True); png = od / f"{r['id']}_{j}.png"; im.save(png)
        a = float(o.get("start", 0)); b = r["dur"] if o.get("end") is None else float(o["end"])
        res.append((png, a, min(b, r["dur"])))
    return res


@stage("cut")
def cut():
    """RTX VSR 放大 → 依 edl 剪接 → 混音（台詞提前 say_lead 秒、配樂台詞期間壓低）→ 響度 → 1080p 燒字幕 → 手機版。"""
    import numpy as np
    e = json.loads((OUT / "post" / "edl.json").read_text(encoding="utf-8")); post = OUT / "post"
    vsr = post / "vsr"; vsr.mkdir(exist_ok=True); seg = post / "seg"; seg.mkdir(exist_ok=True); parts = []
    for r in e["shots"]:
        src = Path(r.get("src") or OUT / "h3" / r["id"] / "clip.mp4"); v = vsr / f"{r['id']}.mp4"
        if v.exists() and v.stat().st_mtime < src.stat().st_mtime:
            v.unlink()                               # 重拍過：重新放大（upscale_vsr.py 不覆寫舊檔）
        if r.get("insert") or UPSCALE == "lanczos":  # 後製插入鏡本來就是 1080p；Linux／Colab 沒有 RTX VSR：直接用下面 ffmpeg 的 lanczos 放大
            v = src
        elif UPSCALE == "flashvsr":
            fv = vsr / r["id"]
            if not (fv / "clip.mp4").exists() or (fv / "clip.mp4").stat().st_mtime < src.stat().st_mtime:
                run([PYH3, T / "flashvsr_cli.py", src, fv])
            v = fv / "clip.mp4"
        elif not v.exists():
            run([PYH3, T / "upscale_vsr.py", "--source", src, "--output", v])
        p = seg / f"{r['id']}.mp4"
        ovs = overlay_pngs(r, post / "overlay")
        vf = "[0:v]scale=1920:1080:flags=lanczos,fps=24[b0]" + "".join(
            f";[b{j}][{j + 1}:v]overlay=0:0:enable='between(t,{a_:.3f},{b_:.3f})'[b{j + 1}]" for j, (_, a_, b_) in enumerate(ovs))
        vf += f";[b{len(ovs)}]format=yuv420p[vout]"
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{r['src_in']:.3f}", "-i", v, *[x for png, _, _ in ovs for x in ("-i", png)],
             "-frames:v", str(round(r["dur"] * FPS)), "-an", "-filter_complex", vf, "-map", "[vout]",
             "-c:v", "libx264", "-crf", "14", "-preset", "medium", p])
        parts.append(p)
    if ending_on():
        parts.append(OUT / "ending" / "ending.mp4")
    (post / "list.txt").write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", post / "list.txt", "-c", "copy", post / "video.mp4"])
    vtotal = dur(post / "video.mp4"); n = int(vtotal * SR) + SR
    voice = np.zeros(n, np.float32); amb_ = np.zeros(n, np.float32); duck = np.ones(n, np.float32)
    under = MIX.get("music_under_lines", 0.30)
    vlufs = MIX.get("voice_lufs")                    # 選填：每句（台詞、旁白）先調到同一個響度（LUFS，聽感音量）再混，不同聲音才不會一大一小
    vclean = post / "voice"; vclean.mkdir(exist_ok=True)
    for r in e["shots"]:
        for l in r["lines"]:
            # 每句先濾：highpass 去低頻轟聲、lowpass 11 kHz 濾嘶聲、adeclick 削爆破音（爆破音會在取樣點之間衝高真峰值，降 target_lufs 也壓不下來）
            cl = vclean / f"{l['id']}.wav"
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", l["file"], "-af", "highpass=f=70,lowpass=f=11000,adeclick", "-ar", str(SR), "-ac", "1",
                 "-c:a", "pcm_f32le", cl])
            a = load(cl); s0 = int(l["film_start"] * SR)
            if vlufs is not None:                    # 用 LUFS 不用 RMS：同 RMS 的低沉男聲聽起來比女聲小
                m = re.findall(r"I:\s*(-?[\d.]+) LUFS", subprocess.run(["ffmpeg", "-i", cl, "-af", "ebur128", "-f", "null", "-"],
                                                                        capture_output=True, text=True, encoding="utf-8", errors="replace").stderr)
                if m:
                    a = a * 10 ** ((float(vlufs) - float(m[-1])) / 20)
            voice[s0:s0 + len(a)] += a[: n - s0]
            duck[max(0, int((l["film_start"] - 0.25) * SR)):int((l["film_end"] + 0.35) * SR)] = under
        if r.get("amb"):                             # amb 階段確認過沒有人聲的 H3 原生音效
            a = load(r["amb"])[int(r["src_in"] * SR):int(r["src_out"] * SR)]
            fade = np.minimum(1, np.minimum(np.arange(len(a)) / (0.15 * SR), (len(a) - np.arange(len(a))) / (0.15 * SR)))
            s0 = int(r["start"] * SR); amb_[s0:s0 + len(a)] += (a * fade * MIX.get("amb_gain", 0.8))[: n - s0]
    sg = {s["id"]: s["music_gain"] for s in SHOTS if s.get("music_gain")}   # 選填：某一鏡的配樂倍數（例：結尾只有字卡、沒旁白，配樂要聽得到）
    for r in e["shots"]:
        if r.get("id") in sg:
            a, b = int(r["start"] * SR), int((r["start"] + r["dur"]) * SR); duck[a:b] *= sg[r["id"]]
    k = int(0.12 * SR); duck = np.convolve(duck, np.ones(k) / k, mode="same")
    if sg:                                           # 倍數變化再多平滑 0.5 秒，不會突然跳大聲
        k2 = SR // 2; duck = np.convolve(np.pad(duck, (k2, k2), mode="edge"), np.ones(k2) / k2, mode="same")[k2:-k2]
    mus = load(json.loads((post / "music_pick.json").read_text(encoding="utf-8"))["file"])[:n]; mus = np.pad(mus, (0, n - len(mus)))
    if MIX.get("music_level"):                       # 選填：配樂比自己的典型音量大的地方壓回典型音量（不放大小聲處），兩句之間才不會突然爆出來
        w = SR // 2; m_ = len(mus) // w * w
        env = np.sqrt((mus[:m_].reshape(-1, w) ** 2).mean(axis=1)) + 1e-9
        g = np.minimum(1.0, np.median(env[env > env.max() * 0.01]) / env)
        k_ = 3; gp = np.pad(g, (k_, k_), mode="edge")
        g = np.array([gp[i:i + 2 * k_ + 1].min() for i in range(len(g))])   # 先取前後 1.5 秒內最小的增益，短暫的爆音也壓得到
        g = np.convolve(np.pad(g, (k_, k_), mode="edge"), np.ones(2 * k_ + 1) / (2 * k_ + 1), mode="valid")   # 再平滑 1.5 秒，不會一抽一抽
        g = np.interp(np.arange(len(mus)), np.arange(len(g)) * w + w / 2, g)
        mus = mus * g.astype(np.float32)
    mus = mus / (np.sqrt((mus[: int(e["story_end"] * SR)] ** 2).mean()) + 1e-9) * MIX.get("music_bed_rms", 0.035)
    t = np.arange(n) / SR
    mix = voice + amb_ + mus * duck * np.clip((vtotal - t) / 3.0, 0, 1) * np.clip(t / 0.8, 0, 1)
    raw = post / "mix_raw.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1", "-i", "-", "-c:a", "pcm_f32le", str(raw)],
                   input=mix[: int(vtotal * SR)].astype(np.float32).tobytes(), check=True)
    # 響度：固定增益 → 4 倍超取樣限幅（近似真峰值限幅；alimiter 一定要 level=false，預設會把峰值拉到 0 dBFS）→ 編成成片用的 AAC 再量
    # 響度與真峰值（review pass4 量的就是 AAC）：響度差太多調增益、真峰值超過 -1 dBTP 就壓低限幅門檻，最多 8 次
    target = MIX.get("target_lufs", -15.0); tp_max = -1.2; gain, lim = 0.0, 0.78
    for _ in range(8):
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af", f"volume={gain:.2f}dB,aresample={SR * 4},"
             f"alimiter=limit={lim:.3f}:level=false:attack=2:release=80,aresample={SR}", "-c:a", "pcm_s24le", post / "mix.wav"])
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", post / "mix.wav", "-c:a", "aac", "-b:a", "256k", post / "mix_check.m4a"])
        r = subprocess.run(["ffmpeg", "-i", str(post / "mix_check.m4a"), "-af", "ebur128=peak=true", "-f", "null", "-"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        summ = r.stderr[r.stderr.rfind("Summary:"):]
        m = re.search(r"I:\s*(-?[\d.]+) LUFS", summ); pk = re.search(r"Peak:\s*(-?[\d.]+) dBFS", summ)
        got = float(m.group(1)) if m else target; tp = float(pk.group(1)) if pk else -99
        print(f"混音 增益 {gain:+.2f} dB、限幅 {lim:.3f} → {got:.1f} LUFS、真峰值 {tp:.1f} dBFS", flush=True)
        if abs(got - target) <= 0.4 and tp <= tp_max:
            break
        if tp > tp_max:
            lim = max(0.25, lim * 10 ** ((tp_max - 0.3 - tp) / 20))
        if abs(got - target) > 0.4:
            gain += target - got
    else:
        print(f"[warn] 混音 8 次還沒同時達標（{got:.1f} LUFS、真峰值 {tp:.1f}）：看 mix.music_bed_rms 是否太大、或某句配音有爆音", flush=True)
    # 字幕（ASS，依說話者上色，放大到 1080p 之後才燒）
    hdr = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n[V4+ Styles]\n"
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
           "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
    for k, c in VOICES.items():
        hdr += f"Style: {k},{SUB_FONT_NAME},58,{c.get('sub_color', '&H00FFFFFF')},&H000000FF,&H00101010,&H80000000,-1,0,0,0,100,100,1,0,1,4,1,2,60,60,70,1\n"
    ev = "\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    caps = sorted([(l, r) for r in e["shots"] for l in r["lines"]], key=lambda x: x[0]["film_start"])
    for i, (l, r) in enumerate(caps):
        a = l["film_start"] - 0.05; b = l["film_end"] + 0.45
        if i + 1 < len(caps):
            b = min(b, caps[i + 1][0]["film_start"] - 0.1)
        b = min(b, r["start"] + r["dur"] - 0.04)
        v = VOICES[l["who"]]                         # 旁白預設不加「名字：」（narrator.sub_prefix 設 true 才加）
        name = f"{v['name']}：" if v.get("sub_prefix", l["who"] != "vo") else ""
        ev += f"Dialogue: 0,{ass_time(a)},{ass_time(b)},{l['who']},,0,0,0,,{name}{l['text']}\n"
    (post / "subs.ass").write_text(hdr + ev, encoding="utf-8")
    (OUT / "cut").mkdir(exist_ok=True)
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", "post/video.mp4", "-i", "post/mix.wav", "-vf", "subtitles=post/subs.ass", "-map", "0:v", "-map", "1:a",
         "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", "-shortest",
         "cut/film_1080p.mp4"])
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", OUT / "cut" / "film_1080p.mp4", "-vf", "scale=1280:720", "-c:v", "libx264", "-crf", "26",
         "-c:a", "aac", "-b:a", "128k", OUT / "cut" / "film_720p_phone.mp4"])
    print(f"成片 work/cut/film_1080p.mp4（{vtotal:.2f} 秒）", flush=True)


@stage("review")
def review():
    """自審五遍（review.py）：1 逐鏡抽格、2 成片聽寫、3 雜訊、4 黑畫面／定格／響度、5 切點明暗／台詞重疊／台詞被鏡尾切掉。"""
    c = OUT / "cut" / "film_1080p.mp4"
    for r in (run([PYH3, HERE / "review.py", c], check=False), run([PYV, HERE / "review.py", c, "--asr"], check=False)):
        print(r.stdout[-3000:], flush=True)
        if r.returncode != 0:                                    # 自審失敗不能悄悄略過
            print(f"⚠ review.py 失敗（{r.returncode}）：\n{r.stderr[-2000:]}", flush=True)
    print("→ 看 work/review/：film_1080p_pass1.jpg、pass5_cuts.jpg、review.json、asr.json；最後一定要人看成片", flush=True)


STAGES = dict(chars=chars, masters=masters, frames=frames, voices=voices, inserts=inserts, h3=h3, amb=amb, edl=edl, music=music, ending=ending, cut=cut,
              review=review)

if __name__ == "__main__":
    names = [a for i, a in enumerate(ARGS) if a in STAGES]
    need = ({"music"} | ({"chars", "masters", "frames"} if IMG_BACKEND == "local" or os.environ.get("IMAGE_FALLBACK") == "1" else set())   # 只用 Image 2.5／Codex 時不用 ComfyUI
            | ({"h3", "amb"} if H3_BACKEND in ("local", "both") else set()))
    print(f"[make_film] IMAGE_BACKEND={IMG_BACKEND}  H3_BACKEND={H3_BACKEND}  UPSCALE={UPSCALE}", flush=True)
    if need & set(names or STAGES) and not comfy_ok():
        sys.exit(f"ComfyUI not running at {HOST}: call configs\\profile.cmd, then {T / 'start_comfy.cmd'}")
    for name in (names or list(STAGES)):
        STAGES[name]()
    print("timing", json.dumps({k: v["sec"] for k, v in timing.items()}, ensure_ascii=False), flush=True)
