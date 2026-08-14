@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto run

echo Eerste installatie van de Brandveiligheidsinspectie-app...
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv
    goto install
)

where python >nul 2>nul
if %errorlevel%==0 (
    python -m venv .venv
    goto install
)

echo.
echo Python 3 is niet gevonden.
echo Installeer Python 3.11 of nieuwer via https://www.python.org/downloads/windows/
echo Kies tijdens de installatie ook "Add Python to PATH".
pause
exit /b 1

:install
if not exist ".venv\Scripts\python.exe" (
    echo Het aanmaken van de Python-omgeving is mislukt.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Installatie van de app-onderdelen is mislukt.
    pause
    exit /b 1
)

:run
echo.
echo Brandveiligheidsinspectie wordt gestart op poort 8502.
echo Sluit dit venster niet zolang de app beschikbaar moet blijven.
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 0.0.0.0 --server.port 8502
pause

