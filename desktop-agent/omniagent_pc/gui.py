"""OmniAgent for Windows: a small window to pair this PC with your account and keep it connected.

Enter the pairing code shown in the phone app (Devices > Add PC) and press Connect. The PC is
remembered, so next time the window connects by itself. Leave it open (or minimised) while you
want your phone to be able to send tasks to this PC.
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import queue
import socket
import threading
import tkinter as tk
import urllib.error
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from omniagent_pc import apps, client

logger = logging.getLogger(__name__)

COLORS = {"idle": "#6b7280", "working": "#b45309", "ok": "#15803d", "bad": "#b91c1c"}
POLL_MS = 120
MAX_LOG_LINES = 400


def explain(exc: BaseException) -> str:
    """A plain-language reason for a failure, with what to do about it."""
    if isinstance(exc, client.RejectedByBackend):
        return "This PC was removed from your account or is no longer allowed. Get a new pairing code in the app and connect again."
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 429:
            return "Too many attempts. Wait a few minutes and try again."
        if exc.code in (400, 404, 422):
            return "That pairing code is wrong, already used, or expired. Make a new one in the app (Devices > Add PC)."
        return f"The server refused the request ({exc.code})."
    if isinstance(exc, (urllib.error.URLError, OSError, TimeoutError)):
        return "Could not reach the server. Check the web address and your internet connection."
    return f"Something went wrong: {exc}"


class AgentWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.task: asyncio.Task | None = None
        self._executors_summary = ""
        self._reconnect_after_stop = False
        self.config = apps.load_config()

        root.title("OmniAgent")
        root.minsize(540, 720)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._build()
        self._show_abilities()
        self._refresh_lists()
        self._refresh_pairing_hint()
        root.after(POLL_MS, self._drain)
        if client.load_credentials(self.api.get().strip()):
            root.after(400, self.connect)  # already paired: connect without asking

    # ------------------------------------------------------------------ layout
    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="OmniAgent", font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="Let your phone control this PC.", foreground="#4b5563").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )

        self.api = tk.StringVar(value=client.DEFAULT_API)
        self.name = tk.StringVar(value=socket.gethostname())
        self.code = tk.StringVar()

        ttk.Label(frame, text="Server").grid(row=2, column=0, sticky="w", pady=4)
        self.api_entry = ttk.Entry(frame, textvariable=self.api)
        self.api_entry.grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="PC name").grid(row=3, column=0, sticky="w", pady=4)
        self.name_entry = ttk.Entry(frame, textvariable=self.name)
        self.name_entry.grid(row=3, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Pairing code").grid(row=4, column=0, sticky="w", pady=4)
        self.code_entry = ttk.Entry(frame, textvariable=self.code, font=("Consolas", 14))
        self.code_entry.grid(row=4, column=1, sticky="ew", pady=4)
        self.code_entry.bind("<Return>", lambda _e: self.connect())
        self.code.trace_add("write", lambda *_: self._upper_code())

        self.pairing_hint = ttk.Label(frame, text="", foreground="#4b5563", wraplength=460, justify="left")
        self.pairing_hint.grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 8))

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=2, sticky="w", pady=6)
        self.connect_button = ttk.Button(buttons, text="Connect", command=self.connect)
        self.connect_button.pack(side="left")
        self.disconnect_button = ttk.Button(buttons, text="Disconnect", command=self.disconnect, state="disabled")
        self.disconnect_button.pack(side="left", padx=8)
        self.forget_button = ttk.Button(buttons, text="Forget this PC", command=self.forget)
        self.forget_button.pack(side="left")

        self.status = tk.Label(frame, text="Not connected", anchor="w", font=("Segoe UI", 11, "bold"), fg=COLORS["idle"])
        self.status.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8, 2))

        self.abilities = ttk.Label(frame, text="", foreground="#4b5563", wraplength=460, justify="left")
        self.abilities.grid(row=8, column=0, columnspan=2, sticky="w")

        lists = ttk.Frame(frame)
        lists.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        lists.columnconfigure(0, weight=1)
        lists.columnconfigure(1, weight=1)
        self.folder_list = self._list_box(lists, 0, "Folders your phone may use (for Claude Code)", "Add folder…", self.add_folder, self.remove_folder)
        self.program_list = self._list_box(lists, 1, "Extra programs your phone may open", "Add program…", self.add_program, self.remove_program)
        ttk.Label(
            frame,
            text="Notepad, Paint and Calculator are built in. Your phone can only use what is listed here; "
            "it never gets to pick a path of its own. Changes reconnect automatically.",
            foreground="#6b7280",
            wraplength=500,
            justify="left",
        ).grid(row=10, column=0, columnspan=2, sticky="w", pady=(2, 0))

        self.log = scrolledtext.ScrolledText(frame, height=8, state="disabled", font=("Consolas", 9), wrap="word")
        self.log.grid(row=11, column=0, columnspan=2, sticky="nsew", pady=(10, 6))
        frame.rowconfigure(11, weight=1)

        ttk.Label(
            frame,
            text="While a task runs, keep your hands off the mouse and keyboard. To stop at once, move the mouse to the "
            "top-left corner of the screen, or press Disconnect.",
            foreground="#6b7280",
            wraplength=480,
            justify="left",
        ).grid(row=12, column=0, columnspan=2, sticky="w")

    def _list_box(self, parent: ttk.Frame, column: int, title: str, add_text: str, add_cmd, remove_cmd) -> tk.Listbox:
        box = ttk.LabelFrame(parent, text=title, padding=6)
        box.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 6, 6 if column == 0 else 0))
        listbox = tk.Listbox(box, height=4, exportselection=False, font=("Segoe UI", 9))
        listbox.pack(fill="both", expand=True)
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text=add_text, command=add_cmd).pack(side="left")
        ttk.Button(row, text="Remove", command=remove_cmd).pack(side="left", padx=6)
        return listbox

    def _upper_code(self) -> None:
        value = self.code.get()
        if value != value.upper():
            self.code.set(value.upper())

    def _show_abilities(self) -> None:
        try:
            from omniagent_pc.executors import build_executors

            actions = sorted(build_executors())
        except Exception as exc:  # noqa: BLE001 - missing Windows libraries
            self.abilities.config(text=f"This PC cannot run tasks yet: {exc}")
            return
        missing = []
        if "scroll" not in actions:
            missing.append("scrolling (pip install pyautogui)")
        if "browser_navigate" not in actions:
            missing.append("web browsing (pip install playwright)")
        text = "This PC can: " + ", ".join(a.replace("_", " ") for a in actions) + "."
        try:
            labels = [spec.label for spec in apps.app_specs(self.config).values()]
            text += " Apps: " + (", ".join(labels) or "none") + "."
            if "claude_code" not in apps.app_specs(self.config):
                text += " (Claude Code was not found: install it so the 'claude' command works.)"
        except Exception:  # noqa: BLE001
            pass
        if missing:
            text += " Not available: " + "; ".join(missing) + "."
        self.abilities.config(text=text)

    def _refresh_pairing_hint(self) -> None:
        saved = client.load_credentials(self.api.get().strip())
        if saved:
            self.pairing_hint.config(text="This PC is already paired with your account. Press Connect (no code needed).")
        else:
            self.pairing_hint.config(text="In the app open Devices > Add PC > Get pairing code, then type the code here.")

    # ------------------------------------------------------------------ state
    def _set_status(self, text: str, tone: str) -> None:
        self.status.config(text=text, fg=COLORS[tone])

    def _write(self, line: str) -> None:
        self.log.config(state="normal")
        self.log.insert("end", f"{datetime.now():%H:%M:%S}  {line}\n")
        count = int(self.log.index("end-1c").split(".")[0])
        if count > MAX_LOG_LINES:
            self.log.delete("1.0", f"{count - MAX_LOG_LINES}.0")
        self.log.see("end")
        self.log.config(state="disabled")

    def _busy(self, running: bool) -> None:
        self.connect_button.config(state="disabled" if running else "normal")
        self.disconnect_button.config(state="normal" if running else "disabled")
        self.forget_button.config(state="disabled" if running else "normal")
        for entry in (self.api_entry, self.name_entry, self.code_entry):
            entry.config(state="disabled" if running else "normal")

    def _drain(self) -> None:
        """Runs on the window's thread: shows what the worker thread reported."""
        try:
            while True:
                kind, text = self.events.get_nowait()
                if kind == "connecting":
                    self._set_status("Connecting…", "working")
                    self._write(text + " (the first time can take up to a minute while the server wakes up)")
                elif kind == "connected":
                    self._set_status("Connected. Your phone can send tasks", "ok")
                    self._write(text)
                    self._refresh_pairing_hint()
                elif kind == "disconnected":
                    self._set_status("Reconnecting…", "working")
                    self._write(text)
                elif kind == "task_started":
                    self._set_status("Running a task…", "working")
                    self._write(text)
                elif kind == "step":
                    self._write("  " + text)
                elif kind == "task_finished":
                    self._set_status("Connected. Your phone can send tasks", "ok")
                    self._write("Task " + text)
                elif kind == "failed":
                    self._set_status("Not connected", "bad")
                    self._write(text)
                    messagebox.showerror("OmniAgent", text, parent=self.root)
                elif kind == "stopped":
                    self._busy(False)
                    self.thread = self.loop = self.task = None
                    if self.status.cget("fg") != COLORS["bad"]:
                        self._set_status("Not connected", "idle")
                    self._refresh_pairing_hint()
                    if self._reconnect_after_stop:
                        self._reconnect_after_stop = False
                        self.root.after(300, self.connect)
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._drain)

    # ------------------------------------------------------------------ actions
    def connect(self) -> None:
        if self.thread is not None:
            return
        api = self.api.get().strip().rstrip("/")
        name = self.name.get().strip() or socket.gethostname()
        code = self.code.get().strip()
        if not api.startswith(("http://", "https://")):
            messagebox.showwarning("OmniAgent", "The server address must start with https://", parent=self.root)
            return
        if not client.load_credentials(api) and not code:
            messagebox.showinfo(
                "OmniAgent",
                "Type the pairing code from the app first (Devices > Add PC > Get pairing code).",
                parent=self.root,
            )
            self.code_entry.focus_set()
            return

        self._busy(True)
        self._set_status("Connecting…", "working")
        self.thread = threading.Thread(target=self._work, args=(api, name, code), daemon=True)
        self.thread.start()

    def _work(self, api: str, name: str, code: str) -> None:
        """The worker thread: owns an asyncio loop and runs the agent until it is stopped."""
        loop = asyncio.new_event_loop()
        self.loop = loop
        try:
            self.task = loop.create_task(
                client.run_client(api, name, socket.gethostname(), code, on_event=lambda k, t: self.events.put((k, t)))
            )
            loop.run_until_complete(self.task)
        except asyncio.CancelledError:
            self.events.put(("step", "Disconnected."))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Agent stopped")
            self.events.put(("failed", explain(exc)))
        finally:
            loop.close()
            self.events.put(("stopped", ""))

    # -- folders and programs the owner allows (kept on this PC, reported to the backend by name)
    def _refresh_lists(self) -> None:
        self.folder_list.delete(0, "end")
        for name, path in self.config["folders"].items():
            self.folder_list.insert("end", f"{name}  -  {path}")
        self.program_list.delete(0, "end")
        for program in self.config["programs"].values():
            self.program_list.insert("end", f"{program['label']}  -  {program['path']}")

    def _lists_changed(self, message: str) -> None:
        apps.save_config(self.config)
        self._refresh_lists()
        self._show_abilities()
        self._write(message)
        if self.thread is not None:  # tell the backend about the new list by reconnecting
            self._reconnect_after_stop = True
            self.disconnect()

    def add_folder(self) -> None:
        path = filedialog.askdirectory(parent=self.root, title="Choose a folder your phone may open Claude Code in")
        if not path:
            return
        try:
            name = apps.add_folder(self.config, str(Path(path)))
        except ValueError as exc:
            messagebox.showwarning("OmniAgent", str(exc), parent=self.root)
            return
        self._lists_changed(f"Folder '{name}' added. Say its name to your phone (for example: open Claude Code in {name}).")

    def remove_folder(self) -> None:
        selected = self.folder_list.curselection()
        if not selected:
            return
        name = list(self.config["folders"])[selected[0]]
        del self.config["folders"][name]
        self._lists_changed(f"Folder '{name}' removed.")

    def add_program(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root, title="Choose a program your phone may open", filetypes=[("Programs", "*.exe")]
        )
        if not path:
            return
        try:
            app_id = apps.add_program(self.config, str(Path(path)))
        except ValueError as exc:
            messagebox.showwarning("OmniAgent", str(exc), parent=self.root)
            return
        self._lists_changed(f"Program '{self.config['programs'][app_id]['label']}' added.")

    def remove_program(self) -> None:
        selected = self.program_list.curselection()
        if not selected:
            return
        app_id = list(self.config["programs"])[selected[0]]
        label = self.config["programs"].pop(app_id)["label"]
        self._lists_changed(f"Program '{label}' removed.")

    def disconnect(self) -> None:
        loop, task = self.loop, self.task
        if loop is not None and task is not None:
            self._write("Disconnecting…")
            loop.call_soon_threadsafe(task.cancel)

    def forget(self) -> None:
        api = self.api.get().strip().rstrip("/")
        if not client.load_credentials(api):
            messagebox.showinfo("OmniAgent", "This PC is not paired yet.", parent=self.root)
            return
        if messagebox.askyesno(
            "OmniAgent",
            "Forget this PC on this computer?\n\nTo use it again you need a new pairing code. "
            "To also remove it from your account, use Devices > Remove in the app.",
            parent=self.root,
        ):
            client.CREDENTIALS_FILE.unlink(missing_ok=True)
            self._write("Forgot this PC. Enter a new pairing code to connect again.")
            self._set_status("Not connected", "idle")
            self._refresh_pairing_hint()

    def close(self) -> None:
        self.disconnect()
        thread = self.thread
        if thread is not None:
            thread.join(timeout=3)
        self.root.destroy()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:  # sharp text and correct coordinates on scaled displays
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass
    root = tk.Tk()
    AgentWindow(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
