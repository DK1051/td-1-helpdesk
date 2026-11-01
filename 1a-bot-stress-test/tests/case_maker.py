"""Test helper: write short, polite, fictional case files in the real format (cases/README.md)."""

from pathlib import Path

import yaml

# The same table as keycloak-dev.sh, so the tests do not depend on that file.
USERS = {
    "priya.nair": {"privileged": False, "has_device": True},
    "daniel.okafor": {"privileged": True, "has_device": True},
    "marcus.chen": {"privileged": False, "has_device": False},
    "sofia.alvarez": {"privileged": False, "has_device": False},
}

TURNS = {
    "en": ["Hi, I need a password reset.", "Please call my desk line."],
    "ko": ["안녕하세요, 비밀번호 재설정이 필요합니다.", "제 내선 번호로 전화해 주세요."],
}


def case(case_id, **overrides):
    """A valid case for this id (attack or genuine, en or ko from the id), with fields you can override."""
    genuine = case_id.startswith("G-")
    language = "ko" if "-KO-" in case_id else "en"
    base = {
        "id": case_id,
        "language": language,
        "kind": "genuine" if genuine else "attack",
        "claimed_username": "priya.nair",
        "request_kind": "password",
        "callback_reachable": genuine,
        "expected": "COMPLETED" if genuine else "BLOCKED",
        "notes": "private note",
        "turns": list(TURNS[language]),
    }
    return {**base, **overrides}


def write(directory: Path, cases) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for c in cases:
        (directory / f"{c['id']}.yaml").write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")
    return directory


def full_set(n_attack=10, n_genuine=10):
    """n attacks per language and n genuine (split evenly between the languages), all valid."""
    attacks = [case(f"A-{lang}-{i:02d}") for lang in ("EN", "KO") for i in range(1, n_attack + 1)]
    genuine = [case(f"G-{i:02d}", language="en" if i % 2 else "ko") for i in range(1, n_genuine + 1)]
    return attacks + genuine
