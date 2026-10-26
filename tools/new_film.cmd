@echo off
REM New film: copy pipeline\template_local to output\<type>\<name>. Usage: new_film.cmd <type> <name>
REM See new_film.py header. Keep this file ASCII-only (cmd reads it in the console codepage).
setlocal
set PYTHONUTF8=1
python "%~dp0new_film.py" %*
endlocal
