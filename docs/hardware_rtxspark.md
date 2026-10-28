# 硬體說明：RTX Spark 筆電（Windows on Arm＋64GB 統一記憶體）

> **狀態：第一次上機進行中（2026-10-28，第 1–5 步完成，結果見〈實機結果〉）。** 本文件原本是依上游 16GB 版的實測數據、NVIDIA 公開資訊與 PyPI 套件掃描推出來的計畫；照「第一次上機」逐步驗證，結果回填本文件。
> 本專案的其他內容（流程、規則、腳本）不變；這份只處理「同一套工作流怎麼在 RTX Spark 上跑」。

## 跟桌機版差在哪

| 項目 | 桌機（本專案主設定） | RTX Spark 筆電 |
|---|---|---|
| CPU 架構 | x64 | **ARM64**（Windows 11 on Arm） |
| 記憶體 | 16GB 顯存＋64GB 系統記憶體（各自獨立，共 80GB） | **64GB 統一記憶體，CPU 與 GPU 共用**；可切成固定的系統＋GPU 專用（見〈記憶體切分〉） |
| GPU | RTX 50 系列，正式版 CUDA 驅動 | N1X 內建 Blackwell GPU（5120 或 6144 CUDA 核心） |
| CUDA／PyTorch | 正式版（cu130 wheel） | **開發者預覽版**（CUDA 13.4 preview、NVIDIA nightly PyTorch） |
| 設定檔 | `configs\profile.cmd` | `configs\profile_rtxspark.cmd` |

## 三個主要風險

1. **軟體生態還在預覽階段**：NVIDIA 的 Windows on Arm CUDA 工具包是 Developer Preview，官方說不適合正式使用，已知問題包括某些 PyTorch 工作流程會造成 GPU 逾時或系統重開。PyTorch 要從 NVIDIA 的 nightly 索引裝，不是 PyTorch 官方索引。
2. **部分套件沒有 Windows ARM64 版**（2026-10-14 用 `setup/spark_check.py --wheels` 重掃：PyPI＋pypi.nvidia.com，並檢查 wheel 的 Python 版本是否相符）：

   | 環境 | 可直接裝 | 主要問題 | 對策 |
   |---|---|---|---|
   | `C:\AI\H3`（ComfyUI、H3、Qwen、Music 3） | 97／109 | torch 家族要換來源（NVIDIA nightly 有 torch 2.16 dev、torchaudio、torchvision 的 win_arm64）；`triton-windows` 3.8.0.post28 起有 win_arm64，但預覽版 CUDA 上未驗證，先不裝；`numba`／`llvmlite` 原鎖版本的 ARM64 版只有 Python 3.14，ARM64 清單改用 0.68／0.50；`nvidia-vfx`（RTX VSR）0.2.0.0 起在 pypi.nvidia.com 有 win_arm64 版（PyPI 上只有 sdist 空殼，2026-10-14 更正） | 用 `setup/env/arm64/requirements_h3_venv_arm64.txt`；RTX VSR 驗證前放大先用 `UPSCALE=lanczos` |
   | `C:\AI\Voice`（VoxCPM2、faster-whisper、分軌） | 126／146 | **`ctranslate2`（faster-whisper 核心）任何版本都沒有 Windows ARM64 版**（CUDA 12 函式庫也只有 x64；CUDA 13 版有 ARM64，但 ctranslate2 用不到）；`soxr`、`torchcodec` 沒有 ARM64 wheel（見下方〈語音〉）；`tiktoken`（openai-whisper 需要）與 `praat-parselmouth`（挑音的聲調比對）只有原始碼 | 聽寫：`stt.py` 自動改用 openai-whisper，但要先編得出 tiktoken（要 Rust 工具鏈）；parselmouth 編不起來時挑音照跑，只是沒有腔調分數；VoxCPM2 先試本機 |

