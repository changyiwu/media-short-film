# 確保本機 ComfyUI 在 127.0.0.1:8188 執行中；沒有的話在背景啟動它。
# 音樂（Music 3）、圖（Qwen）與影片（H3）都共用這個服務。
# ComfyUI 的位置與 Python 由 configs\profile.cmd 的 COMFY_DIR、PY_H3 決定：
#   Comfy Desktop：啟動 Desktop 安裝裡的 ComfyUI（不開 Desktop 視窗），模型、input、output 照 Desktop 的設定
#                  （做法同全域技能 comfyui；Desktop 視窗開著時它已佔用 8188，本腳本就不再啟動）
#   自己安裝：C:\AI\H3\ComfyUI-0.36.0＋C:\AI\H3\venv（預設）
$ErrorActionPreference = 'Stop'
try {
  $st = Invoke-RestMethod -Uri 'http://127.0.0.1:8188/system_stats' -TimeoutSec 4
  Write-Output 'ComfyUI already running.'
  if ($env:COMFY_LISTEN -and (($st.system.argv -join ' ') -notmatch [regex]::Escape("--listen $env:COMFY_LISTEN"))) {
    Write-Output "Warning: COMFY_LISTEN=$env:COMFY_LISTEN but the running ComfyUI was not started with it (other PCs cannot reach it). Close it (or the Desktop window) and rerun this script." }
  if ($env:COMFY_EXTRA_ARGS) { Write-Output "Note: if it was started from the Comfy Desktop window, COMFY_EXTRA_ARGS ($env:COMFY_EXTRA_ARGS) is NOT applied. Close Desktop and rerun this script to start it with the profile's arguments." }
  exit 0
} catch { }
$py  = if ($env:PY_H3)     { $env:PY_H3 }     else { 'C:\AI\H3\venv\Scripts\python.exe' }
$dir = if ($env:COMFY_DIR) { $env:COMFY_DIR } else { 'C:\AI\H3\ComfyUI-0.36.0' }
$listen = if ($env:COMFY_LISTEN) { $env:COMFY_LISTEN } else { '127.0.0.1' }   # 當區網工作機（cloud\hybrid_h3.py 的 H3_REMOTES）時設 0.0.0.0
if ($listen -ne '127.0.0.1') { Write-Output "Listening on ${listen}:8188 (LAN worker mode)." }
$args_ = @('-X','utf8','main.py','--listen',$listen,'--port','8188','--disable-auto-launch','--preview-method','none','--cache-none','--fast','fp16_accumulation')
if (Test-Path (Join-Path $dir '.comfy_environment')) {
  # Comfy Desktop：讀 %APPDATA%\Comfy Desktop 的設定，取模型路徑設定檔與 input／output；刻意不帶 Desktop 的 launchArgs（--enable-manager）
  $cfg  = Join-Path $env:APPDATA 'Comfy Desktop'
  $set  = Get-Content (Join-Path $cfg 'settings.json') -Raw -Encoding UTF8 | ConvertFrom-Json
  $inst = (Get-Content (Join-Path $cfg 'installations.json') -Raw -Encoding UTF8 | ConvertFrom-Json) |
          Where-Object { $_.sourceId -ne 'cloud' -and ((Join-Path $_.installPath 'ComfyUI') -eq $dir.TrimEnd('\')) } | Select-Object -First 1
  if (-not $inst) { Write-Error "COMFY_DIR=$dir is not listed in $cfg\installations.json. Check COMFY_DIR / PY_H3 in configs\profile.cmd." }
  $yaml = Join-Path $cfg "instance-model-paths\$($inst.id).yaml"
  $args_ += @('--extra-model-paths-config', $yaml, '--input-directory', $set.inputDir, '--output-directory', $set.outputDir)
  Write-Output "Starting Comfy Desktop's ComfyUI in the background: $dir"
}
$extra = @(); if ($env:COMFY_EXTRA_ARGS) { $extra = $env:COMFY_EXTRA_ARGS -split ' ' }   # 例如 --reserve-vram 1.5，由 configs\profile.cmd 設定
$quoted = ($args_ + $extra) | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }   # 含空白的路徑要加引號（Comfy Desktop 在 %APPDATA%\Comfy Desktop）
$p = Start-Process -FilePath $py -ArgumentList $quoted -WorkingDirectory $dir -WindowStyle Hidden -PassThru
for ($i = 0; $i -lt 90; $i++) {
  Start-Sleep -Seconds 2
  try { Invoke-RestMethod -Uri 'http://127.0.0.1:8188/system_stats' -TimeoutSec 4 | Out-Null; Write-Output "ComfyUI started after $(($i+1)*2)s (PID $($p.Id); stop: Stop-Process -Id $($p.Id))."; exit 0 } catch { }
  if ($p.HasExited) { Write-Error "ComfyUI exited (code $($p.ExitCode)). Run it by hand to see the error: cd `"$dir`"; & `"$py`" main.py" }
}
Write-Error 'ComfyUI did not come up within 180s.'
