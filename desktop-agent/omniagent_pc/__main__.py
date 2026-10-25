"""Allow `python -m omniagent_pc` from the desktop-agent folder."""

from omniagent_pc.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
