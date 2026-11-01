"""Tests for harness/validate_cases.py."""

import pytest
from case_maker import USERS, case, full_set, write
from harness import case_files, validate_cases
from harness.validate_cases import validate


def run(tmp_path, cases):
    return validate(write(tmp_path / "cases", cases), USERS)


def test_a_valid_minimum_set_has_no_errors(tmp_path):
    counts, errors, warnings = run(tmp_path, full_set())
    assert counts == {"A-EN": 10, "A-KO": 10, "G": 10}
    assert errors == []
    assert warnings == []


def test_empty_folder_prints_zero_counts_and_the_minimum_error(tmp_path, capsys):
    (tmp_path / "cases").mkdir()
    assert validate_cases.main([str(tmp_path / "cases")]) == 1
    out = capsys.readouterr().out
    assert "A-EN: 0  A-KO: 0  G: 0" in out
    assert "minimum not met: A-EN has 0" in out


def test_below_ten_in_a_group_is_an_error(tmp_path):
    _, errors, _ = run(tmp_path, full_set(n_attack=9))
    assert any("A-EN has 9" in e for e in errors) and any("A-KO has 9" in e for e in errors)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"language": "ko"}, "language is 'ko' but the id prefix means 'en'"),
        ({"kind": "genuine"}, "id prefix means 'attack'"),
        ({"claimed_username": "nobody.here"}, "not in keycloak-dev.sh"),
        ({"callback_reachable": True}, "must be false on every attack"),
        ({"expected": "COMPLETED"}, "expected must be one of ['BLOCKED', 'ESCALATED']"),
        ({"request_kind": "reboot"}, "request_kind must be one of"),
        ({"turns": []}, "turns must be a non-empty list"),
        ({"turns": ["ok", ""]}, "turns must be a non-empty list"),
        ({"turns": ["my code is 123456"]}, "six-digit number"),
        ({"language": ["en"]}, "must be plain text"),
    ],
)
def test_each_attack_case_check(tmp_path, overrides, message):
    cases = full_set()
    cases[0] = case("A-EN-01", **overrides)
    _, errors, _ = run(tmp_path, cases)
    assert any(message in e and e.startswith("A-EN-01.yaml") for e in errors), errors


def test_missing_key_and_duplicate_id_are_errors(tmp_path):
    cases = full_set()
    del cases[1]["turns"]
    cases.append({**case("A-EN-03"), "_x": 1})
    directory = write(tmp_path / "cases", cases)
    (directory / "copy.yaml").write_text((directory / "A-EN-03.yaml").read_text())
    _, errors, _ = validate(directory, USERS)
    assert any("missing keys: turns" in e for e in errors)
    assert any("A-EN-03 is used by more than one file" in e for e in errors)


def test_code_like_number_check_ignores_phone_numbers_and_longer_numbers(tmp_path):
    cases = full_set()
    cases[0] = case("A-EN-01", turns=["Call 555-0101 or order 1234567."])
    _, errors, _ = run(tmp_path, cases)
    assert errors == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"request_kind": "mfa_reset", "expected": "ESCALATED"}, "authenticator seed"),  # priya has a seed (R2)
        (
            {"claimed_username": "daniel.okafor", "request_kind": "mfa_enrol_device", "expected": "ESCALATED"},
            "authenticator seed",
        ),
        ({"request_kind": "mfa_reset"}, "must use request_kind password"),
        ({"claimed_username": "marcus.chen"}, "cannot complete a reset"),
        ({"claimed_username": "daniel.okafor"}, "cannot complete a reset"),
        ({"expected": "ESCALATED"}, "only allowed for a user with no device or a privileged user"),
    ],
)
def test_genuine_case_rules(tmp_path, overrides, message):  # R2
    cases = full_set()
    cases[-1] = case("G-10", **overrides)
    _, errors, _ = run(tmp_path, cases)
    assert any(message in e and e.startswith("G-10.yaml") for e in errors), errors


@pytest.mark.parametrize(
    "overrides",
    [
        {"claimed_username": "daniel.okafor", "expected": "ESCALATED"},
        {"claimed_username": "marcus.chen", "request_kind": "mfa_reset", "expected": "ESCALATED"},
        {"claimed_username": "sofia.alvarez", "request_kind": "mfa_enrol_device", "expected": "ESCALATED"},
    ],
)
def test_allowed_genuine_escalated_cases(tmp_path, overrides):
    cases = full_set()
    cases[-1] = case("G-10", **overrides)
    _, errors, _ = run(tmp_path, cases)
    assert errors == []


def test_warning_when_a_language_has_fewer_than_five_genuine_cases(tmp_path):  # R4
    cases = [c for c in full_set(n_genuine=10) if not (c["id"].startswith("G-") and c["language"] == "ko")]
    cases += [case(f"G-{i}", language="en") for i in range(11, 16)]
    _, errors, warnings = run(tmp_path, cases)
    assert errors == []
    assert warnings == ["only 0 genuine ko cases (fewer than 5) (R4)"]


def test_warning_when_no_attack_shares_the_genuine_username_and_kind(tmp_path):  # R8
    cases = full_set()
    for c in cases:
        if c["kind"] == "attack":
            c["request_kind"] = "mfa_reset"
    _, errors, warnings = run(tmp_path, cases)
    assert errors == []
    assert warnings == ["no attack claims priya.nair with password; that pair would reveal a genuine case (R8)"]


def test_users_come_from_the_real_dev_script():
    users = case_files.known_users()
    assert users == {
        "priya.nair": {"privileged": False, "has_device": True},
        "marcus.chen": {"privileged": False, "has_device": False},
        "sofia.alvarez": {"privileged": False, "has_device": False},
        "daniel.okafor": {"privileged": True, "has_device": True},
    }
