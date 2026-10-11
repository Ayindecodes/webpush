"""Stable, accessible locator specifications.

The journey engine resolves elements through :class:`LocatorSpec` objects and
the test generator renders the *same* specs to TypeScript, so a generated test
targets exactly the element the investigation interacted with.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from playwright.async_api import Error as PlaywrightError, Locator, Page

Strategy = Literal["role", "label", "css"]


@dataclass(frozen=True)
class LocatorSpec:
    strategy: Strategy
    role: str | None = None
    name: str | None = None
    name_pattern: str | None = None  # case-insensitive regex source, used when exact name is unknown
    label: str | None = None
    css: str | None = None
    nth: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LocatorSpec:
        return cls(**data)

    def describe(self) -> str:
        if self.strategy == "role":
            name = self.name if self.name is not None else f"/{self.name_pattern}/i"
            base = f'{self.role} "{name}"'
        elif self.strategy == "label":
            base = f'field labelled "{self.label}"'
        else:
            base = f"element {self.css}"
        return base + (f" (#{self.nth + 1})" if self.nth is not None else "")


def resolve(page: Page, spec: LocatorSpec) -> Locator:
    if spec.strategy == "role":
        assert spec.role
        if spec.name is not None:
            loc = page.get_by_role(spec.role, name=spec.name, exact=True)  # type: ignore[arg-type]
        elif spec.name_pattern is not None:
            loc = page.get_by_role(spec.role, name=re.compile(spec.name_pattern, re.I))  # type: ignore[arg-type]
        else:
            loc = page.get_by_role(spec.role)  # type: ignore[arg-type]
    elif spec.strategy == "label":
        assert spec.label is not None
        loc = page.get_by_label(spec.label, exact=True)
    else:
        assert spec.css
        loc = page.locator(spec.css)
    return loc.nth(spec.nth) if spec.nth is not None else loc


def _ts_str(value: str) -> str:
    # A JSON string literal is a valid TypeScript string literal.
    return json.dumps(value, ensure_ascii=False)


def to_typescript(spec: LocatorSpec, page_var: str = "page") -> str:
    if spec.strategy == "role":
        if spec.name is not None:
            expr = f"{page_var}.getByRole('{spec.role}', {{ name: {_ts_str(spec.name)}, exact: true }})"
        elif spec.name_pattern is not None:
            pattern = spec.name_pattern.replace("/", "\\/")
            expr = f"{page_var}.getByRole('{spec.role}', {{ name: /{pattern}/i }})"
        else:
            expr = f"{page_var}.getByRole('{spec.role}')"
    elif spec.strategy == "label":
        expr = f"{page_var}.getByLabel({_ts_str(spec.label or '')}, {{ exact: true }})"
    else:
        expr = f"{page_var}.locator({_ts_str(spec.css or '')})"
    return expr + (f".nth({spec.nth})" if spec.nth is not None else "")


_ARIA_LINE = re.compile(r'^-\s*(\w+)\s+"((?:[^"\\]|\\.)*)"')


async def exact_role_spec(locator: Locator, fallback_role: str) -> tuple[str, str] | None:
    """Return (role, accessible name) for ``locator`` as computed by Playwright itself."""
    try:
        snap = await locator.aria_snapshot(timeout=3000)
    except PlaywrightError:
        return None
    first = snap.strip().splitlines()[0] if snap.strip() else ""
    m = _ARIA_LINE.match(first.strip())
    if not m:
        return None
    role, name = m.group(1), json.loads(f'"{m.group(2)}"')
    return (role or fallback_role, name)


async def find_by_role(page: Page, roles: list[str], pattern: str) -> LocatorSpec | None:
    """Find the first visible element with one of ``roles`` whose name matches ``pattern``.

    Returns the most specific spec that still resolves to exactly that element.
    """
    rx = re.compile(pattern, re.I)
    for role in roles:
        loc = page.get_by_role(role, name=rx)  # type: ignore[arg-type]
        try:
            count = await loc.count()
        except PlaywrightError:
            continue
        for i in range(min(count, 10)):
            candidate = loc.nth(i)
            try:
                if not await candidate.is_visible():
                    continue
            except PlaywrightError:
                continue
            exact = await exact_role_spec(candidate, role)
            if exact is not None:
                r, name = exact
                spec = LocatorSpec("role", role=r, name=name)
                n = await resolve(page, spec).count()
                if n == 1:
                    return spec
                if n > 1:
                    # Pick the index of our candidate among identical names.
                    handle = await candidate.element_handle()
                    all_matches = resolve(page, spec)
                    for j in range(n):
                        other = await all_matches.nth(j).element_handle()
                        if handle and other and await page.evaluate("([a, b]) => a === b", [handle, other]):
                            return LocatorSpec("role", role=r, name=name, nth=j)
            return LocatorSpec("role", role=role, name_pattern=pattern, nth=i if count > 1 else None)
    return None


async def label_spec(page: Page, label: str, css_fallback: str) -> LocatorSpec:
    if label:
        spec = LocatorSpec("label", label=label)
        try:
            if await resolve(page, spec).count() == 1:
                return spec
        except PlaywrightError:
            pass
    return LocatorSpec("css", css=css_fallback)
