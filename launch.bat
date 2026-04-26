@echo off
cd /d "%~dp0"
echo ==========================================
echo   Job Scraper - http://127.0.0.1:5000
echo   (Ctrl+C pour arreter)
echo ==========================================
start "" http://127.0.0.1:5000
python app.py
pause
