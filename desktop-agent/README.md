# OmniAgent Desktop Agent (Phase 1)

Local Windows automation only. This program opens Notepad, types a message,
captures a screenshot with MSS, verifies the result, and prints **Success**
or **Failed**.

Local Notepad automation still works offline. Phase 3 can also connect this
agent to the FastAPI backend over a token-authenticated WebSocket.

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

## The OmniAgent window (easiest)

Double-click **`start_agent.bat`** (the first run sets up Python packages, about a minute), or run
`python app.py`. A small window opens:

1. In the phone app go to **Devices > Add PC > Get pairing code**.
2. Type the code in the window and press **Connect**. The server address is already filled in
   (`https://omniagent-backend-22fj.onrender.com`).
3. The status turns green: *Connected. Your phone can send tasks*. Leave the window open.

The PC is remembered, so next time the window connects by itself. **Disconnect** stops it,
**Forget this PC** clears the saved pairing. The first connection can take up to a minute while the
free server wakes up. `build_exe.bat` can build a single `OmniAgent.exe` (best effort; web browsing is
easier from `start_agent.bat`).

## Connect from the command line

The same thing without the window:

```powershell
pip install -r requirements.txt
python connect.py --code ABCD-EFGH --name "Office PC"   # add --api http://127.0.0.1:8000 for a local backend
```

Get the code in the phone app under **Devices > Add PC**. It works once and
expires after 10 minutes. The first run pairs this PC with your account and
saves a per-device token in `~/.omniagent/agent.json`; later runs reuse it and
need no code. If you remove the PC in the app, or its access expires, the
backend refuses it: run again with `--reset` and a new code.
### How a step runs

For every step the agent acts, looks at the screen, and checks the result:

1. **Act.** If nothing happened (for example the window was not ready), it tries again,
   up to 3 attempts.
2. **Verify.** If the step says what should now be visible (typed text, the app's window
   title, a site name), the agent reads the text on screen and compares it with local
   64-dimensional hashed embeddings and cosine similarity (threshold 0.6). If it does not
   match yet, it looks again after a short wait, up to 3 looks. It never repeats an action
   to "fix" it, because typing twice is worse than not confirming.
3. A step that acted but could not be confirmed is reported as **unverified** and stops the
   plan, which ends as `partial`. After every step the agent sends a small screenshot.

No model or network is used for verification.

Windows 11 Notepad reopens with the last session's unsaved text. The agent never types over
it: it starts a new tab, and refuses to continue if it cannot get a blank page.

If typing fails after some keys may already have gone in, the step is not repeated.

### What this PC can do

On connect the agent tells the backend which actions it can run, and only those are planned
for it: open/type/press keys/click/wait/screenshot always, **scroll** if `pyautogui` is
installed, and **browser navigation** if `playwright` is installed (it drives your installed
Edge or Chrome in a fresh window; nothing is downloaded and downloads are blocked). The
browser also needs "Allow web browsing" switched on for this PC in the app.

### Staying connected and stopping

- If the connection drops, the agent reconnects with growing waits (1s up to 30s). If the
  backend says this PC was removed or is no longer allowed, it stops and asks you to pair again.
- Cancel in the app stops the task after the step it is on. Losing the connection also stops it.
- One task runs at a time.
- **Emergency stop:** move the mouse to the top-left corner of the screen (PyAutoGUI's
  failsafe) or press Ctrl+C in this window.

Tests (plan runner, verification, drivers, protocol, reconnect): run `pytest` in this folder.

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
├── main.py                 Offline Phase 1 entry
├── connect.py              Phase 3 backend connector
├── requirements.txt
├── output/                 Screenshots written here
└── omniagent_pc/
    ├── actions.py          Open Notepad and type
    ├── screenshot.py       MSS screen capture
    ├── verify.py           Confirm text + screenshot
    ├── runner.py           Orchestrate and print status
    └── client.py           Authenticated WebSocket client
```

## Troubleshooting

- **Failed to open Notepad:** another window may have stolen focus, or
  `notepad.exe` may be blocked. Close extra Notepad windows and run again.
- **Typed text was not confirmed:** Windows 11 Notepad is a WinUI app. The
  agent uses the UIA backend first, then win32. Run from a normal desktop
  session, not a remote locked screen.
- **Screenshot failed:** MSS captures the primary monitor. Make sure a
  display is attached and the session is unlocked.
