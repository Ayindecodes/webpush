"""Execute a generated Playwright test in an isolated subprocess.

* The subprocess receives a minimal environment: no database URL, no secret
  keys, no worker credentials — only what the test needs.
* Test-account credentials are injected as environment variables for the
  duration of the run and are redacted from the captured output.
* The test's browser is forced through a fresh egress proxy with the same
  destination policy as investigations.
* The finding is marked reproduced only when the ``[WEBXRAY-DEFECT]``
  assertion is what failed.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from webxray.config import get_settings
from webxray.security.crypto import TestAccountSecret
from webxray.security.redaction import Redactor
from webxray.security.target_policy import EgressPolicy
from webxray.worker.egress_proxy import EgressProxy
from webxray.worker.testgen import DEFECT_MARKER, PRECONDITION_MARKER

RUN_TIMEOUT_S = 240
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PASSTHROUGH_ENV = ["PATH", "SYSTEMROOT", "SystemRoot", "WINDIR", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA",
                    "USERPROFILE", "HOME", "PLAYWRIGHT_BROWSERS_PATH", "COMSPEC", "PATHEXT"]


@dataclass
class TestExecution:
    __test__ = False
    playwright_status: str | None
    outcome: str  # reproduced | not_reproduced | inconclusive
    exit_code: int | None
    duration_ms: int
    error_message: str | None
    output: str
    egress_denied: list[str]


def _collect_tests(suite: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in suite.get("specs", []):
        for t in spec.get("tests", []):
            out.append({"title": spec.get("title"), **t})
    for child in suite.get("suites", []):
        out.extend(_collect_tests(child))
    return out


def classify_report(report: dict[str, Any]) -> tuple[str | None, str, str | None]:
    """Return (playwright_status, outcome, error_message) from a JSON report."""
    tests = [t for s in report.get("suites", []) for t in _collect_tests(s)]
    if not tests:
        errors = report.get("errors") or []
        msg = errors[0].get("message") if errors else "No tests were found in the report."
        return None, "inconclusive", msg
    results = tests[0].get("results") or []
    if not results:
        return None, "inconclusive", "Test did not produce a result."
    result = results[-1]
    status = result.get("status")
    errors = result.get("errors") or ([result["error"]] if result.get("error") else [])
    message = ANSI.sub("", "\n".join(e.get("message", "") for e in errors)).strip() or None
    if status == "passed":
        return status, "not_reproduced", None
    if status in {"failed", "timedOut"} and message and DEFECT_MARKER in message:
        return status, "reproduced", message
    if status == "skipped":
        return status, "inconclusive", "Test was skipped (missing credentials or precondition)."
    if message and PRECONDITION_MARKER in message:
        return status, "inconclusive", "A precondition failed before the defect assertion: " + message
    return status, "inconclusive", message or f"Test ended with status {status}."


async def execute_test(
    *,
    filename: str,
    source: str,
    origin: str,
    secret: TestAccountSecret | None,
    allow_order_submission: bool,
    policy: EgressPolicy,
) -> TestExecution:
    settings = get_settings()
    runner = settings.runner_dir.resolve()
    cli = runner / "node_modules" / "@playwright" / "test" / "cli.js"
    if not cli.exists():
        raise RuntimeError(f"Playwright test runner is not installed at {runner} (run `npm install` there).")
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is required to execute generated tests.")

    run_dir = runner / ".runs" / uuid.uuid4().hex
    run_dir.mkdir(parents=True)
    redactor = Redactor([secret.password, secret.username] if secret else [])
    proxy = EgressProxy(policy, byte_budget=200 * 1024 * 1024)
    await proxy.start()
    try:
        (run_dir / filename).write_text(source, encoding="utf-8")
        config = {
            "testDir": ".",
            "testMatch": [filename],
            "timeout": 120_000,
            "retries": 0,
            "workers": 1,
            "reporter": [["json", {"outputFile": "report.json"}], ["line"]],
            "outputDir": "output",
            "use": {
                "headless": True,
                "proxy": {"server": proxy.server_url, "username": proxy.username, "password": proxy.password},
                "trace": "off",
                "video": "off",
                "screenshot": "off",
            },
        }
        (run_dir / "playwright.config.json").write_text(json.dumps(config), encoding="utf-8")
        (run_dir / "playwright.config.mjs").write_text(
            "import fs from 'node:fs';\n"
            "export default JSON.parse(fs.readFileSync(new URL('./playwright.config.json', import.meta.url)));\n",
            encoding="utf-8",
        )
        env = {k: os.environ[k] for k in _PASSTHROUGH_ENV if k in os.environ}
        env.update({
            "WEBXRAY_BASE_URL": origin,
            "WEBXRAY_ALLOW_ORDER_SUBMISSION": "1" if allow_order_submission else "0",
            "CI": "1",
            "FORCE_COLOR": "0",
        })
        if secret:
            env["WEBXRAY_TEST_EMAIL"] = secret.username
            env["WEBXRAY_TEST_PASSWORD"] = secret.password

        t0 = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            node, str(cli), "test", "--config", str(run_dir / "playwright.config.mjs"),
            cwd=str(run_dir), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            **({"creationflags": 0x08000000} if sys.platform == "win32" else {}),  # CREATE_NO_WINDOW
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), RUN_TIMEOUT_S)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return TestExecution(None, "inconclusive", None, int((time.monotonic() - t0) * 1000),
                                 f"Test run exceeded {RUN_TIMEOUT_S}s and was terminated.", "", [])
        duration_ms = int((time.monotonic() - t0) * 1000)
        output = redactor.text(ANSI.sub("", stdout.decode("utf-8", "replace")))[-20000:]
        report_path = run_dir / "report.json"
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            pw_status, outcome, message = classify_report(report)
        else:
            pw_status, outcome, message = None, "inconclusive", "Playwright did not write a report."
        return TestExecution(
            playwright_status=pw_status,
            outcome=outcome,
            exit_code=proc.returncode,
            duration_ms=duration_ms,
            error_message=redactor.text(message) if message else None,
            output=output,
            egress_denied=[f"{d.host}:{d.port} — {d.reason}" for d in proxy.stats.denied],
        )
    finally:
        await proxy.stop()
        shutil.rmtree(run_dir, ignore_errors=True)
