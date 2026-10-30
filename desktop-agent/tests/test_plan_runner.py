from __future__ import annotations

from omniagent_pc.plan_runner import MAX_ATTEMPTS, RunContext, StepOutcome, run_plan


def plan(*types: str) -> list[dict]:
    return [{"index": i, "action": {"type": t}} for i, t in enumerate(types)]


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[int, str]] = []
        self.details: dict[tuple[int, str], str] = {}
        self.shots: list[bytes | None] = []

    def __call__(self, index: int, status: str, detail: str, shot: bytes | None = None) -> None:
        self.events.append((index, status))
        self.details[(index, status)] = detail
        self.shots.append(shot)


def ok(_action, _ctx) -> StepOutcome:
    return StepOutcome(True, "done")


class Screen:
    """A fake app whose visible text can be scripted."""

    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)
        self.looks = 0

    def observe_text(self) -> str:
        self.looks += 1
        return self.texts[min(self.looks - 1, len(self.texts) - 1)]


def run(steps, executors, ctx=None, rec=None, **kw):
    rec = rec or Recorder()
    sleeps: list[float] = []
    outcome = run_plan(steps, executors, ctx or RunContext(), rec, sleep=sleeps.append, **kw)
    return outcome, rec, sleeps


def test_runs_every_step_in_order() -> None:
    outcome, rec, _ = run(plan("a", "b"), {"a": ok, "b": ok})
    assert outcome.status == "completed"
    assert rec.events == [(0, "running"), (0, "success"), (1, "running"), (1, "success")]


def test_failure_stops_the_plan_and_skips_the_rest() -> None:
    calls: list[str] = []

    def bad(_a, _c) -> StepOutcome:
        calls.append("bad")
        return StepOutcome(False, "no focus")

    def never(_a, _c) -> StepOutcome:
        calls.append("never")
        return StepOutcome(True)

    outcome, rec, _ = run(plan("a", "bad", "c"), {"a": ok, "bad": bad, "c": never})
    assert outcome.status == "partial"
    assert outcome.error == "no focus"
    assert "never" not in calls
    assert (2, "skipped") in rec.events


def test_an_action_that_did_nothing_is_retried_then_fails() -> None:
    calls = {"n": 0}

    def flaky(_a, _c) -> StepOutcome:
        calls["n"] += 1
        return StepOutcome(False, "window not ready")

    outcome, rec, sleeps = run(plan("flaky"), {"flaky": flaky})
    assert calls["n"] == MAX_ATTEMPTS == 3
    assert outcome.status == "failed"
    assert (0, "failed") in rec.events
    assert len(sleeps) == 2  # waits between attempts, not after the last


def test_an_action_that_works_on_the_second_try_succeeds() -> None:
    calls = {"n": 0}

    def second_time(_a, _c) -> StepOutcome:
        calls["n"] += 1
        return StepOutcome(calls["n"] == 2, "ok")

    outcome, _, _ = run(plan("x"), {"x": second_time})
    assert outcome.status == "completed" and calls["n"] == 2


def test_first_step_failing_is_failed_not_partial() -> None:
    outcome, _, _ = run(plan("bad"), {"bad": lambda a, c: StepOutcome(False, "x")})
    assert outcome.status == "failed"


def test_unknown_action_is_refused_not_guessed() -> None:
    outcome, rec, _ = run(plan("a", "format_disk"), {"a": ok})
    assert outcome.status == "partial"
    assert "format_disk" in outcome.error
    assert (1, "failed") in rec.events


def test_a_crashing_executor_becomes_a_failed_step() -> None:
    def boom(_a, _c):
        raise RuntimeError("window vanished")

    outcome, _, _ = run(plan("boom"), {"boom": boom})
    assert outcome.status == "failed"
    assert "window vanished" in outcome.error


def test_stop_request_skips_remaining_steps() -> None:
    flags = iter([False, True])
    outcome, rec, _ = run(plan("a", "b"), {"a": ok, "b": ok}, should_stop=lambda: next(flags))
    assert outcome.status == "partial"
    assert (1, "skipped") in rec.events