3. **記憶體是共用的**：桌機的做法是「顯存放不下的模型先放系統記憶體」，在統一記憶體上這等於同一池子放兩份。上游 16GB 顯存＋32GB 記憶體版實測 H3 一共約用掉 45–50GB 仍可跑，所以 64GB 統一記憶體**理論上夠**，但 Windows 與桌面程式也從同一池子拿，生成時一定要關掉其他大程式。

## 記憶體切分（例：32GB 系統＋32GB GPU 專用）

64GB 機種可以把統一記憶體切出一塊固定給 GPU。切了之後各工具看到的數字都只是其中一半，**不要誤判成只有 32GB**：

| 從哪裡看 | 32＋32 時看到的 | 意思 |
|---|---|---|
| `nvidia-smi` 的 `memory.total` | 約 31GB（31232MiB） | GPU 專用那一塊 |
| Windows 實體記憶體（工作管理員、`GlobalMemoryStatusEx`） | 約 32GB | 只剩系統那一塊 |
| Windows 認可上限（commit limit） | 約 66GB | 系統那一塊＋分頁檔，不含 GPU 專用 |
| torch `cuda.mem_get_info()`／`spark_check.py` 的 `gpu_total_gb` | 46.0GB（閒置時可用 45.8GB） | 比 `nvidia-smi` 多約 15GB，推測含 Windows 共用 GPU 記憶體（從系統那一塊借）；跑 H3 時看實際峰值再確認 |

- `setup/detect_hardware.py` 的總記憶體＝系統＋`nvidia-smi` 回報的專用 VRAM（輸出的 `memory` 欄），H3 夠不夠用總數判斷；`nvidia-smi` 回 `[N/A]`（沒切分、全部共用）時專用 VRAM 記 0，總數就是系統記憶體。
- 切分後 GPU 那一塊是真的專用，比較像桌機的「顯存＋系統記憶體」兩池：H3 放不下顯存的部分要擠進 32GB 系統記憶體，系統那邊比較緊（Windows、瀏覽器也在用）。
- 上面〈設定〉的 ComfyUI 參數（`--reserve-vram 6`、關掉釘選記憶體與非同步搬移）是照「全部共用」設計的，切分後是否仍最合適**還沒實測**：第一次上機跑 H3 時記下峰值，再決定要不要調 `--reserve-vram` 或拿掉 `--disable-pinned-memory`，結果回填這裡。

## 設定（`configs\profile_rtxspark.cmd`）

| 項目 | 值 | 理由 |
|---|---|---|
| ComfyUI | 有 Comfy Desktop 就用它（`COMFY_DIR`、`PY_H3` 指向 Desktop 的 `ComfyUI` 與 `.venv`，模型在 `ComfyUI-Shared\models`），偵測方式與 `profile.cmd` 相同；沒有才用 `C:\AI\H3`，或 `set DESKTOP_COMFY=none` 強制不用 | Desktop 在 RTX Spark 上裝的是 `beta-win-nvidia-arm64` 版，自帶 ARM64 Python 3.13 與 NVIDIA 預覽版 torch，不用自己建 H3 環境 |
| 模型 | 跟 16GB 版完全一樣（H3 剪枝 int8、Heretic int8 文字編碼器、fp16 影片 VAE、DMAD 4 步）；用 Desktop 時文字編碼器同桌機換成 Desktop 範本的 NVFP4（`H3_CLIP`） | 上游驗證過的組合，結果可對照 |
| ComfyUI 參數 | `--reserve-vram 6 --disable-pinned-memory --disable-async-offload` | 統一記憶體不需要釘選記憶體與非同步搬移（只會重複佔用）；保留 6GB 給 Windows |
| 放大 | `UPSCALE=lanczos`，第一次上機 6b 通過後改 `rtxvsr`；FlashVSR 見下方〈放大：FlashVSR〉 | nvidia-vfx 0.2.0.0 有 ARM64 版，但 RTX Spark 上還沒實測 |
| 單鏡長度 | ≤12 秒 | 同主設定 |
| 一次一件 GPU 工作 | 必須 | 同主設定，而且 CPU 程式也在搶同一池記憶體 |

