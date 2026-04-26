@echo off
cd /d "%~dp0"
title Job Scraper Bot Telegram
echo ============================================================
echo  Job Scraper - Bot Telegram (alertes automatiques)
echo ============================================================
echo.
echo Modes disponibles:
echo   1. test       Envoie un message de test sur Telegram
echo   2. list       Liste les alertes du fichier alerts.json
echo   3. once       Lance un scan unique maintenant
echo   4. daemon     Boucle infinie (scan toutes les 4h)
echo.
set /p mode="Choix [1-4] : "

if "%mode%"=="1" python -m bot.main test
if "%mode%"=="2" python -m bot.main list
if "%mode%"=="3" python -m bot.main once
if "%mode%"=="4" python -m bot.main daemon

echo.
pause
