"""Replays every case file against the service (fake Keycloak): attacks must be stopped, the control must pass."""

import pytest
from app import replay

CASE_FILES = sorted(replay.CASES_DIR.glob("*.yaml"))
CONTROL = "control"
ATTACKS = [p for p in CASE_FILES if p.stem != CONTROL]


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    """Run every case once (offline) and index the results by case id."""
    return {r.case_id: r for r in replay.run_offline(CASE_FILES)}


def test_the_expected_case_files_exist():
    assert [p.stem for p in CASE_FILES] == sorted(["T07", "T08", "T09", "T10", "clorox-alleged", "control"])


@pytest.mark.parametrize("path", ATTACKS, ids=lambda p: p.stem)
def test_attack_case_ends_blocked_or_escalated_never_completed(path, results):
    result = results[replay.load_case(path)["id"]]
    assert result.final_states, "the case created no request"
    assert set(result.final_states) <= {"BLOCKED", "ESCALATED"}
    assert "COMPLETED" not in result.final_states
    assert result.passed, result.problems  # also checks every step's HTTP status and the alert count


def test_clorox_case_raises_at_least_one_alert(results):
    assert results["clorox-alleged"].alerts >= 1
    assert results["clorox-alleged"].final_states == ["BLOCKED"] * 3


def test_positive_control_ends_completed(results):
    control = results[CONTROL]
    assert control.final_states == ["COMPLETED"] and control.alerts == 0
    assert control.passed, control.problems


API_FIELDS = {"kind", "claimed_username", "agent_id", "channel", "new_phone", "number_dialed", "reached", "code"}
STEP_KEYS = {"name", "call", "body", "headers", "expect_status", "save"}


def test_case_files_hold_api_calls_only_and_no_secrets():
    for path in CASE_FILES:
        case = replay.load_case(path)
        assert set(case) == {"id", "source", "steps", "expected_final_state", "expected_alerts"}
        for step in case["steps"]:
            assert set(step) <= STEP_KEYS  # no free-text caller lines anywhere but the step name
            body = step.get("body") or {}
            assert set(body) <= API_FIELDS
            if "code" in body:  # a placeholder or an obviously wrong code, never a real one
                assert body["code"] == "000000" or body["code"].startswith("{totp:")
            assert not step.get("headers")  # no tokens in case files
