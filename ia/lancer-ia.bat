@echo off
REM Lance les deux scripts IA de Sentinel-X (vision + anomalies) dans deux fenetres.
REM Premier lancement : cree l'environnement Python et installe les bibliotheques (Internet necessaire une fois).
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python n'est pas installe. Installe Python 3.11 depuis https://www.python.org en cochant "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist .venv (
  echo Creation de l'environnement Python...
  py -3 -m venv .venv
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)

if not exist .env (
  copy .env.example .env >nul
  echo Fichier ia\.env cree : remplis API_URL et API_KEY, puis relance.
  notepad .env
  exit /b 0
)

start "Sentinel-X IA - vision" cmd /k .venv\Scripts\python.exe vision.py
start "Sentinel-X IA - anomalies" cmd /k .venv\Scripts\python.exe anomalies.py
timeout /t 5 /nobreak >nul
start http://localhost:5000/video