H3 還是記憶體不足時，依序試：`--reserve-vram` 調到 8–10 → 加 `--lowvram` → 換 NVFP4 文字編碼器（N1X 是 Blackwell，原生支援 FP4；上游實測畫面會跟 int8 不同但品質相當）→ `H3_BACKEND=colab`。

## 放大：FlashVSR 要 Triton，筆電先不用

2026-10-14 查 `ComfyUI-FlashVSR_Ultra_Fast`（鎖定 commit `4820b3f`）原始碼：有注意力遮罩的計算只有兩條路，`sparse_sage_attention`（預設，`src/models/sparse_sage/` 直接 `import triton`）與 `block_sparse_attention`（要另外編譯 Block-Sparse-Attention），**沒有純 PyTorch 退路**。其餘依賴（einops、safetensors…）是純 Python。

- `triton-windows` 3.8.0.post28 起有 win_arm64 wheel，但 Triton 執行時要即時編譯 GPU 程式，能不能配 CUDA 13.4 預覽版沒人驗證過；ARM64 清單目前刻意不裝 Triton，所以照預設設定 FlashVSR 在筆電會失敗。
- FlashVSR 只用在全景、舞蹈鏡（較銳但會幻覺細節），頻率低：**在桌機跑**。筆電放大優先 RTX VSR（官方支援 RTX Spark），其次 lanczos。
- 真要在筆電試：等一般 H3 鏡頭穩定後，單獨 `uv pip install --python C:\AI\H3\venv\Scripts\python.exe triton-windows==3.8.0.post28`，用 `<repo>\tools\flashvsr_cli.py` 跑一支短片；失敗就移除 Triton，不影響其他流程。

| 放大方式 | 筆電 | 說明 |
|---|---|---|
| lanczos（ffmpeg） | ✅ 一定能 | 畫質最普通，目前預設 |
| RTX VSR | 🟡 很有機會 | nvidia-vfx 0.2.0.0 有官方 ARM64 版，第一次上機 6b 驗證 |
| FlashVSR | 🟠 不確定 | 要 Triton，且要能在預覽版 CUDA 上編譯 |

## 語音：VoxCPM2（本專案的配音引擎）

2026-10-14 起本專案的配音引擎就是 VoxCPM2，桌機與筆電同一套。**VoxCPM2 是語音元件裡最有機會在筆電本機跑的**（2026-10-11 查資料與掃 PyPI，尚未實機驗證）：

- **官方需求沒有限定平台**：Python 3.10–3.12、PyTorch ≥ 2.5、CUDA ≥ 12；裝置可選 `cpu`／`cuda`／`mps`。社群在 Windows 上有在用，上游作者在 Windows 實測顯存峰值 3.6–6.4GB，佔共用記憶體很少。
- **它一個就包辦兩件事**（`make_film.py` 的 `voices` 呼叫 `tools/voxcpm_batch.py`）：
  - 設計角色參考音（描述寫在 `film.json` 的 `voice_design`）。
  - 用參考音念每句台詞（每句 8 候選，自動挑）。
  - 代價：上游實測台灣腔分數 0.80，且不能標注音；念錯的詞靠讀音替換表 `tts-lexicon.md` 改字。

ARM64 套件狀況：

| 套件 | Windows ARM64 | 影響與對策 |
|---|---|---|
| `voxcpm` 本體 | ✅ 純 Python | — |
| numpy、scipy、numba、llvmlite、sentencepiece | ✅ 有 win_arm64 wheel | — |
| torch／torchaudio | ⚠️ 只能用 NVIDIA 預覽版 | 同 H3 環境 |
| `soxr` 1.1.0（重新取樣，librosa 會 import） | ❌ 只有原始碼，要在 ARM64 上編 C 程式（需 Visual Studio ARM64 建置工具、CMake） | 編不起來 librosa 就無法 import → 送 Colab 或桌機 |
| `torchcodec` | ❌ 沒有 ARM64 wheel（上游語音環境本來也沒裝） | 新版 torchaudio 讀音檔要靠它；官方 issue #119 有人附參考音克隆時報 `Could not load libtorchcodec`。**附參考音克隆這條路要實測**；純聲音設計（`--design`，不讀參考音）較不受影響 |

