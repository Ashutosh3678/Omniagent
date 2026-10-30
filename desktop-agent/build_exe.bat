@echo off
rem Optional: builds a single OmniAgent.exe (dist\OmniAgent.exe) that needs no Python on the target PC.
rem Web browsing needs Playwright and is easier to use from start_agent.bat than from the .exe.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv || exit /b 1
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || exit /b 1
)
".venv\Scripts\python.exe" -m pip install pyinstaller || exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconsole --onefile --name OmniAgent ^
    --collect-all pywinauto --collect-all comtypes --hidden-import win32clipboard --hidden-import win32con ^
    app.py || exit /b 1
echo.
echo Built dist\OmniAgent.exe