def test_steps_share_context() -> None:
    def opener(_a, ctx: RunContext) -> StepOutcome:
        ctx.driver = "window-1"
        return StepOutcome(True)

    seen: list[object] = []

    def user(_a, ctx: RunContext) -> StepOutcome:
        seen.append(ctx.driver)
        return StepOutcome(True)

    run(plan("open", "use"), {"open": opener, "use": user})
    assert seen == ["window-1"]


# verification
def typer(text: str):
    return lambda a, c: StepOutcome(True, "typed", expected=text)


def test_a_step_is_confirmed_when_the_text_is_on_screen() -> None:
    ctx = RunContext(driver=Screen("Untitled Notepad Hello from OmniAgent"))
    outcome, rec, _ = run(plan("type"), {"type": typer("Hello from OmniAgent")}, ctx)
    assert outcome.status == "completed"
    assert "confirmed on screen (1.00)" in rec.details[(0, "success")]


def test_a_slow_screen_is_re_observed_without_repeating_the_action() -> None:
    acted = {"n": 0}

    def act(_a, _c) -> StepOutcome:
        acted["n"] += 1
        return StepOutcome(True, "typed", expected="Hello from OmniAgent")

    screen = Screen("Untitled Notepad", "Untitled Notepad", "Untitled Notepad Hello from OmniAgent")
    outcome, rec, sleeps = run(plan("type"), {"type": act}, RunContext(driver=screen))
    assert outcome.status == "completed"
    assert acted["n"] == 1  # never typed twice
    assert screen.looks == 3
    assert len(sleeps) == 2


def test_unconfirmed_step_is_unverified_and_stops_the_plan() -> None:
    screen = Screen("Untitled Notepad File Edit Format View Help quarterly budget totals")
    outcome, rec, _ = run(plan("type", "b"), {"type": typer("Dear team thank you"), "b": ok}, RunContext(driver=screen))
    assert (0, "unverified") in rec.events
    assert "could not confirm" in rec.details[(0, "unverified")]
    assert (1, "skipped") in rec.events
    assert screen.looks == 3  # looked three times, no more
    assert outcome.status == "partial"  # it did act, so it is partial rather than failed


def test_steps_without_an_expectation_are_not_content_checked() -> None:
    screen = Screen("anything")
    outcome, _, _ = run(plan("press"), {"press": ok}, RunContext(driver=screen))
    assert outcome.status == "completed" and screen.looks == 0


def test_an_unreadable_screen_is_unverified_not_a_crash() -> None:
    class Broken:
        def observe_text(self) -> str:
            raise RuntimeError("UI tree unavailable")

    outcome, rec, _ = run(plan("type"), {"type": typer("hi")}, RunContext(driver=Broken()))
    assert (0, "unverified") in rec.events
    assert "UI tree unavailable" in rec.details[(0, "unverified")]


def test_no_driver_means_nothing_to_observe() -> None:
    outcome, rec, _ = run(plan("type"), {"type": typer("hi")}, RunContext())
    assert (0, "unverified") in rec.events


# screenshots and cleanup
def test_every_finished_step_reports_a_screenshot() -> None:
    ctx = RunContext(capture_jpeg=lambda: b"jpeg-bytes")
    _, rec, _ = run(plan("a", "b"), {"a": ok, "b": ok}, ctx)
    finished = [shot for (event, shot) in zip(rec.events, rec.shots) if event[1] == "success"]
    assert finished == [b"jpeg-bytes", b"jpeg-bytes"]


def test_a_failing_screenshot_does_not_fail_the_step() -> None:
    def broken() -> bytes:
        raise OSError("no display")

    outcome, _, _ = run(plan("a"), {"a": ok}, RunContext(capture_jpeg=broken))
    assert outcome.status == "completed"


def test_cleanups_run_in_reverse_order_and_survive_errors() -> None:
    order: list[str] = []
    ctx = RunContext()
    ctx.cleanups += [lambda: order.append("first"), lambda: 1 / 0, lambda: order.append("last")]
    ctx.cleanup()
    assert order == ["last", "first"] and ctx.cleanups == []
