from __future__ import annotations

from omniagent_pc.plan_runner import RunContext, StepOutcome, run_plan


def plan(*types: str) -> list[dict]:
    return [{"index": i, "action": {"type": t}} for i, t in enumerate(types)]


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[int, str]] = []

    def __call__(self, index: int, status: str, detail: str) -> None:
        self.events.append((index, status))


def ok(_action, _ctx) -> StepOutcome:
    return StepOutcome(True, "done")


def test_runs_every_step_in_order() -> None:
    rec = Recorder()
    outcome = run_plan(plan("a", "b"), {"a": ok, "b": ok}, RunContext(), rec)
    assert outcome.status == "completed"
    assert rec.events == [(0, "running"), (0, "success"), (1, "running"), (1, "success")]


def test_failure_stops_the_plan_and_skips_the_rest() -> None:
    rec = Recorder()
    calls: list[str] = []

    def bad(_a, _c) -> StepOutcome:
        calls.append("bad")
        return StepOutcome(False, "no focus")

    def never(_a, _c) -> StepOutcome:
        calls.append("never")
        return StepOutcome(True)

    outcome = run_plan(plan("a", "bad", "c"), {"a": ok, "bad": bad, "c": never}, RunContext(), rec)
    assert outcome.status == "partial"
    assert outcome.error == "no focus"
    assert calls == ["bad"]
    assert (2, "skipped") in rec.events


def test_first_step_failing_is_failed_not_partial() -> None:
    outcome = run_plan(plan("bad"), {"bad": lambda a, c: StepOutcome(False, "x")}, RunContext(), Recorder())
    assert outcome.status == "failed"


def test_unknown_action_is_refused_not_guessed() -> None:
    rec = Recorder()
    outcome = run_plan(plan("a", "format_disk"), {"a": ok}, RunContext(), rec)
    assert outcome.status == "partial"
    assert "format_disk" in outcome.error
    assert (1, "failed") in rec.events


def test_a_crashing_executor_becomes_a_failed_step() -> None:
    def boom(_a, _c):
        raise RuntimeError("window vanished")

    outcome = run_plan(plan("boom"), {"boom": boom}, RunContext(), Recorder())
    assert outcome.status == "failed"
    assert "window vanished" in outcome.error


def test_stop_request_skips_remaining_steps() -> None:
    rec = Recorder()
    flags = iter([False, True])
    outcome = run_plan(plan("a", "b"), {"a": ok, "b": ok}, RunContext(), rec, should_stop=lambda: next(flags))
    assert outcome.status == "partial"
    assert (1, "skipped") in rec.events


def test_steps_share_context() -> None:
    def opener(_a, ctx: RunContext) -> StepOutcome:
        ctx.session = "window-1"
        return StepOutcome(True)

    seen: list[object] = []

    def user(_a, ctx: RunContext) -> StepOutcome:
        seen.append(ctx.session)
        return StepOutcome(True)

    run_plan(plan("open", "use"), {"open": opener, "use": user}, RunContext(), Recorder())
    assert seen == ["window-1"]
