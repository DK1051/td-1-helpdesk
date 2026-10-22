"""Replay runner: plays a case file (a scripted list of API calls) against the service.

    python -m app.replay                              # all cases in tests/replay/, offline (fake Keycloak)
    python -m app.replay tests/replay/T07.yaml        # one case
    python -m app.replay --base-url http://localhost:8000 tests/replay/T07.yaml   # a live server

Run from 1h-verified-reset/. It prints the request state after every step and the final states.
These cases test the service's rules, not an agent's judgement (the agent is tested in 1A).
A case file holds API calls only: no caller dialogue and no secrets. A one-time code is written
as {totp:USERNAME} and filled in at run time from the seed source.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pyotp
import yaml

SERVICE_DIR = Path(__file__).resolve().parent.parent
CASES_DIR = SERVICE_DIR / "tests" / "replay"
PLACEHOLDER = re.compile(r"\{([A-Za-z0-9_.:-]+)\}")


class ReplayError(Exception):
    pass


@dataclass
class CaseResult:
    case_id: str
    lines: list[str] = field(default_factory=list)  # what was printed, step by step
    final_states: list[str] = field(default_factory=list)  # one per request the case created
    alerts: int = 0  # alerts raised during this case
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def load_case(path: Path) -> dict:
    case = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for key in ("id", "source", "steps", "expected_final_state", "expected_alerts"):
        if key not in case:
            raise ReplayError(f"{path}: missing '{key}'")
    return case


def fill(value, variables: dict, code_for):
    """Replace {name} with a saved value and {totp:user} with a fresh one-time code."""
    if isinstance(value, str):

        def lookup(match):
            name = match.group(1)
            if name.startswith("totp:"):
                return code_for(name.split(":", 1)[1])
            if name not in variables:
                raise ReplayError(f"unknown variable {{{name}}}")
            return str(variables[name])

        return PLACEHOLDER.sub(lookup, value)
    if isinstance(value, dict):
        return {k: fill(v, variables, code_for) for k, v in value.items()}
    if isinstance(value, list):
        return [fill(v, variables, code_for) for v in value]
    return value


def run_case(case: dict, http, code_for) -> CaseResult:
    """`http` is anything with .request(method, path, json=..., headers=...) (TestClient or httpx.Client)."""
    result = CaseResult(case_id=case["id"])
    alerts_before = len(http.get("/alerts").json())
    variables: dict = {}
    created: list[str] = []

    for number, step in enumerate(case["steps"], start=1):
        method, path = step["call"].split(" ", 1)
        path = fill(path, variables, code_for)
        body = fill(step.get("body"), variables, code_for)
        headers = fill(step.get("headers") or {}, variables, code_for)
        response = http.request(method, path, json=body, headers=headers)
        try:
            data = response.json()
        except ValueError:
            data = {}
        for var, field_name in (step.get("save") or {}).items():
            variables[var] = data.get(field_name)
            if var == "request_id" and data.get(field_name):
                created.append(data[field_name])

        state = "-"
        if variables.get("request_id"):
            state = http.get(f"/reset-requests/{variables['request_id']}").json().get("state", "?")
        result.lines.append(
            f"  {number:>2}. {step['name']}\n      {method} {path} -> HTTP {response.status_code}, state {state}"
        )
        expected = step.get("expect_status")
        if expected is not None and response.status_code != expected:
            result.problems.append(f"step {number}: expected HTTP {expected}, got {response.status_code}")

    result.final_states = [http.get(f"/reset-requests/{rid}").json()["state"] for rid in created]
    result.alerts = len(http.get("/alerts").json()) - alerts_before
    wanted = case["expected_final_state"]
    if not result.final_states:
        result.problems.append("the case created no request")
    for state in result.final_states:
        if state != wanted:
            result.problems.append(f"final state {state}, expected {wanted}")
    if result.alerts != case["expected_alerts"]:
        result.problems.append(f"{result.alerts} alert(s), expected {case['expected_alerts']}")
    return result


def format_result(result: CaseResult) -> str:
    verdict = "ok" if result.passed else "FAILED: " + "; ".join(result.problems)
    head = f"{result.case_id}: final {', '.join(result.final_states)}; alerts {result.alerts}; {verdict}"
    return "\n".join([f"== {result.case_id}", *result.lines, head])


# ---- where one-time codes come from ------------------------------------------------------------
def seed_code_provider(seeds_path: Path):
    """Live mode: compute the current code from the dev seed file (dev only; see README, D1).

    The service refuses a code from a time step it has already accepted. So if this process already
    used the current step for a user, wait for the next 30-second step before asking again.
    (A code used by some OTHER process in the same 30 seconds, e.g. a curl step, is not known here:
    wait for the next step yourself.)
    """
    last_step_used: dict[str, int] = {}

    def code_for(username: str) -> str:
        totp = pyotp.TOTP(json.loads(Path(seeds_path).read_text())[username])
        step = totp.timecode(datetime.now(UTC))
        if last_step_used.get(username, -1) >= step:
            time.sleep(totp.interval - time.time() % totp.interval + 0.5)
            step = totp.timecode(datetime.now(UTC))
        last_step_used[username] = step
        return totp.generate_otp(step)

    return code_for


def _returning(thing):
    """A zero-argument function that returns `thing`, for app.dependency_overrides."""

    def provide():
        return thing

    return provide


def _fresh_codes(fake):
    """Offline: a code from the fake authenticator, always newer than any code used before."""

    def code_for(_username: str) -> str:
        return fake.fresh_code()

    return code_for


def run_offline(paths: list[Path]) -> list[CaseResult]:
    """Each case gets a fresh service state and a fresh fake Keycloak. All cases share one temporary
    pair of log files, so a case's alert count is measured as a difference (after minus before)."""
    from fastapi.testclient import TestClient

    from .fake_keycloak import dev_users_fake
    from .main import app, get_keycloak, get_store
    from .state import Store

    results = []
    names = ("AUDIT_LOG_PATH", "ALERTS_LOG_PATH")
    saved = {name: os.environ.get(name) for name in names}  # put back afterwards: callers' settings stay theirs
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["AUDIT_LOG_PATH"] = str(Path(tmp) / "audit.jsonl")
            os.environ["ALERTS_LOG_PATH"] = str(Path(tmp) / "alerts.jsonl")
            for path in paths:
                fake, store = dev_users_fake(), Store()
                app.dependency_overrides[get_keycloak] = _returning(fake)
                app.dependency_overrides[get_store] = _returning(store)
                try:
                    results.append(run_case(load_case(path), TestClient(app), _fresh_codes(fake)))
                finally:
                    app.dependency_overrides.clear()
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return results


def run_live(paths: list[Path], base_url: str) -> list[CaseResult]:
    seeds = Path(os.environ.get("SEEDS_PATH", SERVICE_DIR / ".dev" / "seeds.json"))
    with httpx.Client(base_url=base_url, timeout=10) as http:
        return [run_case(load_case(p), http, seed_code_provider(seeds)) for p in paths]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Replay case files against the Verified Reset Service")
    parser.add_argument("cases", nargs="*", type=Path, help="case files (default: all in tests/replay/)")
    parser.add_argument("--base-url", help="use a running service, e.g. http://localhost:8000 (default: offline)")
    args = parser.parse_args(argv)
    paths = args.cases or sorted(CASES_DIR.glob("*.yaml"))
    results = run_live(paths, args.base_url) if args.base_url else run_offline(paths)
    for result in results:
        print(format_result(result))
    failed = [r.case_id for r in results if not r.passed]
    print(
        f"\n{len(results) - len(failed)}/{len(results)} cases as expected" + (f"; FAILED: {failed}" if failed else "")
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
