"""Write the README results table from results/*.json (and the cost per model from results/costs.md).

    PYTHONPATH=1a-bot-stress-test python -m harness.render_results
    PYTHONPATH=1a-bot-stress-test python -m harness.render_results --results-dir X --readme Y

The table sits between the two marker lines `<!-- results:start -->` and `<!-- results:end -->` in the README.
Everything between the markers is replaced on each run, so nothing in the table is typed by hand.
One row per model x language (English, Korean, then All). A model's cost is shown on its All row.

results/costs.md is a Markdown table with the columns `model | batch | balance before | balance after | difference`
(Eojin reads the balances; `chores` writes the file). A model's cost is the sum of its `difference` cells. If the file
is missing, or any of that model's cells is empty or not a number, the cost shows as TODO(Eojin).
"""

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START, END = "<!-- results:start -->", "<!-- results:end -->"
NO_RUNS = "No runs yet — real evaluation deferred."
TODO_COST = "TODO(Eojin)"
LANGUAGE_NAMES = {"en": "English", "ko": "Korean", "all": "All"}
HEADER = (
    "| Model | Language | Verified before acting | Correct escalation (strict) | Correct escalation (lenient) "
    "| False refusal | Attacker success | Unfinished | Cost |"
)


class RenderError(Exception):
    pass


# ---- cells -----------------------------------------------------------------------------------------
def rate_cell(cell: dict) -> str:
    """A rate with its counts, for example `85% (17/20)`. A zero denominator is `n/a`."""
    if cell["rate"] == "n/a":
        return "n/a (0/0)"
    return f"{round(cell['rate'] * 100)}% ({cell['numerator']}/{cell['denominator']})"


def success_cell(group: dict) -> str:
    text = f"{group['attacker_success']['count']} of {group['attack_cases']}"
    hole = group["attacker_success_hole"]["count"]
    return f"{text} (hole: {hole})" if hole else text


def group_row(model: str, language: str, group: dict, cost: str, run_ok: bool) -> str:
    name = LANGUAGE_NAMES.get(language, language)
    if not run_ok:
        return f"| {model} | {name} | run check failed: not reported | | | | | | {cost} |"
    cells = [
        rate_cell(group["verified_before_acting"]),
        rate_cell(group["correct_escalation_strict"]),
        rate_cell(group["correct_escalation_lenient"]),
        rate_cell(group["false_refusal"]),
        success_cell(group),
        str(group["unfinished"]["count"]),
    ]
    return f"| {model} | {name} | " + " | ".join(cells) + f" | {cost} |"


# ---- cost ------------------------------------------------------------------------------------------
def read_costs(path: Path) -> dict[str, str]:
    """model -> "$12.34", or TODO(Eojin) when any of that model's difference cells cannot be read."""
    if not path.exists():
        return {}
    model_col = diff_col = None
    totals: dict[str, Decimal] = {}
    missing: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
            continue  # the separator row
        lowered = [c.lower() for c in cells]
        if model_col is None and "model" in lowered:
            model_col = lowered.index("model")
            diff_col = next((i for i, c in enumerate(lowered) if "difference" in c), None)
            continue
        if model_col is None or diff_col is None or len(cells) <= max(model_col, diff_col):
            continue
        model = cells[model_col]
        if not model:
            continue
        try:
            totals[model] = totals.get(model, Decimal(0)) + Decimal(cells[diff_col].replace("$", "").replace(",", ""))
        except InvalidOperation:
            missing.add(model)
    return {m: (TODO_COST if m in missing else f"${totals[m]:.2f}") for m in totals.keys() | missing}


# ---- the table -------------------------------------------------------------------------------------
def load_results(results_dir: Path) -> dict[str, dict]:
    """file stem -> parsed result, in name order. The stem names the row, so `haiku-rerun` is its own row."""
    found = {}
    for path in sorted(Path(results_dir).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise RenderError(f"{path.name}: cannot be read as JSON") from None
        if not isinstance(data, dict) or "groups" not in data:
            raise RenderError(f"{path.name}: not a score.py result (no 'groups')")
        found[path.stem] = data
    return found


def build_table(results: dict[str, dict], costs: dict[str, str]) -> str:
    if not results:
        return NO_RUNS
    rows = [HEADER, "|" + " --- |" * 9]
    for model, data in results.items():
        run_ok = all(c.get("ok") for c in data.get("run_checks", {}).values())
        groups = data["groups"]
        order = [g for g in ("en", "ko") if g in groups] + sorted(g for g in groups if g not in ("en", "ko", "all"))
        order += ["all"] if "all" in groups else []
        for language in order:
            cost = costs.get(model, TODO_COST) if language == "all" else ""
            rows.append(group_row(model, language, groups[language], cost, run_ok))
    note = (
        "Each cell is a rate with its counts (cases that count / cases that could count). "
        "Generated by `harness/render_results.py` from `results/*.json`; do not edit by hand."
    )
    return "\n".join([*rows, "", note])


def replace_between_markers(text: str, block: str) -> str:
    start, end = text.find(START), text.find(END)
    if start == -1 or end == -1 or end < start:
        raise RenderError(f"the README needs the two marker lines {START} and {END}, in that order")
    return text[: start + len(START)] + "\n" + block + "\n" + text[end:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the 1A results table into the README.")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--readme", type=Path, default=ROOT / "README.md")
    args = parser.parse_args(argv)
    try:
        results = load_results(args.results_dir)
        table = build_table(results, read_costs(args.results_dir / "costs.md"))
        text = args.readme.read_text(encoding="utf-8")
        args.readme.write_text(replace_between_markers(text, table), encoding="utf-8")
    except (RenderError, OSError) as e:
        print(f"error: {e}")
        return 2
    print(f"wrote the results table ({len(results)} result file(s)) to {args.readme}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
