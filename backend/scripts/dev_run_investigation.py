"""Development helper: create an investigation directly in the DB and run it in-process.

Usage: python scripts/dev_run_investigation.py [origin] [--viewports desktop,mobile] [--no-submit]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from webxray.db import dispose_engine, session_scope  # noqa: E402
from webxray.logging_setup import configure_logging  # noqa: E402
from webxray.models import Environment, Finding, Investigation, Organization, Project, ReproductionTest  # noqa: E402
from webxray.schemas import InvestigationConfig  # noqa: E402
from webxray.worker.pipeline import InvestigationRunner  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("origin", nargs="?", default="http://127.0.0.1:4100")
    ap.add_argument("--viewports", default="desktop,mobile")
    ap.add_argument("--no-submit", action="store_true")
    args = ap.parse_args()
    async with session_scope() as s:
        org = Organization(name="Dev org")
        s.add(org)
        await s.flush()
        proj = Project(org_id=org.id, name="Dev project")
        s.add(proj)
        await s.flush()
        env = Environment(org_id=org.id, project_id=proj.id, origin=args.origin, verification_token=secrets.token_hex(16),
                          verification_status="verified", verification_method="operator_allowlist")
        s.add(env)
        await s.flush()
        cfg = InvestigationConfig(viewports=args.viewports.split(","), allow_registration=True,
                                  allow_order_submission=not args.no_submit, max_pages=20)
        inv = Investigation(org_id=org.id, project_id=proj.id, environment_id=env.id, mode="autonomous",
                            goal="dev run", config=cfg.model_dump())
        s.add(inv)
        await s.flush()
        inv_id = inv.id
    print("investigation", inv_id)
    await InvestigationRunner(inv_id).run()
    async with session_scope() as s:
        inv = await s.get(Investigation, inv_id)
        print("STATUS", inv.status, inv.error)
        print(json.dumps(inv.summary, indent=1, default=str)[:4000])
        for f in (await s.scalars(select(Finding).where(Finding.investigation_id == inv_id))).all():
            print(f"- [{f.classification}/{f.severity}] {f.title} | strength={f.evidence_strength} repro={f.reproduction.get('status')} test={f.reproduction.get('test')}")
        for t in (await s.scalars(select(ReproductionTest).where(ReproductionTest.investigation_id == inv_id))).all():
            print("TEST", t.filename, t.verification_status)
    await dispose_engine()


if __name__ == "__main__":
    configure_logging("WARNING")
    asyncio.run(main())
