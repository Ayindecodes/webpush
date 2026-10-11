"""Playwright (TypeScript) reproduction test generation.

Tests are rendered from the *same* locator specs the journey engine used, so
the test exercises exactly what the investigation observed. Credentials are
read from environment variables at run time and never embedded in source.

Assertion messages carry markers the runner uses to classify outcomes:

* ``[WEBXRAY-PRECONDITION]`` — setup failed; the run is inconclusive.
* ``[WEBXRAY-DEFECT]`` — the expected behaviour did not happen; the defect
  is reproduced.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from webxray.worker.journeys.checkout import CHECKOUT_VALUES, PAYMENT_PURPOSES
from webxray.worker.locators import LocatorSpec, to_typescript

DEFECT_MARKER = "[WEBXRAY-DEFECT]"
PRECONDITION_MARKER = "[WEBXRAY-PRECONDITION]"


def _js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _loc(spec: dict[str, Any] | None) -> str:
    if not spec:
        raise ValueError("journey definition is missing a resolved locator")
    return to_typescript(LocatorSpec.from_dict(spec))


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "reproduction"


def generate_checkout_test(
    *,
    finding_title: str,
    investigation_id: str,
    origin: str,
    viewport: dict[str, Any],
    user_agent: str,
    definition: dict[str, Any],
    auth: dict[str, Any],
) -> tuple[str, str]:
    resolved = (definition.get("resolved") or {}).get(viewport["name"]) or {}
    submit = resolved.get("submit")
    control_name = (submit or {}).get("name") or "the submit control"
    product_path = definition["product_path"]
    is_touch = bool(viewport.get("has_touch"))
    vp_label = f"{viewport['label']} ({viewport['width']}×{viewport['height']})"

    if not auth.get("login_path") or not auth.get("username_field") or not auth.get("password_field") or not auth.get("submit"):
        raise ValueError("journey has no recorded login flow; cannot generate an authenticated test")

    fill_lines: list[str] = []
    for f in resolved.get("fields", []):
        loc = _loc(f["locator"])
        purpose = f["purpose"]
        if f["action"] == "keep":
            continue
        if f["action"] == "select":
            fill_lines.append(f"      await {loc}.selectOption({_js(f['value'])});")
            continue
        value = CHECKOUT_VALUES.get(purpose, "WEBXRAY")
        if purpose == "email":
            value = "webxray-checkout@example.test"
        if purpose in PAYMENT_PURPOSES:
            fill_lines.append(f"      if (SUBMIT_ORDER) await {loc}.fill({_js(value)}); // sandbox test card data")
        else:
            fill_lines.append(f"      await {loc}.fill({_js(value)});")
    fills = "\n".join(fill_lines) or "      // No fillable fields were recorded."

    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    source = f"""// WEB X-RAY reproduction test
// Finding:        {finding_title}
// Investigation:  {investigation_id}
// Generated:      {now}
//
// This file was generated from recorded browser evidence. It is NOT a verified
// result by itself — WEB X-RAY marks a finding as reproduced only after running
// this test and observing the {DEFECT_MARKER} assertion fail.
//
// Run it yourself:
//   WEBXRAY_BASE_URL={origin} \\
//   WEBXRAY_TEST_EMAIL=<test account email> WEBXRAY_TEST_PASSWORD=<test account password> \\
//   npx playwright test {_slug(finding_title)}.spec.ts
// Set WEBXRAY_ALLOW_ORDER_SUBMISSION=1 only against a sandbox payment environment.
import {{ test, expect, type Locator, type Page }} from '@playwright/test';

const BASE_URL = process.env.WEBXRAY_BASE_URL ?? {_js(origin)};
const EMAIL = process.env.WEBXRAY_TEST_EMAIL ?? '';
const PASSWORD = process.env.WEBXRAY_TEST_PASSWORD ?? '';
const SUBMIT_ORDER = process.env.WEBXRAY_ALLOW_ORDER_SUBMISSION === '1';
const TOUCH = {str(is_touch).lower()};
const url = (path: string) => new URL(path, BASE_URL).toString();

test.use({{
  viewport: {{ width: {viewport['width']}, height: {viewport['height']} }},
  deviceScaleFactor: {viewport.get('device_scale_factor', 1)},
  isMobile: {str(bool(viewport.get('is_mobile'))).lower()},
  hasTouch: {str(is_touch).lower()},
  userAgent: {_js(user_agent)},
}});

/**
 * Sends a real tap/click at the control's visual center and reports which element the
 * browser delivered it to. A capture-phase listener cancels the event, so the probe has
 * no side effects. Coordinates are converted to the visual viewport, which is what
 * Playwright's touchscreen/mouse use.
 */
