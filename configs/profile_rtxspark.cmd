@echo off
rem RTX Spark laptop (Windows on Arm, 64GB unified memory shared by CPU and GPU). NOT TESTED YET - see docs\hardware_rtxspark.md
rem Same models as the 16GB VRAM versions. Unified memory: pinned host memory and async offload only duplicate data in the same pool, so turn them off.
rem --reserve-vram 6 leaves room for Windows and the desktop in the shared pool. If H3 runs out of memory, raise it or add --lowvram.
set PYTHONDONTWRITEBYTECODE=1
set COMFY_HOST=http://127.0.0.1:8188
set COMFY_DIR=C:\AI\H3\ComfyUI-0.36.0
set H3_UNET=minimax_h3_ref2va_pruned_int8_convrot.safetensors
set H3_CLIP=qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors
set H3_VIDEO_VAE=minimax_h3_video_vae_fp16.safetensors
set COMFY_EXTRA_ARGS=--reserve-vram 6 --disable-pinned-memory --disable-async-offload
rem Comfy Desktop (default install name "ComfyUI"; on RTX Spark it installs the beta-win-nvidia-arm64 bundle with ARM64 CUDA torch):
rem use its ComfyUI, .venv and shared models instead of C:\AI\H3, same as configs\profile.cmd.
rem Renamed the Desktop install? Change DESKTOP_COMFY below. To use your own C:\AI\H3 install instead: set DESKTOP_COMFY=none
if not defined DESKTOP_COMFY set DESKTOP_COMFY=%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI
if exist "%DESKTOP_COMFY%\.venv\Scripts\python.exe" (
  set "COMFY_DIR=%DESKTOP_COMFY%"
  set "PY_H3=%DESKTOP_COMFY%\.venv\Scripts\python.exe"
  set "COMFY_MODELS_DIR=%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Shared\models"
  set H3_CLIP=qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
  rem Desktop template files win only if they exist; otherwise keep the files downloaded with setup\downloads_*.json
  if exist "%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Shared\models\diffusion_models\qwen_image_edit_2511_int8_convrot.safetensors" set QWEN_EDIT_UNET=qwen_image_edit_2511_int8_convrot.safetensors
  if exist "%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Shared\models\diffusion_models\minimax_music3_dit_fp16.safetensors" set MUSIC3_DIT=minimax_music3_dit_fp16.safetensors
  echo [profile] Comfy Desktop: %DESKTOP_COMFY%
)
if not defined PY_H3 set PY_H3=C:\AI\H3\venv\Scripts\python.exe
rem nvidia-vfx 0.2.0.0 has a win_arm64 wheel (pypi.nvidia.com), but RTX VSR on RTX Spark is untested: keep lanczos until
rem docs\hardware_rtxspark.md first-run step 6b passes, then change this to UPSCALE=rtxvsr (or set UPSCALE=flashvsr)
set UPSCALE=lanczos
rem Voice environments live outside the repo. Installed somewhere else? set AI_ROOT (install root) or PY_VOICE before calling this.
if not defined AI_ROOT set "AI_ROOT=C:\AI"
if not defined PY_VOICE set "PY_VOICE=%AI_ROOT%\Voice\venv\Scripts\python.exe"
echo [profile] RTX Spark (Windows on Arm, unified memory, UNTESTED): ComfyUI %COMFY_EXTRA_ARGS%, UPSCALE=%UPSCALE%. Close other big apps.
