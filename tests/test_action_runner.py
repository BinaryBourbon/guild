"""Tests for run_primitive retry logic (item #1 fix)."""
import pytest

from guild.primitives import ActionResult, PrimitiveError, run_primitive


def _always_succeeds(**kwargs) -> ActionResult:
    return ActionResult(success=True, data=kwargs)


def _always_transient(**kwargs) -> ActionResult:  # noqa: ARG001
    raise PrimitiveError("transient", "network blip")


def _always_permanent(**kwargs) -> ActionResult:  # noqa: ARG001
    raise PrimitiveError("permanent", "bad input")


def _succeeds_on_attempt(n: int):
    """Returns a callable that fails transiently *n-1* times then succeeds."""
    calls = {"count": 0}

    def fn(**kwargs) -> ActionResult:  # noqa: ARG001
        calls["count"] += 1
        if calls["count"] < n:
            raise PrimitiveError("transient", f"attempt {calls['count']}")
        return ActionResult(success=True, data={"attempt": calls["count"]})

    return fn


def test_success_no_retries():
    result = run_primitive(_always_succeeds, {"x": 1}, _sleep=lambda _: None)
    assert result.success
    assert result.data == {"x": 1}


def test_permanent_error_returns_immediately():
    calls = []

    def fn(**_):
        calls.append(1)
        raise PrimitiveError("permanent", "bad")

    result = run_primitive(fn, {}, _sleep=lambda _: None)
    assert not result.success
    assert result.error.kind == "permanent"
    assert len(calls) == 1  # no retry on permanent


def test_transient_retries_then_returns_result_not_raises():
    """Critical: final transient attempt must RETURN ActionResult, not raise."""
    sleeps = []
    result = run_primitive(_always_transient, {}, max_retries=3, _sleep=sleeps.append)
    assert not result.success
    assert result.error.kind == "transient"
    assert "max retries" in result.error.message
    # Should have slept between attempts 0→1 and 1→2 (not after final attempt)
    assert len(sleeps) == 2
    assert sleeps == [1.0, 2.0]  # 2^0, 2^1


def test_transient_succeeds_on_second_attempt():
    fn = _succeeds_on_attempt(2)
    sleeps = []
    result = run_primitive(fn, {}, max_retries=3, _sleep=sleeps.append)
    assert result.success
    assert result.data["attempt"] == 2
    assert len(sleeps) == 1


def test_max_retries_one_returns_immediately():
    """max_retries=1 means one attempt, no sleep, returns failed result."""
    sleeps = []
    result = run_primitive(_always_transient, {}, max_retries=1, _sleep=sleeps.append)
    assert not result.success
    assert result.error.kind == "transient"
    assert len(sleeps) == 0
