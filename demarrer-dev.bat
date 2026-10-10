@echo off
REM Lance l'environnement de developpement Sentinel-X (broker de test + API + faux boitier)
REM Double-clique sur ce fichier, puis ouvre http://localhost:3000
cd /d "%~dp0api"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js n'est pas installe. Installe la version LTS depuis https://nodejs.org puis relance.
  pause
  exit /b 1
)

if not exist node_modules (
  echo Installation des dependances, patiente...
  call npm install
)

REM Premier lancement : cree api\.env avec une cle API aleatoire (jamais commitee)
if not exist .env (
  node -e "const fs=require('fs');const k=require('crypto').randomBytes(24).toString('hex');fs.writeFileSync('.env',fs.readFileSync('.env.example','utf8').replace(/^API_KEY=.*$/m,'API_KEY='+k))"
  echo Fichier api\.env cree avec une cle API aleatoire.
)

start "Broker MQTT de test" cmd /k npm run broker
timeout /t 2 /nobreak >nul
start "API Sentinel-X" cmd /k npm run dev
timeout /t 3 /nobreak >nul
start "Simulateur boitier" cmd /k npm run simulate
timeout /t 2 /nobreak >nul
start http://localhost:3000
