"""Evidence-grounded diagnosis.

The engine separates three things the product must never blur:

* **Observed failure** — what the browser actually did (step outcome).
* **Hypotheses** — candidate causes, each marked supported / not supported /
  inconclusive *by recorded evidence*, never by plausibility alone.
* **Evidence strength** — derived from reproducibility across repeated runs
  and the directness of the evidence. No percentages are invented.

All logic here is deterministic and unit-testable; nothing calls an AI model.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from webxray.worker.crawler import CrawledPage, path_of
from webxray.worker.journeys.checkout import RunResult

STRENGTH_ORDER = {"strong": 0, "moderate": 1, "limited": 2}
STATUS_ORDER = {"supported": 0, "inconclusive": 1, "not_supported": 2}

SCREEN_WORD = {"desktop": "computer", "tablet": "tablet", "mobile": "phone"}


@dataclass
class EvidenceRef:
    evidence_id: Any
    role: str

    def as_dict(self) -> dict[str, Any]:
        return {"evidence_id": str(self.evidence_id), "role": self.role}


@dataclass
class Hypothesis:
    key: str
    title: str
    status: str  # supported | not_supported | inconclusive
    strength: str  # strong | moderate | limited
    rationale: str
    evidence: list[EvidenceRef] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "title": self.title, "status": self.status, "strength": self.strength,
            "rationale": self.rationale, "evidence": [e.as_dict() for e in self.evidence],
        }


@dataclass
class DiagnosedFinding:
    dedupe_key: str
    kind: str
    classification: str
    severity: str
    title: str
    summary: str
    expected: str | None
    observed: str | None
    page_url: str | None
    viewport_name: str | None
    reproduction: dict[str, Any]
    hypotheses: list[Hypothesis]
    evidence_strength: str
    steps_to_reproduce: list[str]
    recommendation: str | None
    evidence: list[EvidenceRef]
    occurrences: int = 1
    journey_failure: dict[str, Any] | None = None  # data needed for test generation


# --------------------------------------------------------------------------- journeys


def _step_window(run: RunResult, key: str) -> dict[str, list[dict[str, Any]]]:
    return run.step_windows.get(key, {"network": [], "console": [], "page_errors": []})


def _reproducibility(failed: int, attempts: int) -> str:
    if attempts >= 2 and failed == attempts:
        return "reproducible"
    if failed == attempts == 1:
        return "observed_once"
    if 0 < failed < attempts:
        return "intermittent"
    return "not_reproduced"


def diagnose_checkout(runs: list[RunResult], *, journey_name: str = "Checkout") -> list[DiagnosedFinding]:
    by_viewport: dict[str, list[RunResult]] = defaultdict(list)
    for r in runs:
        by_viewport[r.viewport.name].append(r)
    passing_viewports = [v for v, rs in by_viewport.items() if rs and all(r.status == "passed" for r in rs)]

    findings: list[DiagnosedFinding] = []
    for vname, vruns in by_viewport.items():
        failing = [r for r in vruns if r.status != "passed"]
        if not failing:
            continue
        step_key, _ = Counter(r.failure_step for r in failing).most_common(1)[0]
        same = [r for r in failing if r.failure_step == step_key]
        repro = _reproducibility(len(same), len(vruns))
        vp = same[0].viewport
        first_step = same[0].step(step_key)
        assert first_step is not None
        hypotheses = _checkout_hypotheses(same, step_key, by_viewport, passing_viewports)
        hypotheses.sort(key=lambda h: (STATUS_ORDER[h.status], STRENGTH_ORDER[h.strength]))
        top = hypotheses[0] if hypotheses and hypotheses[0].status == "supported" else None

        submit = same[0].step("submit_order")
        observed = first_step.observed
        if submit is not None and step_key != "submit_order" and submit.status in {"failed", "error"}:
            observed += f" Activating it as a user would: {submit.observed}"
        elif submit is not None and submit.status == "skipped":
            observed += " (Order submission was not attempted: not approved for this environment.)"

        control = _control_name(same[0])
        if step_key in {"submit_reachable", "submit_order"}:
            title = f"{journey_name} can't be finished on a {SCREEN_WORD.get(vp.name, vp.label.lower())}: the '{control}' button can't be tapped"
            if not vp.has_touch:
                title = title.replace("taps", "clicks")
        else:
            title = f"{journey_name} stops at “{first_step.name}” on a {SCREEN_WORD.get(vp.name, vp.label.lower())}"

        classification = "confirmed_defect" if repro == "reproducible" else "warning"
        screen = SCREEN_WORD.get(vp.name, vp.label.lower())
        contrast = " and ".join(f"a {SCREEN_WORD.get(v, v)}" for v in passing_viewports) or None
        press = "tap" if vp.has_touch else "click"
        button_step = step_key in {"submit_reachable", "submit_order"}
        if button_step:
            first = f"On a {screen}, visitors can't finish {journey_name.lower()}: when they {press} “{control}”, the order isn't placed."
        else:
            first = f"On a {screen}, {journey_name.lower()} stops at “{first_step.name}”."
        tries = f"We tried {len(vruns)} time{'s' if len(vruns) != 1 else ''} and it failed {'every time' if len(same) == len(vruns) else f'{len(same)} of them'}."
        summary_bits = [first, tries]
        if contrast:
            summary_bits.append(f"On {contrast} it works fine.")
        if top and top.key == "overlay_interception":
            summary_bits.append(f"The reason: another part of the page sits on top of the button, so the {press} lands on that instead.")
        elif top:
            summary_bits.append(f"The most likely reason: {top.title[0].lower() + top.title[1:]}.")
        else:
            summary_bits.append("We couldn't pin down a single cause from the evidence — see the possible causes below.")
        if top and top.key == "overlay_interception" and button_step:
            plain_observed = f"The {press} lands on whatever is covering the button, so nothing happens: no order is sent and no confirmation appears."
        else:
            plain_observed = observed

        evidence: list[EvidenceRef] = []
        for r in same:
            st = r.step(step_key)
            if st:
                for role, eid in st.evidence.items():
                    if eid:
                        evidence.append(EvidenceRef(eid, f"{r.viewport.name}#{r.attempt}:{step_key}:{role}"))
            if submit_r := r.step("submit_order"):
                for role, eid in submit_r.evidence.items():
                    if eid:
                        evidence.append(EvidenceRef(eid, f"{r.viewport.name}#{r.attempt}:submit_order:{role}"))
            for k in ("network_evidence", "console_evidence"):
                if r.observations.get(k):
                    evidence.append(EvidenceRef(r.observations[k], f"{r.viewport.name}#{r.attempt}:{k.split('_')[0]}_log"))
        for v in passing_viewports:
            pr = by_viewport[v][0]
            st = pr.step(step_key)
            if st and st.evidence.get("hit_test"):
                evidence.append(EvidenceRef(st.evidence["hit_test"], f"contrast:{v}:hit_test"))
            if st and st.evidence.get("after"):
                evidence.append(EvidenceRef(st.evidence["after"], f"contrast:{v}:screenshot"))

        recommendation = _recommendation(top, vp.width, control) if top else (
            "Look through the evidence below, make a change, then press “Run the test again” to check it."
        )
        product = path_of(same[0].observations.get("product_url", "") or "") or "a product page"
        device = f"a phone (or a browser window {vp.width}×{vp.height} pixels with touch turned on)" if vp.is_mobile else f"a computer (browser window {vp.width}×{vp.height} pixels)"
        steps = [
            f"Open the site on {device}.",
            "Sign in with a test account.",
            f"Go to {product} and add it to the cart.",
            "Open the cart and go to checkout.",
            "Fill in the checkout form with test details (use the test card shown on the checkout page).",
            f"Scroll down to “{control}” and {press} it.",
            "What should happen: the order confirmation page. What happens instead: " + plain_observed[0].lower() + plain_observed[1:],
        ]
        findings.append(
            DiagnosedFinding(
                dedupe_key=f"journey:checkout:{vname}:{step_key}",
                kind="journey_failure",
                classification=classification,
                severity="critical" if step_key in {"submit_reachable", "submit_order", "begin_checkout"} else "high",
                title=title,
                summary=" ".join(summary_bits),
                expected=(f"{'Tapping' if press == 'tap' else 'Clicking'} “{control}” places the order and shows a confirmation page." if button_step
                          else f"{first_step.expected}, and the order confirmation is shown."),
                observed=plain_observed,
                page_url=None,
                viewport_name=vname,
                reproduction={
                    "status": repro,
                    "failed_runs": len(same),
                    "total_runs": len(vruns),
                    "failing_viewports": [vname],
                    "passing_viewports": passing_viewports,
                    "run_ids": [str(r.run_id) for r in vruns],
                },
                hypotheses=hypotheses,
                evidence_strength=_overall_strength(top, repro),
                steps_to_reproduce=steps,
                recommendation=recommendation,
                evidence=_dedupe(evidence),
                journey_failure={"viewport": vp.as_dict(), "step": step_key, "control": control, "top_hypothesis": top.key if top else None},
            )
        )
    return findings


def _control_name(run: RunResult) -> str:
    ht = run.observations.get("hit_test") or {}
    loc = ht.get("locator") or {}
    return loc.get("name") or loc.get("name_pattern") or "submit control"


def _overall_strength(top: Hypothesis | None, repro: str) -> str:
    if top is None:
        return "limited"
    if repro == "reproducible":
        return top.strength
    return "moderate" if top.strength == "strong" else "limited"


def _checkout_hypotheses(
    failing: list[RunResult],
    step_key: str,
    by_viewport: dict[str, list[RunResult]],
    passing_viewports: list[str],
) -> list[Hypothesis]:
    hyps: list[Hypothesis] = []
    n = len(failing)
    hit_tests = [r.observations.get("hit_test") for r in failing]
    have_hit = [h for h in hit_tests if h]

    # 1) Overlay / interception, decided by the probe tap (real input delivery).
    if have_hit:
        naturals = [h["attempts"][0] for h in have_hit]

        def intercepted(a: dict[str, Any]) -> dict[str, Any] | None:
            probe = a.get("probe") or {}
            if probe.get("installed") and not probe.get("received"):
                return probe.get("interceptor") or {"overlayRoot": probe.get("receivedBy")}
            return None

        covered = [(a, intercepted(a)) for a in naturals if intercepted(a)]
        roots = Counter(((i or {}).get("overlayRoot") or {}).get("selector") for _, i in covered)
        evidence = [
            EvidenceRef(r.step("submit_reachable").evidence.get(k), f"{r.viewport.name}#{r.attempt}:{k}")  # type: ignore[union-attr]
            for r in failing if r.step("submit_reachable")
            for k in ("hit_test", "styles", "dom", "element", "overflow") if r.step("submit_reachable").evidence.get(k)  # type: ignore[union-attr]
        ]
        if covered and len(covered) == len(naturals) and len(roots) == 1:
            root_sel = next(iter(roots))
            sample = covered[0][1] or {}
            styles = sample.get("overlayStyles") or {}
            position = styles.get("position")
            all_positions = all(h.get("covered_at_all_positions") for h in have_hit)
            contrast_ok = []
            for v in passing_viewports:
                ht = by_viewport[v][0].observations.get("hit_test")
                if ht and (ht["attempts"][0].get("probe") or {}).get("received"):
                    contrast_ok.append(by_viewport[v][0].viewport.label)
            strength = "strong" if (n >= 2 and position in {"fixed", "sticky"}) else "moderate"
            method = (covered[0][0].get("probe") or {}).get("method", "tap")
            efp_agrees = all(not a["centerHit"] for a, _ in covered)
            rationale = (
                f"In {len(covered)}/{len(naturals)} failing run(s), a probe {method} at the control's visual center was delivered "
                f"by the browser to <{(sample.get('overlayRoot') or {}).get('tag')}> `{root_sel}` instead of the control. "
                f"That element has position: {position}, z-index: {styles.get('z-index')}, bottom: {styles.get('bottom')}, "
                f"height: {styles.get('height')}. "
            )
            rationale += (
                "document.elementFromPoint agrees. " if efp_agrees else
                "document.elementFromPoint (layout coordinates) disagrees, which happens when the layout viewport differs "
                "from the visible screen (e.g. horizontal overflow); the probe reflects what a user's input actually reaches. "
            )
            rationale += (
                "The control stayed covered at every scroll position tested (including fully scrolled to the bottom), so a user cannot reach it."
                if all_positions else "The control became reachable only at some scroll positions."
            )
            if contrast_ok:
                rationale += f" At {', '.join(contrast_ok)} the same probe reached the control."
            hyps.append(Hypothesis(
                "overlay_interception",
                f"Another part of the page covers the button and catches the tap ({root_sel})",
                "supported", strength, rationale, evidence,
            ))
        elif covered:
            hyps.append(Hypothesis(
                "overlay_interception", "Something on the page may be covering the button", "inconclusive", "limited",
                f"The probe was intercepted in {len(covered)}/{len(naturals)} run(s), by differing elements ({', '.join(str(k) for k in roots)}).",
                evidence,
            ))
        else:
            hyps.append(Hypothesis(
                "overlay_interception", "Something on the page is covering the button", "not_supported", "strong",
                "Probe taps/clicks at the control's visual center reached the control in every failing run.", evidence,
            ))

        widths = [h.get("document_width") or 0 for h in have_hit]
        vw = failing[0].viewport.width
        if any(w > vw + 1 for w in widths):
            hyps.append(Hypothesis(
                "horizontal_overflow", "The page is wider than the screen, which shifts where things are",
                "inconclusive", "limited",
                f"The document was {max(widths)}px wide in a {vw}px viewport. Overflow enlarges the layout viewport on mobile, "
                "which changes where fixed-position elements sit relative to page content. Recorded as a contributing factor; "
                "on its own it does not explain the failure.",
                [e for e in evidence if e.role.endswith(":overflow")],
            ))

        disabled = [a for a in naturals if a.get("disabled")]
        hyps.append(Hypothesis(
            "disabled_control", "The button is switched off (disabled)",
            "supported" if disabled else "not_supported", "strong",
            f"Control was disabled in {len(disabled)}/{len(naturals)} run(s)." if disabled
            else "The control was enabled (no disabled or aria-disabled state) in every failing run.",
        ))
        hidden = [a for a in naturals if not a.get("visible")]
        hyps.append(Hypothesis(
            "control_not_visible", "The button is hidden or invisible",
            "supported" if hidden else "not_supported", "strong",
            f"Control was not visible in {len(hidden)}/{len(naturals)} run(s)." if hidden
            else "The control had non-zero size, visibility: visible and opacity > 0 in every failing run.",
        ))

    # 2) JavaScript exceptions during the failing steps.
    keys = [step_key, "submit_order"] if step_key != "submit_order" else [step_key]
    errs = [(r, e) for r in failing for k in keys for e in _step_window(r, k)["page_errors"]]
    con_errs = [(r, c) for r in failing for k in keys for c in _step_window(r, k)["console"] if c["type"] == "error"]
    con_ev = [EvidenceRef(r.observations.get("console_evidence"), f"{r.viewport.name}#{r.attempt}:console_log") for r in failing if r.observations.get("console_evidence")]
    if errs:
        hyps.append(Hypothesis(
            "javascript_exception", "A script error stops the button from working", "supported",
            "moderate" if len({r.run_id for r, _ in errs}) == n else "limited",
            f"{len(errs)} uncaught exception(s) during the failing step(s), e.g. “{errs[0][1]['message'][:160]}”.", con_ev,
        ))
    else:
        hyps.append(Hypothesis(
            "javascript_exception", "A script error stops the button from working", "not_supported", "moderate",
            f"No uncaught exceptions were recorded during the failing step(s) in {n} run(s)"
            + (f"; {len(con_errs)} console error(s) were logged." if con_errs else "."), con_ev,
        ))

    # 3) Failed or erroring network requests during the failing steps.
    bad = [
        (r, req) for r in failing for k in keys for req in _step_window(r, k)["network"]
        if req.get("same_origin") and ((req.get("status") or 0) >= 400 or (req.get("failure") and "ERR_ABORTED" not in req["failure"]))
    ]
    net_ev = [EvidenceRef(r.observations.get("network_evidence"), f"{r.viewport.name}#{r.attempt}:network_log") for r in failing if r.observations.get("network_evidence")]
    submissions = [r.observations.get("submission") for r in failing if r.observations.get("submission")]
    no_submit = [s for s in submissions if not s.get("submission_requests")]
    if bad:
        sample = bad[0][1]
        hyps.append(Hypothesis(
            "failed_request", "The website's server fails the request", "supported", "moderate",
            f"{len(bad)} same-origin request(s) failed during the failing step(s), e.g. {sample['method']} {urlsplit(sample['url']).path} → {sample.get('status') or sample.get('failure')}.",
            net_ev,
        ))
    else:
        detail = f"No same-origin request returned an error or failed during the failing step(s) in {n} run(s)."
        if submissions and len(no_submit) == len(submissions):
            detail += " After activating the control, no submission request (POST/PUT/PATCH) was sent at all — the action never reached the server."
        hyps.append(Hypothesis("failed_request", "The website's server fails the request", "not_supported", "strong" if submissions else "moderate", detail, net_ev))
    return hyps


def _recommendation(top: Hypothesis, width: int, control: str = "the button") -> str:
    again = " Then press “Run the test again” — it passes once the problem is gone."
    if top.key == "overlay_interception":
        return (
            f"Make sure nothing covers “{control}” on screens {width}px wide or narrower. For example, add empty space at the bottom "
            "of the page as tall as the bar that covers it, or hide that bar during checkout. (For developers: the covering element "
            "and its styles are in the evidence.)" + again
        )
    if top.key == "disabled_control":
        return f"Find out why “{control}” stays switched off on this screen size even after the form is filled in correctly." + again
    if top.key == "control_not_visible":
        return f"Check the styles for this screen size — they hide or squash “{control}”." + again
    if top.key == "javascript_exception":
        return "Fix the script error shown in the console evidence." + again
    if top.key == "failed_request":
        return "Check the website's server logs for the failing request shown in the network evidence (same time)." + again
    return "Look through the evidence, make a change, and run the test again."


def _dedupe(refs: list[EvidenceRef]) -> list[EvidenceRef]:
    seen: set[str] = set()
    out: list[EvidenceRef] = []
    for r in refs:
        key = str(r.evidence_id)
        if r.evidence_id and key not in seen:
            seen.add(key)
            out.append(r)
    return out


# --------------------------------------------------------------------------- page signals


def diagnose_pages(pages: list[CrawledPage]) -> list[DiagnosedFinding]:
    findings: list[DiagnosedFinding] = []

    http: dict[tuple[str, str, int], list[tuple[CrawledPage, dict[str, Any]]]] = defaultdict(list)
    for p in pages:
        for req in p.signals.http_errors:
            path = urlsplit(req["url"]).path or "/"
            http[(req["method"], path, int(req["status"]))].append((p, req))
    explained_console: set[int] = set()
    for (method, path, status), hits in http.items():
        page_urls = sorted({path_of(p.final_url) + (f" ({p.auth_state})" if p.auth_state != "public" else "") for p, _ in hits})
        resource = hits[0][1].get("resource_type", "")
        correlated = []
        for p, _ in hits:
            for c in p.signals.console_errors:
                if str(status) in c["text"] or path in c["text"] or (resource in {"fetch", "xhr"} and "fail" in c["text"].lower()):
                    correlated.append(c["text"])
                    explained_console.add(id(c))
        is_document = resource == "document"
        severity = "medium" if status >= 500 else ("low" if not is_document else "medium")
        evidence = _dedupe(
            [EvidenceRef(p.network_evidence_id, f"network_log:{path_of(p.final_url)}") for p, _ in hits]
            + [EvidenceRef(p.console_evidence_id, f"console_log:{path_of(p.final_url)}") for p, _ in hits if p.console_evidence_id]
            + [EvidenceRef(p.screenshot_id, f"screenshot:{path_of(p.final_url)}") for p, _ in hits[:3]]
        )
        summary = (
            f"{method} {path} returned HTTP {status} on {len(hits)} page load(s) ({', '.join(page_urls[:5])}"
            f"{'…' if len(page_urls) > 5 else ''})."
        )
        if correlated:
            summary += f" The page logged a related console error: “{correlated[0][:200]}”."
        summary += " The failing request is directly observed; its effect on the user-visible workflow was not verified."
        findings.append(DiagnosedFinding(
            dedupe_key=f"http:{method}:{path}:{status}",
            kind="http_error",
            classification="warning",
            severity=severity,
            title=f"Part of the site isn't loading: {path} fails with error {status}",
            summary=summary,
            expected=f"{method} {path} succeeds (2xx/3xx)",
            observed=f"HTTP {status} ({resource or 'request'}) on {len(hits)} page load(s)",
            page_url=hits[0][0].final_url,
            viewport_name="desktop",
            reproduction={"status": "reproducible" if len(hits) >= 2 else "observed_once", "failed_runs": len(hits), "total_runs": len(hits), "pages": page_urls},
            hypotheses=[],
            evidence_strength="strong" if len(hits) >= 2 else "moderate",
            steps_to_reproduce=[f"Open {page_urls[0].split(' ')[0]} with browser devtools open (Network tab).", f"Observe {method} {path} → HTTP {status}."],
            recommendation=f"Check the server/handler for {path}; if the failure is expected, handle it without logging errors and confirm the UI degrades gracefully.",
            evidence=evidence,
            occurrences=len(hits),
        ))

    page_errs: dict[str, list[tuple[CrawledPage, dict[str, Any]]]] = defaultdict(list)
    for p in pages:
        for e in p.signals.page_errors:
            page_errs[e["message"][:200]].append((p, e))
    for msg, hits in page_errs.items():
        urls = sorted({path_of(p.final_url) for p, _ in hits})
        findings.append(DiagnosedFinding(
            dedupe_key=f"pageerror:{msg[:150]}",
            kind="page_error",
            classification="warning",
            severity="medium",
            title=f"A script on the page crashes: {msg[:110]}",
            summary=f"Thrown on {len(hits)} page load(s) ({', '.join(urls[:5])}). Impact on workflows was not verified.",
            expected="No uncaught exceptions",
            observed=msg,
            page_url=hits[0][0].final_url,
            viewport_name="desktop",
            reproduction={"status": "reproducible" if len(hits) >= 2 else "observed_once", "failed_runs": len(hits), "total_runs": len(hits), "pages": urls},
            hypotheses=[],
            evidence_strength="strong" if len(hits) >= 2 else "moderate",
            steps_to_reproduce=[f"Open {urls[0]} with the browser console open."],
            recommendation="Fix the exception at the stack location in the console evidence.",
            evidence=_dedupe([EvidenceRef(p.console_evidence_id, f"console_log:{path_of(p.final_url)}") for p, _ in hits]),
            occurrences=len(hits),
        ))

    console: dict[str, list[tuple[CrawledPage, dict[str, Any]]]] = defaultdict(list)
    for p in pages:
        statuses = {str(r.get("status")) for r in p.signals.http_errors} | (
            {"403"} if p.signals.blocked_requests else set()
        )
        for c in p.signals.console_errors:
            if id(c) in explained_console:
                continue
            # Chromium echoes every failed subresource as a console error; those are
            # already reported (with more detail) as HTTP-error or blocked-request findings.
            m = re.match(r"Failed to load resource: .*status of (\d{3})", c["text"])
            if m and m.group(1) in statuses:
                continue
            console[c["text"][:200]].append((p, c))
    for text, hits in console.items():
        urls = sorted({path_of(p.final_url) for p, _ in hits})
        findings.append(DiagnosedFinding(
            dedupe_key=f"console:{text[:150]}",
            kind="console_error",
            classification="observation",
            severity="low",
            title=f"The page reports an error: {text[:110]}",
            summary=f"Logged on {len(hits)} page load(s) ({', '.join(urls[:5])}).",
            expected="No console errors",
            observed=text,
            page_url=hits[0][0].final_url,
            viewport_name="desktop",
            reproduction={"status": "reproducible" if len(hits) >= 2 else "observed_once", "failed_runs": len(hits), "total_runs": len(hits), "pages": urls},
            hypotheses=[],
            evidence_strength="moderate",
            steps_to_reproduce=[f"Open {urls[0]} with the browser console open."],
            recommendation=None,
            evidence=_dedupe([EvidenceRef(p.console_evidence_id, f"console_log:{path_of(p.final_url)}") for p, _ in hits]),
            occurrences=len(hits),
        ))

    blocked: dict[str, list[tuple[CrawledPage, dict[str, Any]]]] = defaultdict(list)
    for p in pages:
        for b in p.signals.blocked_requests:
            host = urlsplit(b["url"]).hostname or b["url"].split(":")[0]
            blocked[host].append((p, b))
    for host, hits in blocked.items():
        urls = sorted({path_of(p.final_url) for p, _ in hits})
        findings.append(DiagnosedFinding(
            dedupe_key=f"blocked:{host}",
            kind="blocked_request",
            classification="observation",
            severity="info",
            title=f"The page tries to reach a private network address ({host})",
            summary=(
                f"{len(hits)} request(s) to {host} from {', '.join(urls[:5])} were blocked by WEB X-RAY's egress policy "
                f"({hits[0][1].get('reason', 'denied')}). Real users' browsers would attempt this request."
            ),
            expected="Pages reference only public resources",
            observed=f"Request to {hits[0][1].get('url')}",
            page_url=hits[0][0].final_url,
            viewport_name="desktop",
            reproduction={"status": "reproducible" if len(hits) >= 2 else "observed_once", "failed_runs": len(hits), "total_runs": len(hits), "pages": urls},
            hypotheses=[],
            evidence_strength="strong",
            steps_to_reproduce=[f"View the source of {urls[0]} and search for {host}."],
            recommendation="Remove references to internal or link-local addresses from public pages.",
            evidence=_dedupe([EvidenceRef(p.network_evidence_id, f"network_log:{path_of(p.final_url)}") for p, _ in hits]),
            occurrences=len(hits),
        ))
    return findings


# --------------------------------------------------------------------------- layout


def diagnose_layout(runs: list[RunResult]) -> list[DiagnosedFinding]:
    """Horizontal overflow observed during journey runs (measured, not inferred)."""
    by_key: dict[tuple[str, str], list[tuple[RunResult, dict[str, Any]]]] = defaultdict(list)
    totals: Counter[str] = Counter(r.viewport.name for r in runs)
    for r in runs:
        for path, data in (r.observations.get("overflow") or {}).items():
            by_key[(r.viewport.name, path)].append((r, data))
    findings: list[DiagnosedFinding] = []
    for (vname, path), hits in by_key.items():
        r0, d0 = hits[0]
        vp = r0.viewport
        culprits = d0.get("culprits") or []
        names = ", ".join(f"<{c['element']['tag']}> {c['element'].get('selector', '')}".strip() for c in culprits[:4])
        evidence = [
            EvidenceRef(r.step("submit_reachable").evidence.get("overflow"), f"{r.viewport.name}#{r.attempt}:overflow")  # type: ignore[union-attr]
            for r, _ in hits if r.step("submit_reachable") and r.step("submit_reachable").evidence.get("overflow")  # type: ignore[union-attr]
        ] + [
            EvidenceRef(r.step("submit_reachable").evidence.get("after"), f"{r.viewport.name}#{r.attempt}:screenshot")  # type: ignore[union-attr]
            for r, _ in hits[:1] if r.step("submit_reachable")
        ]
        reproducible = len(hits) >= 2 and len(hits) == totals[vname]
        findings.append(DiagnosedFinding(
            dedupe_key=f"overflow:{vname}:{path}",
            kind="layout_overflow",
            classification="confirmed_defect" if reproducible else "warning",
            severity="medium",
            title=f"{path} is too wide for a {SCREEN_WORD.get(vp.name, vp.label.lower())} screen ({d0['documentWidth']}px of content on a {vp.width}px screen)",
            summary=(
                f"Measured in {len(hits)} of {totals[vname]} {vp.label} run(s): the document is {d0['overflowPx']}px wider than the "
                f"viewport, so the page scrolls horizontally and parts of the layout are cut off. Elements extending past the "
                f"viewport edge: {names or 'not identified'}."
            ),
            expected=f"Content fits within {vp.width}px",
            observed=f"Document width {d0['documentWidth']}px",
            page_url=path,
            viewport_name=vname,
            reproduction={"status": "reproducible" if reproducible else "observed_once", "failed_runs": len(hits), "total_runs": totals[vname]},
            hypotheses=[],
            evidence_strength="strong" if reproducible else "moderate",
            steps_to_reproduce=[f"Open {path} at {vp.width}×{vp.height} (mobile emulation).", "Scroll horizontally; content extends past the right edge."],
            recommendation="Let the listed elements shrink (e.g. min-width: 0 / width: 100% on inputs inside flex rows) or wrap at this breakpoint.",
            evidence=_dedupe([e for e in evidence if e.evidence_id]),
            occurrences=len(hits),
        ))
    return findings
