"""Tests for harness/make_batches.py."""

import json

import pytest
import yaml
from case_maker import case, full_set, write
from harness import make_batches as mb
from harness.case_files import load_cases

SECRET_KEYS = {"id", "kind", "expected", "callback_reachable", "notes"}


def make(tmp_path, cases, seed=mb.DEFAULT_SEED):
    loaded, _ = load_cases(write(tmp_path / "cases", cases))
    return mb.make_batches(loaded, seed)


def test_batches_have_only_the_allowed_keys_and_no_case_id_text(tmp_path):
    batches, manifest = make(tmp_path, full_set())
    mb.write_batches(batches, manifest, tmp_path / "out")
    files = sorted((tmp_path / "out").glob("*.yaml"))
    assert files
    for f in files:
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        for entry in data["cases"]:
            assert set(entry) == set(mb.BATCH_KEYS)
            assert not SECRET_KEYS & set(entry)
        text = f.read_text(encoding="utf-8")
        assert "private note" not in text
        for case_id in (c["id"] for c in full_set()):
            assert case_id not in text


def test_placeholder_is_left_in_place(tmp_path):
    cases = full_set()
    cases[0] = case("A-EN-01", turns=["The code is {{OTP}}."])
    batches, _ = make(tmp_path, cases)
    assert any("The code is {{OTP}}." in c["turns"] for b in batches.values() for c in b)


def test_at_most_twenty_cases_per_file_and_one_language_per_file(tmp_path):
    batches, manifest = make(tmp_path, full_set(n_attack=20, n_genuine=20))
    assert sorted(batches) == ["en-1", "en-2", "ko-1", "ko-2"]
    assert all(len(b) <= mb.MAX_PER_FILE for b in batches.values())
    for name, b in batches.items():
        assert {c["language"] for c in b} == {name.split("-")[0]}
    assert sum(len(b) for b in batches.values()) == 60
    assert len(manifest["calls"]) == 60


def test_manifest_maps_call_ids_back_to_the_labels(tmp_path):
    cases = full_set()
    batches, manifest = make(tmp_path, cases)
    by_id = {c["id"]: c for c in cases}
    assert manifest["seed"] == mb.DEFAULT_SEED
    for name, b in batches.items():
        for entry in b:
            meta = manifest["calls"][entry["call_id"]]
            original = by_id[meta["case_id"]]
            assert meta["batch"] == name
            assert (meta["kind"], meta["expected"], meta["callback_reachable"]) == (
                original["kind"], original["expected"], original["callback_reachable"],
            )  # fmt: skip
            assert entry["turns"] == original["turns"]
    assert sorted(manifest["calls"]) == [f"C-{n:02d}" for n in range(1, 31)]


def test_same_seed_gives_same_output_and_another_seed_differs(tmp_path):
    a = make(tmp_path / "a", full_set())
    b = make(tmp_path / "b", full_set())
    c = make(tmp_path / "c", full_set(), seed=7)
    assert a == b
    assert a != c


def test_call_order_does_not_reveal_the_kind(tmp_path):
    batches, manifest = make(tmp_path, full_set(n_attack=20, n_genuine=20))
    first_file = next(iter(batches.values()))
    kinds = [manifest["calls"][c["call_id"]]["kind"] for c in first_file]
    assert kinds != sorted(kinds)  # attacks and genuine requests are mixed, not grouped


def test_error_when_a_file_would_lack_attacks_or_genuine_cases(tmp_path):  # R4
    only_attacks = [c for c in full_set() if c["kind"] == "attack"]
    with pytest.raises(mb.BatchError, match="would not hold both"):
        make(tmp_path / "x", only_attacks)
    # 25 English attacks + 1 English genuine request -> 2 files, one of them has no genuine case.
    lopsided = [case(f"A-EN-{i:02d}") for i in range(1, 26)] + [case("G-01")]
    with pytest.raises(mb.BatchError, match="would not hold both"):
        make(tmp_path / "y", lopsided)


def test_no_cases_is_an_error(tmp_path):
    with pytest.raises(mb.BatchError, match="no cases"):
        mb.make_batches([])


def test_cli_refuses_invalid_cases_and_writes_nothing(tmp_path, capsys):
    write(tmp_path / "cases", full_set(n_attack=9))
    out = tmp_path / "batches"
    assert mb.main([str(tmp_path / "cases"), str(out)]) == 1
    assert "minimum not met" in capsys.readouterr().out
    assert not out.exists()


def test_cli_writes_batch_files_and_manifest(tmp_path, capsys):
    cases = full_set()
    write(tmp_path / "cases", cases)
    out = tmp_path / "batches"
    assert mb.main([str(tmp_path / "cases"), str(out)]) == 0
    assert (out / "en-1.yaml").exists() and (out / "ko-1.yaml").exists()
    assert len(json.loads((out / "manifest.json").read_text())["calls"]) == 30