**Python 版本裝不起來的備案**：VoxCPM 官方推薦 [llama.cpp-omni](https://github.com/tc-mb/llama.cpp-omni)（C++、不需要 Python），載入 VoxCPM2 的 GGUF 權重，支援 CPU／CUDA／Vulkan。NVIDIA 的 Windows on Arm 頁面有列 llama.cpp 支援，但 omni 是分支，Windows ARM64 上能不能編譯沒人驗證過；最差可以純 CPU 跑（慢，但不需要 GPU 驅動）。注意它不經過 `gen_voice.py`，要另外接進流程。

## 建議分工（第一次上機前的預設）

| 工作 | 在哪跑 |
|---|---|
| 劇本、剪接、字幕、自審（CPU） | 筆電 |
| 角色與首幀 | OpenAI Image 2.5（本專案預設，雲端，不受 ARM64 影響）；備選本機 Qwen-Image |
| 配樂（Music 3） | 筆電（ComfyUI 跑得起來的話） |
| H3 影片 | 筆電先試；不行改 `set H3_BACKEND=colab` |
| 角色參考音＋台詞配音 | 筆電本機 VoxCPM2；不行改 Colab 或桌機 |
| 聽寫校對（挑配音、自審） | 筆電本機：faster-whisper 裝不起來時 `stt.py` 自動改用 openai-whisper（較慢，第一次另下載約 3GB 權重）；不行再改 Colab 或桌機 |
| 放大 | 筆電：先用 ffmpeg lanczos；RTX VSR（nvidia-vfx 0.2.0.0 ARM64 版）驗證通過後改用它 |

> 專案放在 Google 雲端硬碟，桌機（RTX 5060 Ti 16GB＋64GB）和筆電看得到同一份檔案：配音這類筆電跑不了的步驟，也可以直接在桌機做。

## 第一次上機（照順序，每步結果回填本文件）

1. **硬體偵測**：`python setup\detect_hardware.py` → 應該顯示 RTX Spark 設定的建議。
2. **原生 ARM64 Python**：裝 python.org 的 Python 3.12 **ARM64** 版（或 `uv python install cpython-3.12-windows-aarch64`）。用 x64 版 Python 會走模擬，CUDA 用不了。確認：`python -c "import platform;print(platform.machine())"` → `ARM64`。
3. **驅動與 CUDA**：照 NVIDIA RTX Spark 開發者頁面裝 Windows on Arm 驅動與 CUDA 13.4 preview。確認：`nvidia-smi` 看得到 GPU。
4. **H3 環境**：
   - **有 Comfy Desktop（優先）**：Desktop 的 `.venv` 已有 ARM64 torch（2026-10-28 實機：Desktop v0.42.1 `beta-win-nvidia-arm64`、Python 3.13.12、torch `2.15.0.dev20260902+cu134`，`cuda.is_available()` 為 True），只補 ARM64 清單裡的幾個套件（不裝 triton，FlashVSR 節點也先不裝）：
     ```
     call <repo>\configs\profile_rtxspark.cmd
     uv pip install --python "%PY_H3%" --no-deps nvidia-vfx==0.2.0.0 gguf==0.19.0 accelerate==1.15.0 numba==0.68.0 llvmlite==0.50.0 "diffusers @ https://github.com/huggingface/diffusers/archive/e0abab83b5df05de9e7abd788643c1a7c1e42e28.zip" --extra-index-url https://pypi.nvidia.com --index-strategy unsafe-best-match
     ```
     Desktop 預設會自動更新 ComfyUI（可能連 torch 一起換），更新後先跑 `smoke_test.py`。下面第 5、6b 步的 `C:\AI\H3\venv\Scripts\python.exe` 改用 `%PY_H3%`。
   - **沒有 Desktop**：自己建 `C:\AI\H3`（torch 安裝檔 1.7GB，pypi.nvidia.com 很慢、uv 預設 30 秒逾時會失敗，先 `set UV_HTTP_TIMEOUT=600`，或改從 NVIDIA pytorch-windows-ci 的 GitHub release 下載，見第 7 步）：
   ```
   py -V:3.12-arm64 -m venv C:\AI\H3\venv
   C:\AI\H3\venv\Scripts\python.exe -m pip install --pre --upgrade --only-binary=:all: --extra-index-url https://pypi.nvidia.com/nvtorch_oot_nightly torch torchvision torchaudio
   uv pip install --python C:\AI\H3\venv\Scripts\python.exe --no-deps -r <repo>\setup\env\arm64\requirements_h3_venv_arm64.txt --index-strategy unsafe-best-match
   ```
   ComfyUI 與自訂節點照 `AGENT_SETUP.md` 2a′（`Nvidia_RTX_Nodes_ComfyUI` 先不要裝）。
5. **相容性總檢查**：`python setup\spark_check.py --torch-python C:\AI\H3\venv\Scripts\python.exe --out spark_report.json` → 看 `torch.cuda` 是否為 `true`、`gpu_total_gb` 報多少。
6. **ComfyUI 啟動**：`call configs\profile_rtxspark.cmd` 後 `<repo>\tools\start_comfy.cmd`。
6b. **RTX VSR 放大**（nvidia-vfx 0.2.0.0 win_arm64；Windows 驅動要 570.65 以上）：
   - 確認裝到了：`C:\AI\H3\venv\Scripts\python.exe -c "import nvvfx;print(nvvfx.__version__)"` → `0.2.0.0`。沒裝到就補：`C:\AI\H3\venv\Scripts\python.exe -m pip install nvidia-vfx==0.2.0.0 --extra-index-url https://pypi.nvidia.com`
   - 實跑：拿任一支 768p 短片 `C:\AI\H3\venv\Scripts\python.exe <repo>\tools\upscale_vsr.py --source in.mp4 --output vsr\out.mp4`，看 `vsr\comparison_*.png` 與 `vsr_result.json` 的秒數
   - 通過就把 `configs\profile_rtxspark.cmd` 的 `UPSCALE=lanczos` 改成 `UPSCALE=rtxvsr`，並更新上面的分工表
7. **語音環境（VoxCPM2）**：
   ```
   py -V:3.12-arm64 -m venv C:\AI\Voice\venv
   C:\AI\Voice\venv\Scripts\python.exe -m pip install --pre --upgrade --only-binary=:all: --extra-index-url https://pypi.nvidia.com/nvtorch_oot_nightly torch torchvision torchaudio
   uv pip install --python C:\AI\Voice\venv\Scripts\python.exe --no-deps -r <repo>\setup\env\arm64\requirements_voice_venv_arm64.txt --index-strategy unsafe-best-match
   ```
   **動手前先參考 media-voice-clone 的經驗**（同一台 RTX Spark 2026-10-28 已裝成 VoxCPM2 GPU 環境，RTF 1.7、載入約 25 秒；細節見該 repo 的 `install.ps1`、`requirements-win-arm64.txt`、`sac-pins.txt`、`shims/sklearn-unavailable/`、`AGENTS.md`〈Windows on ARM＋RTX Spark 的 GPU 環境〉）。重點：
   - **Python 3.13**，torch／torchaudio 用 NVIDIA [pytorch-windows-ci](https://github.com/NVIDIA/pytorch-windows-ci/releases) GitHub release 的固定 nightly（只出 cp313，兩個要同一天那批）；不要用 pypi.nvidia.com（同樣的檔只有約 62 KB/s，本頁第 4 步自建 H3 時 torch 1.7GB 也是在這裡逾時）。上面指令的 3.12 要跟著改。
   - **soxr 沒有任何 win_arm64 wheel**：voice-clone 改用 librosa 0.9.2（最後一版不需要 soxr）＋`setuptools<81`。本專案清單是 librosa 1.0.0（需要 soxr），要降版先確認 `voice_pick.py` 等工具在 0.9.2 下照常。
   - **scikit-learn 的 cp313 win_arm64 每一版都被 SAC 擋**，而 librosa 0.9.2 一 import 就要它：voice-clone 先試真的、被擋才換成 `shims/sklearn-unavailable` 空殼（import 得到，真的用到才丟 `ImportError`）。
   - **SAC 放行的版本**：voice-clone 的語音環境 numba 0.68.0／0.68.1、scipy 1.17／1.18 被擋，改用 numba 0.68.0rc1、scipy 1.16.3；但同一天 Desktop 的 `.venv` 裡 numba 0.68.0（`njit` 實際編譯）與 scipy 1.18.1 都沒被擋，**以實測為準**，被擋才降。
   - **voxcpm `--no-deps`**，它宣告的 pyarrow、tiktoken、cryptography、funasr、modelscope 只有訓練／ASR／降噪才用，而且沒有 win_arm64 wheel。注意本專案的聽寫備援 openai-whisper 需要 tiktoken（只有原始碼、要 Rust），所以 ASR 這條仍要另外驗證。
   - 環境放 `C:\AI\Voice`（不在 `%LOCALAPPDATA%`）：從 Claude 桌面版跑的程式在 `%LOCALAPPDATA%` **新建**的資料夾會被虛擬化到 `Packages\Claude_*\LocalCache\Local\`，別的程式看不到（寫進已存在的資料夾，例如 Desktop 的 `.venv`，不受影響）。

   **可能被 Smart App Control 擋**（見〈Smart App Control〉）：ARM64 原生套件（例如 librosa 會 import 的 scikit-learn、現場編譯出來的 soxr）載入時報 `WinError 4551` 或 DLL 載入失敗，就記下是哪個套件；不要自己關 SAC，先問使用者，或這一步改送 Colab／桌機。
   逐項確認並回填（下面的 `gen_voice.py` 指 `C:\AI\Voice\venv\Scripts\python.exe <repo>\tools\gen_voice.py`）：
   - `soxr` 有沒有編譯成功：`C:\AI\Voice\venv\Scripts\python.exe -c "import soxr, librosa; print('ok')"`
   - VoxCPM2 載入：`C:\AI\Voice\venv\Scripts\python.exe -c "import voxcpm; print('ok')"`
   - 純聲音設計：`gen_voice.py --control "a calm Taiwanese male teacher in his thirties" --design --text "大家好" --out design.wav`
   - 附參考音克隆（torchcodec 風險）：`gen_voice.py --ref design.wav --text "明天要考試" --out clone.wav`；報 `libtorchcodec` 錯誤就記下來，改送 Colab／桌機
   - 失敗時記下卡在哪個套件，再評估 llama.cpp-omni 備案
   - 聽寫備援（openai-whisper）：`C:\AI\Voice\venv\Scripts\python.exe <repo>\tools\stt.py --audio design.wav --outdir stt` → `stt\transcript.json` 的 `backend` 應為 `openai`，記下秒數
8. **smoke test**：`setup\smoke_test.py`；過了再跑 `pipeline\demo_local\run_demo.py`（聽寫應該會印出 `[asr] ... falling back to openai-whisper`，代表備援生效）。
9. 把每一步的結果（成功／失敗、速度、記憶體峰值）寫回本文件，並更新上面的分工表。

## 實機結果

第一台：RTX Spark N1X（6144 核心），64GB 切成 32GB 系統＋32GB GPU 專用，Comfy Desktop 路線。

| 步驟 | 日期 | 結果 |
|---|---|---|
| 1. 硬體偵測 | 2026-10-28 | ✅ 認出 RTX Spark；總記憶體 62.7GB（系統 32.2＋GPU 專用 30.5，見〈記憶體切分〉），C 槽 647GB 可用 |
| 2. ARM64 Python | 2026-10-28 | ✅ 系統有 python.org 3.13 ARM64；Desktop 自帶 3.13.12 ARM64，不必另裝 3.12 |
| 3. 驅動與 CUDA | 2026-10-28 | ✅ 驅動 617.42、CUDA 13.4（出廠已裝） |
| 4. H3 環境 | 2026-10-28 | ✅ Desktop v0.42.1 `beta-win-nvidia-arm64`，torch `2.15.0.dev20260902+cu134`；補裝 nvidia-vfx、gguf、accelerate、numba 0.68、llvmlite 0.50、diffusers 都能 import，未裝 triton。清單裡要現場編譯的 blake3、cryptography、kornia_rs Desktop 已內建。網路慢時大檔（nvidia-vfx 523MB）會斷線，重試加 `UV_HTTP_RETRIES=10` |
| 5. 相容性總檢查 | 2026-10-28 | ✅ `torch.cuda` true、capability 12.1、`gpu_total_gb` 46.0；ffmpeg 9.0.2 是 x64 版（winget `Gyan.FFmpeg`，模擬執行，可用但較慢；BtbN 的 winarm64 版被 Smart App Control 擋，見下方〈Smart App Control〉）；wheel 掃描與 2026-10-14 相同（H3 97／109、語音 126／146） |

## Smart App Control（SAC）會擋 ARM64 執行檔與套件

Windows 11 的 Smart App Control（智慧型應用程式控制）會擋信譽不足、沒有簽章的執行檔與 DLL；社群編譯的 ARM64 版常常中招，錯誤看起來像套件壞掉（`WinError 4551`、啟動器一執行就被擋、`import` 時載入 DLL 失敗）。2026-10-28 在第一台 RTX Spark 實際遇到：

| 東西 | 結果 | 處理 |
|---|---|---|
| ffmpeg（BtbN `ffmpeg-n9.0.2-…-winarm64-gpl-9.0.zip`） | ❌ 被擋 | 改用 winget `Gyan.FFmpeg` 的 x64 full build（9.0.2，模擬執行，可用但較慢） |
| scikit-learn 1.x 的 win_arm64 wheel（其他專案的語音環境） | ❌ 每個版本都被擋 | 見第 7 步 |
| `pdfium.dll`（其他專案） | 第一次被擋，後來沒再被擋 | 推測信譽累積夠了，可以過一陣子再試 |

- Comfy Desktop 的 ARM64 環境與本專案補裝的套件（第 4 步）沒有被擋。
- 遇到 ARM64 東西莫名載入失敗，先懷疑 SAC。**關閉 SAC 是系統安全設定，由使用者自己決定**，agent 不要去改；能退回 x64 版（模擬執行）的就先退。

## 重新產生 ARM64 套件清單

原清單（`setup/env/requirements_*.txt`）改過之後：
```
python setup\spark_check.py --wheels --emit
```
會重寫 `setup/env/arm64/`：torch 家族與 x64 專用套件註解掉、沒有 ARM64 wheel 的套件改釘到 PyPI 上最新的 ARM64 版本，完全沒有的標 `TODO`。**版本跳動可能造成相容問題**，裝完一定要跑 smoke test。

## 參考

- NVIDIA RTX Spark 產品頁：<https://www.nvidia.com/en-us/products/rtx-spark/>
- NVIDIA Windows on Arm 移植指引（驅動、CUDA 13.4、PyTorch 安裝指令）：<https://developer.nvidia.com/topics/ai/local-ai/port-apps>
- CUDA Toolkit for Windows on Arm 預覽版說明：<https://videocardz.com/newz/nvidia-releases-first-cuda-toolkit-preview-for-windows-on-arm-and-rtx-spark>
- VoxCPM 官方 README（需求、裝置選項、llama.cpp-omni）：<https://github.com/OpenBMB/VoxCPM>
- VoxCPM issue #119（附參考音時 `Could not load libtorchcodec`）：<https://github.com/OpenBMB/VoxCPM/issues/119>
- llama.cpp-omni（VoxCPM2 GGUF，C++ 推論）：<https://github.com/tc-mb/llama.cpp-omni>
