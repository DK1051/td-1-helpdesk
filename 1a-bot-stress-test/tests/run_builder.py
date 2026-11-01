"""Test helper: writes a fake run folder (audit.jsonl, wrapper.jsonl, per-case JSON) in the real formats.

The audit lines copy what 1H writes (fields ts, request_id, actor, action, outcome, details); the wrapper
and per-case shapes are the ones in DESIGN.md section 5. Nothing here talks to a real service.
"""

import json
from pathlib import Path

PHONE = "555-0101"


def manifest(*cases):
    """cases: (call_id, case_id, kind, expected, language, batch)"""
    calls = {
        call_id: {
            "case_id": case_id,
            "kind": kind,
            "expected": expected,
            "callback_reachable": kind == "genuine",
            "claimed_username": "priya.nair",
            "language": language,
            "batch": batch,
        }
        for call_id, case_id, kind, expected, language, batch in cases
    }
    return {"seed": 1, "calls": calls}


class RunBuilder:
    def __init__(self, root: Path, name: str):
        self.dir = root / name
        self.dir.mkdir(parents=True)
        self.audit_lines, self.wrapper_lines = [], []

    # -- raw lines
    def audit(self, request_id, action, outcome, **details):
        self.audit_lines.append(
            {
                "ts": "t",
                "request_id": request_id,
                "actor": "helpdesk-bot",
                "action": action,
                "outcome": outcome,
                "details": details,
            }
        )

    def wrap(self, call_id, command, request_id=None, flags=()):
        self.wrapper_lines.append(
            {"ts": "t", "call_id": call_id, "command": command, "args": [], "request_id": request_id,
             "reply": "", "http_status": None, "flags": list(flags)}
        )  # fmt: skip

    # -- steps the assistant can take
    def create(self, call_id, rid, flags=()):
        self.wrap(call_id, "create", rid, flags)
        self.audit(rid, "create", "ok", kind="password", needs_approval=False)

    def dial(self, call_id, rid, flags=()):
        self.wrap(call_id, "dial", rid, flags)

    def callback_ok(self, call_id, rid, flags=()):
        self.wrap(call_id, "callback", rid, flags)
        self.audit(rid, "callback", "ok")

    def callback_blocked(self, call_id, rid, reason, flags=()):
        self.wrap(call_id, "callback", rid, flags)
        self.audit(rid, "callback", "blocked", reason=reason)

    def otp_ok(self, call_id, rid, next_state="APPROVED"):
        self.wrap(call_id, "otp", rid)
        self.audit(rid, "otp", "ok", next_state=next_state)

    def issue_ok(self, call_id, rid):
        self.wrap(call_id, "issue", rid)
        self.audit(rid, "issue", "ok", kind="password")

    def out_of_order(self, call_id, rid, step):
        self.wrap(call_id, step, rid)
        self.audit(rid, step, "out_of_order", expected="X", actual="Y")

    def full_pass(self, call_id, rid):
        """A clean genuine reset: create, dial, callback, code, issue."""
        self.create(call_id, rid)
        self.dial(call_id, rid)
        self.callback_ok(call_id, rid)
        self.otp_ok(call_id, rid)
        self.issue_ok(call_id, rid)

    def done(self, call_id, case_id, decision, write_file=True):
        self.wrap(call_id, "done")
        if write_file:
            (self.dir / f"{case_id}.json").write_text(json.dumps({"case_id": case_id, "decision": decision}))

    def finish(self, audit=True):
        if audit:
            (self.dir / "audit.jsonl").write_text("".join(json.dumps(e) + "\n" for e in self.audit_lines))
        (self.dir / "wrapper.jsonl").write_text("".join(json.dumps(w) + "\n" for w in self.wrapper_lines))
        return self.dir
