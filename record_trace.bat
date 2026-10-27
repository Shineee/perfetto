@echo off
rem Record a 20s Android trace (with Frame Timeline) and open it in ui.perfetto.dev
cd /d "%~dp0"
python record_android_trace -c record_trace.config -o trace_file.perfetto-trace
echo.
pause
