@echo off
rem 16GB VRAM + 64GB RAM. Same models as the 32GB-VRAM version (verified bit-identical, see docs\hardware.md)
rem Only difference: start ComfyUI with --reserve-vram 1.5, and run one GPU job at a time.
rem If VAE decode crashes, add: --disable-pinned-memory --disable-async-offload
set PYTHONDONTWRITEBYTECODE=1
set COMFY_HOST=http://127.0.0.1:8188
set COMFY_DIR=C:\AI\H3\ComfyUI-0.36.0
set H3_UNET=minimax_h3_ref2va_pruned_int8_convrot.safetensors
set H3_CLIP=qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors
set H3_VIDEO_VAE=minimax_h3_video_vae_fp16.safetensors
set COMFY_EXTRA_ARGS=--reserve-vram 1.5
rem Comfy Desktop (default install name "ComfyUI"): use its ComfyUI, .venv and shared models instead of C:\AI\H3.
rem The model files are the ones Desktop templates download (NVFP4 H3 text encoder unless the INT8 one is downloaded, int8 Qwen edit, fp16 Music 3 DiT).
rem Renamed the Desktop install? Change DESKTOP_COMFY below. To use your own C:\AI\H3 install instead: set DESKTOP_COMFY=none
if not defined DESKTOP_COMFY set DESKTOP_COMFY=%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI
if exist "%DESKTOP_COMFY%\.venv\Scripts\python.exe" (
  set "COMFY_DIR=%DESKTOP_COMFY%"
  set "PY_H3=%DESKTOP_COMFY%\.venv\Scripts\python.exe"
  set "COMFY_MODELS_DIR=%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Shared\models"
  rem Text encoder: keep the Heretic INT8 one (docs\hardware.md: NVFP4 changes results and is unstable) if it is in the shared
  rem models; Desktop ships only NVFP4, so fall back to it until setup\downloads_uncensored.json has been downloaded
  if not exist "%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Shared\models\text_encoders\qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors" set H3_CLIP=qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
  rem Desktop template files win only if they exist; otherwise keep the files downloaded with setup\downloads_*.json
  if exist "%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Shared\models\diffusion_models\qwen_image_edit_2511_int8_convrot.safetensors" set QWEN_EDIT_UNET=qwen_image_edit_2511_int8_convrot.safetensors
  if exist "%LOCALAPPDATA%\Comfy-Desktop\ComfyUI-Shared\models\diffusion_models\minimax_music3_dit_fp16.safetensors" set MUSIC3_DIT=minimax_music3_dit_fp16.safetensors
  echo [profile] Comfy Desktop: %DESKTOP_COMFY%
)
if not defined PY_H3 set PY_H3=C:\AI\H3\venv\Scripts\python.exe
rem Voice environments live outside the repo. Installed somewhere else? set AI_ROOT (install root) or PY_VOICE before calling this.
if not defined AI_ROOT set "AI_ROOT=C:\AI"
if not defined PY_VOICE set "PY_VOICE=%AI_ROOT%\Voice\venv\Scripts\python.exe"
echo [profile] 16GB VRAM + 64GB RAM: H3 text encoder %H3_CLIP%, start ComfyUI with %COMFY_EXTRA_ARGS%
