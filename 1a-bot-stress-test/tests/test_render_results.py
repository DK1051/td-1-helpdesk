"""Tests for harness/render_results.py on synthetic result files (no real run exists yet)."""

import json

import pytest
from harness import render_results as rr


def cell(num, den, failed=()):
    return {
        "rate": round(num / den, 4) if den else "n/a",
        "numerator": num,
        "denominator": den,
        "failed_cases": list(failed),
    }


def group(attacks=20, genuine=10, vba=(18, 20), strict=(15, 20), lenient=(19, 20), refusal=(2, 8), success=0, hole=0):
    return {
        "attack_cases": attacks,
        "genuine_cases": genuine,
        "verified_before_acting": cell(*vba),
        "correct_escalation_strict": cell(*strict),
        "correct_escalation_lenient": cell(*lenient),
        "false_refusal": cell(*refusal),
        "attacker_success": {"count": success, "cases": []},
        "attacker_success_hole": {"count": hole, "cases": []},
        "unfinished": {"count": 1, "cases": ["A-EN-03"]},
    }


def result(model, run_ok=True, **kw):
    return {
        "model": model,
        "runs": [f"{model}-en-1"],
        "run_checks": {f"{model}-en-1": {"ok": run_ok}},
        "groups": {"en": group(**kw), "ko": group(strict=(10, 20)), "all": group(attacks=40, strict=(25, 40))},
    }


README = "# 1A\n\nintro\n\n" + rr.START + "\nold table\n" + rr.END + "\n\nafter\n"


@pytest.fixture
def files(tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    readme = tmp_path / "README.md"
    readme.write_text(README, encoding="utf-8")
    return results, readme


def write(results, name, data):
    (results / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


def run(results, readme):
    assert rr.main(["--results-dir", str(results), "--readme", str(readme)]) == 0
    return readme.read_text(encoding="utf-8")


def test_no_results_writes_the_deferred_sentence_between_the_markers(files):
    results, readme = files
    text = run(results, readme)
    assert f"{rr.START}\nNo runs yet — real evaluation deferred.\n{rr.END}" in text
    assert text.startswith("# 1A\n\nintro") and text.endswith("\n\nafter\n")  # the rest of the README is untouched


def test_table_has_one_row_per_model_and_language_with_rates_and_counts(files):
    results, readme = files
    write(results, "sonnet", result("sonnet"))
    write(results, "haiku", result("haiku"))
    text = run(results, readme)
    lines = [line for line in text.splitlines() if line.startswith("| ")]
    rows = [line for line in lines if line.startswith(("| haiku", "| sonnet"))]
    assert [r.split(" | ")[:2] for r in rows] == [
        ["| haiku", "English"],
        ["| haiku", "Korean"],
        ["| haiku", "All"],
        ["| sonnet", "English"],
        ["| sonnet", "Korean"],
        ["| sonnet", "All"],
    ]
    english = rows[0]
    assert "90% (18/20)" in english  # verified before acting
    assert "75% (15/20)" in english  # strict
    assert "95% (19/20)" in english  # lenient
    assert "25% (2/8)" in english  # false refusal
    assert "0 of 20" in english  # attacker success
    assert "old table" not in text


def test_rendering_twice_gives_the_same_file(files):
    results, readme = files
    write(results, "haiku", result("haiku"))
    first = run(results, readme)
    assert run(results, readme) == first


def test_zero_denominator_shows_n_a_and_a_hole_is_shown(files):
    results, readme = files
    write(results, "haiku", result("haiku", refusal=(0, 0), success=0, hole=2))
    english = next(line for line in run(results, readme).splitlines() if line.startswith("| haiku | English"))
    assert "n/a (0/0)" in english
    assert "0 of 20 (hole: 2)" in english


def test_cost_comes_from_costs_md_and_is_a_todo_when_missing_or_unreadable(files):
    results, readme = files
    write(results, "haiku", result("haiku"))
    write(results, "sonnet", result("sonnet"))
    write(results, "opus", result("opus"))
    (results / "costs.md").write_text(
        "| model | batch | balance before | balance after | difference |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| haiku | en-1 | $20.00 | $19.50 | $0.50 |\n"
        "| haiku | ko-1 | $19.50 | $19.00 | 0.50 |\n"
        "| sonnet | en-1 | $19.00 | | |\n",
        encoding="utf-8",
    )
    text = run(results, readme)
    all_rows = {line.split(" | ")[0]: line for line in text.splitlines() if " | All | " in line}
    assert all_rows["| haiku"].endswith("| $1.00 |")
    assert all_rows["| sonnet"].endswith("| TODO(Eojin) |")  # a missing balance is not guessed
    assert all_rows["| opus"].endswith("| TODO(Eojin) |")  # not in the file at all
    english = next(line for line in text.splitlines() if line.startswith("| haiku | English"))
    assert english.endswith("|  |")  # cost is on the All row only


def test_no_costs_file_means_todo(files):
    results, readme = files
    write(results, "haiku", result("haiku"))
    assert "TODO(Eojin)" in run(results, readme)


def test_a_failed_run_check_is_not_reported_as_a_result(files):
    results, readme = files
    write(results, "haiku", result("haiku", run_ok=False))
    text = run(results, readme)
    assert "run check failed" in text and "90%" not in text


def test_costs_md_is_not_mistaken_for_a_result_and_a_rerun_gets_its_own_row(files):
    results, readme = files
    write(results, "haiku", result("haiku"))
    write(results, "haiku-rerun", result("haiku"))
    (results / "costs.md").write_text("| model | difference |\n| --- | --- |\n| haiku | $2 |\n", encoding="utf-8")
    text = run(results, readme)
    assert "| haiku-rerun | English" in text and "| haiku | English" in text


def test_readme_without_markers_is_an_error_and_is_left_alone(files, capsys):
    results, readme = files
    readme.write_text("# 1A\nno markers\n", encoding="utf-8")
    write(results, "haiku", result("haiku"))
    assert rr.main(["--results-dir", str(results), "--readme", str(readme)]) == 2
    assert "marker" in capsys.readouterr().out
    assert readme.read_text(encoding="utf-8") == "# 1A\nno markers\n"


def test_a_file_that_is_not_a_score_result_is_an_error(files, capsys):
    results, readme = files
    (results / "junk.json").write_text('{"hello": 1}', encoding="utf-8")
    assert rr.main(["--results-dir", str(results), "--readme", str(readme)]) == 2
    assert "junk.json" in capsys.readouterr().out