async function probeCenter(page: Page, control: Locator) {{
  const at = await control.evaluate((el) => {{
    const r = el.getBoundingClientRect();
    const vv = window.visualViewport ?? {{ offsetLeft: 0, offsetTop: 0, scale: 1 }};
    const events: EventTarget[] = [];
    const types = ['pointerdown', 'mousedown', 'touchstart', 'pointerup', 'mouseup', 'touchend', 'click'];
    const handler = (e: Event) => {{
      if (e.target) events.push(e.target);
      e.preventDefault();
      e.stopImmediatePropagation();
    }};
    for (const t of types) window.addEventListener(t, handler, {{ capture: true, passive: false }});
    (window as any).__wxProbe = {{ el, events, types, handler }};
    return {{
      x: Math.round((r.left + r.width / 2 - vv.offsetLeft) * vv.scale),
      y: Math.round((r.top + r.height / 2 - vv.offsetTop) * vv.scale),
    }};
  }});
  if (TOUCH) await page.touchscreen.tap(at.x, at.y);
  else await page.mouse.click(at.x, at.y);
  const result = await page.evaluate(() => {{
    const p = (window as any).__wxProbe;
    for (const t of p.types) window.removeEventListener(t, p.handler, {{ capture: true }});
    delete (window as any).__wxProbe;
    const first = p.events.find((t: any) => t && t.nodeType === 1) as Element | undefined;
    if (!first) return {{ received: false, receivedBy: 'nothing (no input event was delivered)' }};
    let root: Element | null = first;
    while (root && root !== document.body) {{
      const pos = getComputedStyle(root).position;
      if (pos === 'fixed' || pos === 'sticky' || pos === 'absolute') break;
      root = root.parentElement;
    }}
    const node = root && root !== document.body ? root : first;
    const describe = (n: Element) =>
      `<${{n.tagName.toLowerCase()}}${{n.id ? '#' + n.id : ''}}${{[...n.classList].map((c) => '.' + c).join('')}}>`;
    return {{ received: first === p.el || p.el.contains(first), receivedBy: describe(node) }};
  }});
  return {{ ...at, ...result }};
}}

test({_js(f"{control_name} is reachable and checkout completes on {vp_label}")}, async ({{ page }}) => {{
  test.skip(!EMAIL || !PASSWORD, 'Set WEBXRAY_TEST_EMAIL and WEBXRAY_TEST_PASSWORD for the designated test account.');

  await test.step('Log in with the designated test account', async () => {{
    await page.goto(url({_js(auth['login_path'])}));
    await {_loc(auth['username_field'])}.fill(EMAIL);
    await {_loc(auth['password_field'])}.fill(PASSWORD);
    await {_loc(auth['submit'])}.click();
    await expect({_loc(auth['indicator'])}, '{PRECONDITION_MARKER} login must succeed').toBeVisible();
  }});

  await test.step('Start from an empty cart', async () => {{
    await page.goto(url({_js(definition.get('cart_path') or '/cart')}));
    for (let i = 0; i < 10; i++) {{
      const remove = page.getByRole('button', {{ name: /^\\s*remove\\b/i }}).first();
      if (!(await remove.isVisible().catch(() => false))) break;
      await remove.click();
      await page.waitForLoadState('domcontentloaded');
    }}
  }});

  await test.step('Add a product to the cart', async () => {{
    await page.goto(url({_js(product_path)}));
    await {_loc(resolved.get('add_to_cart'))}.click();
    await expect(page.locator('body'), '{PRECONDITION_MARKER} item must be added to the cart').toContainText(/added to (your )?(cart|bag|basket)/i);
  }});

  await test.step('Open the cart and begin checkout', async () => {{
    await {_loc(resolved.get('cart_link'))}.click();
    await {_loc(resolved.get('checkout_entry'))}.click();
    await expect(page, '{PRECONDITION_MARKER} checkout page must open').toHaveURL(/{re.escape(definition.get('checkout_path') or '/checkout').replace('/', '\\/')}/);
  }});

  await test.step('Fill the checkout form with test data', async () => {{
{fills}
  }});

  const control = {_loc(submit)};
  await test.step({_js(f"{control_name} receives a {'tap' if is_touch else 'click'} at its visual center")}, async () => {{
    await expect(control, '{PRECONDITION_MARKER} control must exist and be enabled').toBeEnabled();
    await control.scrollIntoViewIfNeeded();
    const probe = await probeCenter(page, control);
    expect(probe.received, `{DEFECT_MARKER} a {'tap' if is_touch else 'click'} at the center of {control_name} (${{probe.x}}, ${{probe.y}}) is delivered to ${{probe.receivedBy}} instead of the control`).toBe(true);
  }});

  if (SUBMIT_ORDER) {{
    await test.step('Submitting the order shows the confirmation', async () => {{
      await control.{'tap' if is_touch else 'click'}();
      await expect(page.locator('body'), '{DEFECT_MARKER} order confirmation must appear').toContainText(/order (is |has been )?(confirmed|placed|complete)|thank you/i, {{ timeout: 10_000 }});
    }});
  }}
}});
"""
    filename = f"{_slug(finding_title)}.spec.ts"
    return filename, source


def source_sha256(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()
