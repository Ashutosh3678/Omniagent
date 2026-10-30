"""What this PC lets OmniAgent open, decided by the PC's owner.

The list lives in a small file on this PC (`apps.json` next to the pairing file), not in the cloud:

* **Programs** the owner added in the OmniAgent window (a path to an .exe), on top of the built-in
  ones (Notepad, Paint, Calculator, the browser, Claude Code).
* **Folders** the owner picked (for Claude Code to work in).

The agent tells the backend which apps and folder *names* exist. The phone, the planner and the
backend can only choose from those names; a path is never accepted from outside, so nothing can point
the agent at a program or folder the owner did not add here.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ID_CLEAN = re.compile(r"[^a-z0-9]+")
_NAME_CLEAN = re.compile(r"[^A-Za-z0-9 _.\-]+")
MAX_PROGRAMS = 30
MAX_FOLDERS = 50


@dataclass(frozen=True)
class AppSpec:
    id: str
    label: str
    kind: str  # notepad | browser | claude_code | window
    exe: str | None = None  # what to start, for kind "window"
    title_hint: str | None = None  # part of the window's title, to find it once it opens
    needs_workspace: bool = False

    def describe(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "needs_workspace": self.needs_workspace}


BUILTIN: dict[str, AppSpec] = {
    "notepad": AppSpec("notepad", "Notepad", "notepad"),
    "paint": AppSpec("paint", "Paint", "window", exe="mspaint.exe", title_hint="Paint"),
    "calculator": AppSpec("calculator", "Calculator", "window", exe="calc.exe", title_hint="Calculator"),
    "browser": AppSpec("browser", "Web browser", "browser"),
    "claude_code": AppSpec("claude_code", "Claude Code", "claude_code", needs_workspace=True),
}


# --------------------------------------------------------------------------- the owner's file
def config_path() -> Path:
    return Path(os.environ.get("OMNIAGENT_HOME", Path.home() / ".omniagent")) / "apps.json"


def load_config(path: Path | None = None) -> dict[str, Any]:
    """{"programs": {id: {"label", "path"}}, "folders": {name: path}}. A missing or damaged file is empty."""
    try:
        data = json.loads((path or config_path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    programs = data.get("programs") if isinstance(data, dict) else None
    folders = data.get("folders") if isinstance(data, dict) else None
    return {
        "programs": {
            k: v
            for k, v in (programs if isinstance(programs, dict) else {}).items()
            if isinstance(v, dict) and isinstance(v.get("path"), str) and isinstance(v.get("label"), str)
        },
        "folders": {k: v for k, v in (folders if isinstance(folders, dict) else {}).items() if isinstance(v, str)},
    }


def save_config(config: dict[str, Any], path: Path | None = None) -> None:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config, indent=2), encoding="utf-8")


def slug_id(text: str) -> str:
    cleaned = _ID_CLEAN.sub("_", text.lower()).strip("_")[:28] or "program"
    return cleaned if not cleaned[0].isdigit() else f"app_{cleaned}"


def clean_name(text: str) -> str:
    return _NAME_CLEAN.sub("_", text).strip(" ._-")[:80] or "folder"


def _unique(base: str, taken: set[str], sep: str = "-", limit: int = 80) -> str:
    """`base`, or `base-2`, `base-3`... (folders) / `base_2`... (program ids, which may not contain a hyphen)."""
    if base not in taken:
        return base
    number = 2
    while True:
        suffix = f"{sep}{number}"
        candidate = base[: limit - len(suffix)] + suffix
        if candidate not in taken:
            return candidate
        number += 1


def add_program(config: dict[str, Any], exe_path: str, label: str | None = None) -> str:
    """Remembers a program. Only existing .exe files are accepted. Returns its id."""
    path = Path(exe_path)
    if not path.is_absolute() or path.suffix.lower() != ".exe" or not path.is_file():
        raise ValueError("Choose an existing program file (.exe)")
    if len(config["programs"]) >= MAX_PROGRAMS:
        raise ValueError(f"At most {MAX_PROGRAMS} programs can be added")
    name = (label or path.stem).strip()[:40] or path.stem
    taken = set(config["programs"]) | set(BUILTIN)
    app_id = _unique(slug_id(name), taken, sep="_", limit=32)
    config["programs"][app_id] = {"label": name, "path": str(path)}
    return app_id


def add_folder(config: dict[str, Any], folder: str, name: str | None = None) -> str:
    """Remembers a folder under a short name the phone can use. Returns that name."""
    path = Path(folder)
    if not path.is_absolute() or not path.is_dir():
        raise ValueError("Choose an existing folder")
    if len(config["folders"]) >= MAX_FOLDERS:
        raise ValueError(f"At most {MAX_FOLDERS} folders can be added")
    for existing_name, existing_path in config["folders"].items():
        if Path(existing_path) == path:
            return existing_name
    chosen = _unique(clean_name(name or path.name or str(path)), set(config["folders"]))
    config["folders"][chosen] = str(path)
    return chosen


# --------------------------------------------------------------------------- what is available now
def _on_path(program: str) -> bool:
    return shutil.which(program) is not None


def _builtin_available(spec: AppSpec) -> bool:
    if spec.kind == "notepad":
        return True
    if spec.kind == "browser":
        return importlib.util.find_spec("playwright") is not None
    if spec.kind == "claude_code":
        return _on_path("claude")
    return spec.exe is not None and _on_path(spec.exe)


def app_specs(config: dict[str, Any]) -> dict[str, AppSpec]:
    """Every app this PC can open right now, by id."""
    specs = {app_id: spec for app_id, spec in BUILTIN.items() if _builtin_available(spec)}
    for app_id, program in config["programs"].items():
        if app_id not in BUILTIN and Path(program["path"]).is_file():
            specs[app_id] = AppSpec(app_id, program["label"], "window", exe=program["path"])
    return specs


def folder_paths(config: dict[str, Any]) -> dict[str, Path]:
    return {name: Path(path) for name, path in config["folders"].items() if Path(path).is_dir()}


def catalog(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the agent reports to the backend: app ids and labels, and folder names (never paths)."""
    config = config if config is not None else load_config()
    return {
        "apps": [spec.describe() for spec in app_specs(config).values()],
        "workspaces": sorted(folder_paths(config)),
    }
