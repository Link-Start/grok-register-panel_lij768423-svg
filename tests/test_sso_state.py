# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sso_to_auth_json import classify_sso_account_state, parse_sso_line, run_check_sso_state
from webui import sso_state_ops


TOKEN = "e" * 80


def test_classify_matches_risk_gate():
    assert classify_sso_account_state({"denied": True, "found": True, "bot_flag_source": 0}) == "flagged"
    assert classify_sso_account_state({"found": True, "bot_flag_source": 1, "policy": ""}) == "flagged"
    assert classify_sso_account_state({"found": True, "bot_flag_source": 2}) == "flagged"
    assert classify_sso_account_state({"found": True, "bot_flag_source": 0, "policy": "deny", "event": "$login"}) == "flagged"
    assert classify_sso_account_state({"found": True, "bot_flag_source": 0, "policy": "allow"}) == "clean"
    assert classify_sso_account_state({"found": False, "status_code": 403, "error": "cf"}) == "error"
    assert classify_sso_account_state({"found": False, "status_code": 200, "error": ""}) == "unknown"


def test_parse_quarantine_line_keeps_jwt_not_details():
    line = f"risk@example.test----{TOKEN}----botFlagSource=2 policy=deny"
    parsed = sso_state_ops.parse_quarantine_line(line)
    assert parsed is not None
    assert parsed.email == "risk@example.test"
    assert parsed.sso == TOKEN


def test_run_check_sso_state_classifies_and_exports(monkeypatch_inspect=None):
    records = [
        parse_sso_line(f"ok@example.test----{TOKEN}"),
        parse_sso_line(f"bad@example.test----{'f' * 80}"),
    ]
    states = {
        TOKEN: {
            "found": True,
            "bot_flag_source": 0,
            "bot_flag_details": "",
            "policy": "",
            "risk": 0.1,
            "event": "",
            "denied": False,
            "status_code": 200,
            "error": "",
        },
        "f" * 80: {
            "found": True,
            "bot_flag_source": 1,
            "bot_flag_details": "policy=deny,event=$registration",
            "policy": "deny",
            "risk": 0.99,
            "event": "$registration",
            "denied": True,
            "status_code": 200,
            "error": "",
        },
    }

    def fake_inspect(sso, proxy="", log=print, timeout=20):
        return dict(states[sso])

    import sso_to_auth_json as mod

    previous = mod.inspect_sso_account_state
    mod.inspect_sso_account_state = fake_inspect
    try:
        with tempfile.TemporaryDirectory() as temp:
            flagged = Path(temp) / "flagged.jsonl"
            clean = Path(temp) / "clean.txt"
            summary = run_check_sso_state(
                records,
                export=flagged,
                clean_export=clean,
                log=lambda *_args, **_kwargs: None,
            )
            assert summary["total"] == 2
            assert summary["clean_count"] == 1
            assert summary["flagged_count"] == 1
            assert summary["denied_count"] == 1
            assert flagged.read_text(encoding="utf-8").count("\n") == 1
            assert TOKEN in clean.read_text(encoding="utf-8")
            assert "f" * 80 not in flagged.read_text(encoding="utf-8")
    finally:
        mod.inspect_sso_account_state = previous


def test_start_scan_uses_paste_and_never_returns_token():
    import sso_to_auth_json as mod

    def fake_inspect(sso, proxy="", log=print, timeout=20):
        return {
            "found": True,
            "bot_flag_source": 0,
            "bot_flag_details": "",
            "policy": "",
            "risk": None,
            "event": "",
            "denied": False,
            "status_code": 200,
            "error": "",
        }

    previous = mod.inspect_sso_account_state
    previous_dirs = (
        sso_state_ops.LOG_DIR,
        sso_state_ops.REPORT_FILE,
        sso_state_ops.FLAGGED_EXPORT,
        sso_state_ops.CLEAN_EXPORT,
        sso_state_ops.CONFIG_FILE,
    )
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        sso_state_ops.LOG_DIR = root / "log"
        sso_state_ops.REPORT_FILE = sso_state_ops.LOG_DIR / "sso_state_report.json"
        sso_state_ops.FLAGGED_EXPORT = sso_state_ops.LOG_DIR / "sso_flagged.jsonl"
        sso_state_ops.CLEAN_EXPORT = sso_state_ops.LOG_DIR / "sso_clean.txt"
        sso_state_ops.CONFIG_FILE = root / "config.json"
        sso_state_ops.LOG_DIR.mkdir()
        sso_state_ops._cancel.clear()
        with sso_state_ops._lock:
            sso_state_ops._state["running"] = False
            sso_state_ops._state["items"] = []
        mod.inspect_sso_account_state = fake_inspect
        try:
            started = sso_state_ops.start_sso_state_scan(
                source="paste",
                text=f"ok@example.test----{TOKEN}\n",
                delay=0,
            )
            assert started["ok"] is True
            thread = sso_state_ops._thread
            if thread:
                thread.join(timeout=5)
            status = sso_state_ops.sso_state_status()
            dumped = json.dumps(status, ensure_ascii=False)
            assert TOKEN not in dumped
            assert status["summary"]["clean_count"] == 1
            export = sso_state_ops.read_sso_state_export("clean")
            assert export["ok"] is True
            assert TOKEN in export["content"]
        finally:
            mod.inspect_sso_account_state = previous
            (
                sso_state_ops.LOG_DIR,
                sso_state_ops.REPORT_FILE,
                sso_state_ops.FLAGGED_EXPORT,
                sso_state_ops.CLEAN_EXPORT,
                sso_state_ops.CONFIG_FILE,
            ) = previous_dirs


if __name__ == "__main__":
    test_classify_matches_risk_gate()
    test_parse_quarantine_line_keeps_jwt_not_details()
    test_run_check_sso_state_classifies_and_exports()
    test_start_scan_uses_paste_and_never_returns_token()
    print("OK sso state")
