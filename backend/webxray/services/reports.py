"""Investigation report assembled exclusively from persisted records.

Every claim in the report references the finding, evidence, run, or test it
came from. Nothing is summarized by a model.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from webxray.models import (
    Approval,
    BrowserRun,
    Environment,
    Evidence,
    Feature,
    Finding,
    FindingEvidence,
    Investigation,
    Journey,
    Page,
    Project,
    ReproductionTest,
    TestRun,
)

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


async def build_report(db: AsyncSession, inv: Investigation) -> dict[str, Any]:
    env = await db.get(Environment, inv.environment_id)
    project = await db.get(Project, inv.project_id)
    pages = (await db.scalars(select(Page).where(Page.investigation_id == inv.id).order_by(Page.created_at))).all()
    features = (await db.scalars(select(Feature).where(Feature.investigation_id == inv.id).order_by(Feature.name))).all()
    journeys = (await db.scalars(select(Journey).where(Journey.investigation_id == inv.id))).all()
    runs = (await db.scalars(select(BrowserRun).where(BrowserRun.investigation_id == inv.id).order_by(BrowserRun.started_at))).all()
    findings = (await db.scalars(select(Finding).where(Finding.investigation_id == inv.id))).all()
    approvals = (await db.scalars(select(Approval).where(Approval.investigation_id == inv.id))).all()
    tests = (await db.scalars(select(ReproductionTest).where(ReproductionTest.investigation_id == inv.id))).all()

    finding_items = []
    for f in sorted(findings, key=lambda f: (SEVERITY_ORDER.index(f.severity) if f.severity in SEVERITY_ORDER else 9, f.title)):
        ev = (await db.execute(
            select(Evidence.id, Evidence.kind, Evidence.label, Evidence.sha256, FindingEvidence.role)
            .join(FindingEvidence, FindingEvidence.evidence_id == Evidence.id).where(FindingEvidence.finding_id == f.id)
        )).all()
        test = next((t for t in tests if t.finding_id == f.id), None)
        last_run = await db.get(TestRun, test.last_run_id) if test and test.last_run_id else None
        finding_items.append({
            "id": str(f.id), "title": f.title, "severity": f.severity, "classification": f.classification, "kind": f.kind,
            "summary": f.summary, "expected": f.expected, "observed": f.observed, "viewport": f.viewport_name,
            "reproduction": f.reproduction, "evidence_strength": f.evidence_strength,
            "hypotheses": f.hypotheses, "steps_to_reproduce": f.steps_to_reproduce, "recommendation": f.recommendation,
            "evidence": [{"id": str(i), "kind": k, "label": lbl, "sha256": sha, "role": role} for i, k, lbl, sha, role in ev],
            "test": {
                "id": str(test.id), "filename": test.filename, "verification_status": test.verification_status,
                "last_run": {
                    "id": str(last_run.id), "outcome": last_run.outcome, "playwright_status": last_run.playwright_status,
                    "duration_ms": last_run.duration_ms, "finished_at": last_run.finished_at.isoformat() if last_run.finished_at else None,
                } if last_run else None,
            } if test else None,
        })

    s = inv.summary or {}
    confirmed = [f for f in finding_items if f["classification"] == "confirmed_defect"]
    reproduced = [f for f in finding_items if f["test"] and f["test"]["verification_status"] == "reproduced"]
    exec_summary = (
        f"WEB X-RAY investigated {env.origin if env else 'the target'} ({inv.mode} mode) and finished with status "
        f"'{inv.status}'. It discovered {len(pages)} page record(s), executed {len(runs)} journey run(s), and recorded "
        f"{len(finding_items)} finding(s): {len(confirmed)} confirmed defect(s), of which {len(reproduced)} were independently "
        f"reproduced by an executed Playwright test."
    )
    return {
        "investigation": {
            "id": str(inv.id), "status": inv.status, "mode": inv.mode, "goal": inv.goal, "created_at": inv.created_at.isoformat(),
            "started_at": inv.started_at.isoformat() if inv.started_at else None,
            "finished_at": inv.finished_at.isoformat() if inv.finished_at else None,
            "error": inv.error, "blocked_reason": inv.blocked_reason,
        },
        "executive_summary": exec_summary,
        "target": {"project": project.name if project else None, "origin": env.origin if env else None,
                   "verification": env.verification_method if env else None, "viewports": inv.config.get("viewports"),
                   "browser": "Chromium (Playwright 1.63), isolated context per run, egress-proxied"},
        "access": {"auth_state": inv.auth_state, **(s.get("auth") or {}),
                   "approvals": [{"kind": a.kind, "statement": a.statement, "at": a.created_at.isoformat()} for a in approvals]},
        "discovery": {
            "pages": [{"url": p.url, "title": p.title, "status": p.status_code, "classification": p.classification,
                       "auth_state": p.auth_state, "screenshot_id": str(p.screenshot_id) if p.screenshot_id else None} for p in pages],
            "crawl_notes": s.get("crawl_notes", []), "skipped_links": s.get("skipped_links", {}),
        },
        "features": [{"key": f.key, "name": f.name, "status": f.status, "details": f.details} for f in features],
        "journeys": [{
            "name": j.name, "status": j.status,
            "runs": [{"id": str(r.id), "viewport": r.viewport_name, "attempt": r.attempt, "status": r.status,
                      "failure_step": r.failure_step} for r in runs if r.journey_id == j.id],
        } for j in journeys],
        "coverage": {"limitations": s.get("limitations", []), "features": s.get("features", {}),
                     "egress_blocked_requests": s.get("egress_blocked", 0)},
        "findings": finding_items,
    }


def report_markdown(r: dict[str, Any]) -> str:
    inv, t = r["investigation"], r["target"]
    out = [f"# WEB X-RAY investigation report", "",
           f"- Investigation: `{inv['id']}` · status **{inv['status']}** · mode {inv['mode']}",
           f"- Target: {t['origin']} (project: {t['project']}; authorization: {t['verification']})",
           f"- Viewports: {', '.join(t['viewports'] or [])} · {t['browser']}", "",
           "## 1. Executive summary", "", r["executive_summary"], ""]
    acc = r["access"]
    out += ["## 2. Authentication and access", "", f"- Session state: {acc.get('auth_state')}",
            f"- Outcome: {acc.get('status', 'n/a')} — {acc.get('detail', '')}"]
    out += [f"- Approval ({a['kind']}): {a['statement']}" for a in acc.get("approvals", [])]
    out += ["", "## 3. Discovered pages", "", "| Page | Status | Type | Session |", "|---|---|---|---|"]
    out += [f"| {p['url']} | {p['status']} | {p['classification']} | {p['auth_state']} |" for p in r["discovery"]["pages"]]
    out += ["", *[f"- {n}" for n in r["discovery"]["crawl_notes"]], ""]
    out += ["## 4. Features", "", "| Feature | Status |", "|---|---|"]
    out += [f"| {f['name']} | {f['status']} |" for f in r["features"]]
    out += ["", "## 5. Journeys", ""]
    for j in r["journeys"]:
        out.append(f"**{j['name']}** — {j['status']}")
        out += [f"- {x['viewport']} attempt {x['attempt']}: {x['status']}" + (f" (failed at `{x['failure_step']}`)" if x["failure_step"] else "") for x in j["runs"]]
    out += ["", "## 6. Coverage and limitations", "", *[f"- {x}" for x in r["coverage"]["limitations"]], ""]
    out += ["## 7. Findings", ""]
    for i, f in enumerate(r["findings"], 1):
        out += [f"### 7.{i} [{f['severity'].upper()}] {f['title']}", "",
                f"*{f['classification'].replace('_', ' ')} · evidence strength: {f['evidence_strength']} · reproduction: "
                f"{f['reproduction'].get('status')} ({f['reproduction'].get('failed_runs')}/{f['reproduction'].get('total_runs')} runs)*", "",
                f["summary"], ""]
        if f["expected"]:
            out.append(f"- **Expected:** {f['expected']}")
        if f["observed"]:
            out.append(f"- **Observed:** {f['observed']}")
        if f["steps_to_reproduce"]:
            out += ["", "**Steps to reproduce**", "", *[f"{n}. {s}" for n, s in enumerate(f["steps_to_reproduce"], 1)]]
        if f["hypotheses"]:
            out += ["", "**Likely causes (ranked by evidence)**", ""]
            out += [f"- *{h['status'].replace('_', ' ')}, {h['strength']}* — {h['title']}: {h['rationale']}" for h in f["hypotheses"]]
        if f["recommendation"]:
            out += ["", f"**Recommended fix:** {f['recommendation']}"]
        if f["test"]:
            lr = f["test"]["last_run"]
            out += ["", f"**Reproduction test:** `{f['test']['filename']}` — {f['test']['verification_status']}"
                    + (f" (Playwright: {lr['playwright_status']}, {lr['duration_ms']} ms)" if lr else " (not executed)")]
        out += ["", "**Evidence**", "", *[f"- {e['kind']}: {e['label']} (sha256 {e['sha256'][:12]}…)" for e in f["evidence"]], ""]
    out += ["## 8. Next steps", "",
            "- Fix confirmed defects, then re-run their reproduction tests from the finding page; a passing run is recorded as 'not reproduced'.",
            "- Review warnings: they are directly observed but their user impact was not verified.",
            "- Expand coverage for features marked untested."]
    return "\n".join(out) + "\n"
