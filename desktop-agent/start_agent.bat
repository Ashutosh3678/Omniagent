@echo off
rem Starts the OmniAgent window. The first run creates a private Python environment and installs what it needs.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Setting up OmniAgent for the first time. This takes a minute...
    python -m venv .venv || goto :nopython
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :failed
)
start "" ".venv\Scripts\pythonw.exe" app.py
exit /b 0

:nopython
echo Python 3.11 or newer is needed. Install it from https://www.python.org/downloads/ and run this again.
pause
exit /b 1

:failed
echo Installing the requirements failed. See the messages above.
pause
exit /b 1
