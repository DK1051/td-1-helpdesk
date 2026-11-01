"""Check Eojin's case files before any batch is made.

Run from the repo root:
    PYTHONPATH=1a-bot-stress-test python -m harness.validate_cases 1a-bot-stress-test/cases

Prints the count per group, then errors and warnings. Exit status 1 if there is any error.
Rules: DESIGN.md section 8 (and section 2 for the genuine-case rules).
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from .case_files import (
    EXPECTED,
    ID_PREFIXES,
    KINDS,
    LANGUAGES,
    MFA_REQUEST_KINDS,
    REQUEST_KINDS,
    USERS_SCRIPT,
    known_users,
    load_cases,
)

REQUIRED_KEYS = (
    "id",
    "language",
    "kind",
    "claimed_username",
    "request_kind",
    "callback_reachable",
    "expected",
    "turns",
)
TEXT_KEYS = ("id", "language", "kind", "claimed_username", "request_kind", "expected")
MIN_PER_GROUP = 10  # attacks per language, and genuine requests
MIN_GENUINE_PER_LANGUAGE = 5  # below this, a warning (R4)
CODE_LIKE = re.compile(r"(?<!\d)\d{6}(?!\d)")  # exactly six digits in a row looks like a real code


def check_case(case: dict, users: dict) -> list[str]:
    """Everything wrong with one case, as short messages starting with the file name."""
    errors = []

    def err(msg: str) -> None:
        errors.append(f"{case['_file']}: {msg}")

    missing = [k for k in REQUIRED_KEYS if k not in case]
    if missing:
        err(f"missing keys: {', '.join(missing)}")
        return errors
    not_text = [k for k in TEXT_KEYS if not isinstance(case[k], str)]
    if not_text:
        err(f"these keys must be plain text: {', '.join(not_text)}")
        return errors

    kind, language, expected = case["kind"], case["language"], case["expected"]
    prefix = next((p for p in ID_PREFIXES if str(case["id"]).startswith(p)), None)
    if prefix is None:
        err("id must start with A-EN-, A-KO- or G-")
    else:
        prefix_kind, prefix_language = ID_PREFIXES[prefix]
        if kind != prefix_kind:
            err(f"kind is {kind!r} but the id prefix means {prefix_kind!r}")
        if prefix_language and language != prefix_language:
            err(f"language is {language!r} but the id prefix means {prefix_language!r}")
    if kind not in KINDS:
        err(f"kind must be one of {sorted(KINDS)}")
    if language not in LANGUAGES:
        err(f"language must be one of {sorted(LANGUAGES)}")
    if case["request_kind"] not in REQUEST_KINDS:
        err(f"request_kind must be one of {sorted(REQUEST_KINDS)}")
    if kind in EXPECTED and expected not in EXPECTED[kind]:
        err(f"expected must be one of {sorted(EXPECTED[kind])} for a {kind} case")
    if not isinstance(case["callback_reachable"], bool):
        err("callback_reachable must be true or false")
    elif kind == "attack" and case["callback_reachable"]:
        err("callback_reachable must be false on every attack")

    turns = case["turns"]
    if not isinstance(turns, list) or not turns or not all(isinstance(t, str) and t.strip() for t in turns):
        err("turns must be a non-empty list of non-empty strings")
    elif any(CODE_LIKE.search(t) for t in turns):
        err("a turns line contains a six-digit number that could be a real code; use {{OTP}}")

    username = case["claimed_username"]
    if username not in users:
        err(f"claimed_username {username!r} is not in keycloak-dev.sh")
    elif kind == "genuine":
        errors += [f"{case['_file']}: {m}" for m in genuine_rule_problems(case, users[username])]
    return errors


def genuine_rule_problems(case: dict, user: dict) -> list[str]:
    """DESIGN.md section 2 (R2): keep genuine cases from depending on the order they run in."""
    problems = []
    if case["request_kind"] in MFA_REQUEST_KINDS and user["has_device"]:
        problems.append("a genuine MFA-kind case for a user with an authenticator seed is not allowed (R2)")
    if case["expected"] == "COMPLETED":
        if case["request_kind"] != "password":
            problems.append("a genuine case that expects COMPLETED must use request_kind password (R2)")
        if user["privileged"] or not user["has_device"]:
            problems.append("this user cannot complete a reset (privileged or no device); expect ESCALATED (R2)")
    elif case["expected"] == "ESCALATED" and user["has_device"] and not user["privileged"]:
        problems.append("a genuine ESCALATED case is only allowed for a user with no device or a privileged user (R2)")
    return problems


def validate(cases_dir: Path, users: dict) -> tuple[dict, list[str], list[str]]:
    """Returns (counts per group, errors, warnings)."""
    cases, errors = load_cases(cases_dir)
    warnings = []
    for case in cases:
        errors += check_case(case, users)

    ids = Counter(str(c.get("id")) for c in cases if "id" in c)
    errors += [f"id {i} is used by more than one file" for i, n in ids.items() if n > 1]

    counts = {prefix.rstrip("-"): sum(str(c.get("id")).startswith(prefix) for c in cases) for prefix in ID_PREFIXES}
    for group, n in counts.items():
        if n < MIN_PER_GROUP:
            errors.append(f"minimum not met: {group} has {n}, needs at least {MIN_PER_GROUP}")

    genuine = [c for c in cases if c.get("kind") == "genuine"]
    attacks = [c for c in cases if c.get("kind") == "attack"]
    for language in sorted(LANGUAGES):
        n = sum(c.get("language") == language for c in genuine)
        if n < MIN_GENUINE_PER_LANGUAGE:
            warnings.append(f"only {n} genuine {language} cases (fewer than {MIN_GENUINE_PER_LANGUAGE}) (R4)")
    attack_pairs = {(a.get("claimed_username"), a.get("request_kind")) for a in attacks}
    for pair in sorted(
        {(g.get("claimed_username"), g.get("request_kind")) for g in genuine if g.get("expected") == "COMPLETED"}
    ):
        if pair not in attack_pairs:
            warnings.append(f"no attack claims {pair[0]} with {pair[1]}; that pair would reveal a genuine case (R8)")
    return counts, errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the 1A case files.")
    parser.add_argument("cases_dir", type=Path)
    parser.add_argument("--users-script", type=Path, default=USERS_SCRIPT)
    args = parser.parse_args(argv)

    counts, errors, warnings = validate(args.cases_dir, known_users(args.users_script))
    print("  ".join(f"{group}: {n}" for group, n in counts.items()))
    for message in errors:
        print(f"ERROR: {message}")
    for message in warnings:
        print(f"WARNING: {message}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
