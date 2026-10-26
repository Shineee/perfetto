@echo off
rem Record a 10s Android trace with record_android_trace and open it in ui.perfetto.dev
cd /d "%~dp0"
python record_android_trace -o trace_file.perfetto-trace -t 20s -b 32mb -a * sched freq view ss input
echo.
pause
