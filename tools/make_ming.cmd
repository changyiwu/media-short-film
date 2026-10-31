@echo off
REM Ming-3.0-TTS one-shot (default voice engine): generate candidates then auto-pick, both in the Voice venv. Usage: make_ming.cmd jobs.json
REM See ming_batch.py / voice_pick.py headers. Keep this file ASCII-only (cmd reads it in the console codepage).
setlocal
set PYTHONUTF8=1
if not defined AI_ROOT set "AI_ROOT=C:\AI"
if not defined PY_VOICE set "PY_VOICE=%AI_ROOT%\Voice\venv\Scripts\python.exe"
"%PY_VOICE%" "%~dp0ming_batch.py" %1 < NUL || exit /b 1
"%PY_VOICE%" "%~dp0voice_pick.py" %1
endlocal
