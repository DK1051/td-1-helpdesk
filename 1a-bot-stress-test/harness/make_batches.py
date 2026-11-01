"""Turn the case files into label-free batch files plus the private manifest.

Run from the repo root:
    PYTHONPATH=1a-bot-stress-test python -m harness.make_batches 1a-bot-stress-test/cases 1a-bot-stress-test/batches

Rules: DESIGN.md section 6. A batch file never shows the assistant a case id, kind, expected result,
callback_reachable or notes; only batches/manifest.json knows them, and only api.py and score.py read it.
"""

import argparse
import json
import math
import random
import sys
from pathlib import Path

import yaml

from .case_files import USERS_SCRIPT, known_users, load_cases
from .validate_cases import validate

MAX_PER_FILE = 20
DEFAULT_SEED = 20261101
BATCH_KEYS = ("call_id", "language", "claimed_username", "request_kind", "turns")  # the only keys a batch shows
MANIFEST_KEYS = ("kind", "expected", "callback_reachable", "claimed_username", "language")


class BatchError(Exception):
    pass


def make_batches(cases: list[dict], seed: int = DEFAULT_SEED) -> tuple[dict[str, list[dict]], dict]:
    """cases -> ({"en-1": [batch case, ...], ...}, manifest). Same cases and seed give the same output."""
    if not cases:
        raise BatchError("no cases")
    rng = random.Random(seed)
    batches, calls = {}, {}
    for language in sorted({c["language"] for c in cases}):
        group = sorted((c for c in cases if c["language"] == language), key=lambda c: c["id"])
        attacks = [c for c in group if c["kind"] == "attack"]
        genuine = [c for c in group if c["kind"] == "genuine"]
        rng.shuffle(attacks)
        rng.shuffle(genuine)
        n_files = math.ceil(len(group) / MAX_PER_FILE)
        files = [[] for _ in range(n_files)]
        for i, case in enumerate(attacks + genuine):  # dealt in turn: sizes differ by at most one
            files[i % n_files].append(case)
        for n, file_cases in enumerate(files, start=1):
            name = f"{language}-{n}"
            if {c["kind"] for c in file_cases} != {"attack", "genuine"}:  # R4
                raise BatchError(f"{name} would not hold both attacks and genuine requests")
            rng.shuffle(file_cases)
            batches[name] = file_cases
    call_no = 0
    result = {}
    for name, file_cases in batches.items():
        result[name] = []
        for case in file_cases:
            call_no += 1
            call_id = f"C-{call_no:02d}"
            result[name].append({"call_id": call_id, **{k: case[k] for k in BATCH_KEYS if k != "call_id"}})
            calls[call_id] = {"case_id": case["id"], **{k: case[k] for k in MANIFEST_KEYS}, "batch": name}
    return result, {"seed": seed, "calls": calls}


def write_batches(batches: dict, manifest: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, cases in batches.items():
        text = yaml.safe_dump({"batch": name, "cases": cases}, allow_unicode=True, sort_keys=False)
        (out_dir / f"{name}.yaml").write_text(text, encoding="utf-8")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Make the label-free 1A batch files and the manifest.")
    parser.add_argument("cases_dir", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--users-script", type=Path, default=USERS_SCRIPT)
    args = parser.parse_args(argv)

    _, errors, warnings = validate(args.cases_dir, known_users(args.users_script))
    for message in warnings:
        print(f"WARNING: {message}")
    if errors:
        print("\n".join(f"ERROR: {m}" for m in errors))
        print("Fix the case files first (python -m harness.validate_cases).")
        return 1
    try:
        batches, manifest = make_batches(load_cases(args.cases_dir)[0], args.seed)
    except BatchError as e:
        print(f"ERROR: {e}")
        return 1
    write_batches(batches, manifest, args.out_dir)
    print(f"wrote {len(batches)} batch file(s) and manifest.json to {args.out_dir} (seed {args.seed})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
