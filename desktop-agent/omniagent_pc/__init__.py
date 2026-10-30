"""OmniAgent — local Windows PC agent."""

from omniagent_pc.models import StepResult, TaskResult

__all__ = ["StepResult", "TaskResult", "run_phase1_task"]


def __getattr__(name: str):
    # Imported lazily so the pure-Python parts (plan runner, tests) load without the Windows UI libraries.
    if name == "run_phase1_task":
        from omniagent_pc.runner import run_phase1_task

        return run_phase1_task
    raise AttributeError(name)
