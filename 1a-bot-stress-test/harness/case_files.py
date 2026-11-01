"""Read Eojin's case files and the dev-user table. Shared by validate_cases.py and make_batches.py.

A case file is one YAML file (see ../cases/README.md). This module only reads; it judges nothing.
"""

import re
from pathlib import Path

import yaml

LANGUAGES = {"en", "ko"}
KINDS = {"attack", "genuine"}
REQUEST_KINDS = {"password", "mfa_reset", "mfa_enrol_device", "mfa_change_phone"}
MFA_REQUEST_KINDS = REQUEST_KINDS - {"password"}
EXPECTED = {"attack": {"BLOCKED", "ESCALATED"}, "genuine": {"COMPLETED", "ESCALATED"}}

# id prefix -> (kind, language). A genuine case may be in either language, so its language is None.
ID_PREFIXES = {"A-EN-": ("attack", "en"), "A-KO-": ("attack", "ko"), "G-": ("genuine", None)}

# Where the four dev users are defined (the 1H dev script is the one source of truth).
USERS_SCRIPT = Path(__file__).resolve().parents[2] / "1h-verified-reset" / "scripts" / "keycloak-dev.sh"

# One row looks like:  "priya.nair|Priya|Nair|555-0101|-|-|yes"   (name|first|last|phone|group|role|has TOTP device)
_USER_ROW = re.compile(r'^\s*"([a-z][a-z0-9.]*)\|[^|]*\|[^|]*\|[^|]*\|([^|]*)\|[^|]*\|(yes|no)"\s*$')


def known_users(script: Path = USERS_SCRIPT) -> dict[str, dict]:
    """username -> {"privileged": bool, "has_device": bool}, read from the dev script."""
    users = {}
    for line in script.read_text(encoding="utf-8").splitlines():
        row = _USER_ROW.match(line)
        if row:
            users[row.group(1)] = {"privileged": row.group(2) == "privileged", "has_device": row.group(3) == "yes"}
    return users


def load_cases(cases_dir: Path) -> tuple[list[dict], list[str]]:
    """Every *.yaml / *.yml file in the folder -> (cases, problems). Each case gets a `_file` key."""
    cases, problems = [], []
    for path in sorted(Path(cases_dir).glob("*.y*ml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError):
            problems.append(f"{path.name}: cannot be read as YAML")
            continue
        if not isinstance(data, dict):
            problems.append(f"{path.name}: must hold one mapping (key: value lines)")
            continue
        cases.append({**data, "_file": path.name})
    return cases, problems
