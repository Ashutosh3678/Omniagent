# OmniAgent Desktop Agent (Phase 1)

Local Windows automation only. This program opens Notepad, types a message,
captures a screenshot with MSS, verifies the result, and prints **Success**
or **Failed**.

It does not include AI, a mobile app, a backend, a database, or remote
connectivity.

## Requirements

- Windows 10 or Windows 11
- Python 3.11 or newer

## Install

From this folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks the venv script, run this once for the current user,
then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Run

Leave this window in the foreground and do not use the mouse or keyboard
while the agent runs.

```powershell
python main.py
```

Or:

```powershell
python -m omniagent_pc
```

Type a custom message:

```powershell
python main.py Hello from OmniAgent
```

A successful run:

1. Opens a new Notepad window.
2. Types `Hello from OmniAgent` (or your custom text).
3. Saves a PNG under `output/`.
4. Checks that Notepad still shows the text and that the screenshot is a valid PNG.
5. Prints `Task status: Success` or `Task status: Failed`.

The process exits `0` on success and `1` on failure. Notepad is left open so
you can confirm the typed text yourself.

## Project layout

```text
desktop-agent/
├── main.py                 Entry point
├── requirements.txt
├── output/                 Screenshots written here
└── omniagent_pc/
    ├── actions.py          Open Notepad and type
    ├── screenshot.py       MSS screen capture
    ├── verify.py           Confirm text + screenshot
    └── runner.py           Orchestrate and print status
```

## Troubleshooting

- **Failed to open Notepad:** another window may have stolen focus, or
  `notepad.exe` may be blocked. Close extra Notepad windows and run again.
- **Typed text was not confirmed:** Windows 11 Notepad is a WinUI app. The
  agent uses the UIA backend first, then win32. Run from a normal desktop
  session, not a remote locked screen.
- **Screenshot failed:** MSS captures the primary monitor. Make sure a
  display is attached and the session is unlocked.
