"""Northwind Supply — WEB X-RAY's controlled benchmark e-commerce application.

This app exists so WEB X-RAY can be evaluated against *known* defects. The
defects are deliberate and catalogued in ``defects.json``; each one can be
switched off with an environment flag so fix verification can be exercised.

Run:  python -m uvicorn app:app --app-dir demo-shop --port 4100

Flags:
  DEMO_FIX_CHECKOUT_OVERLAY=1   remove the mobile checkout overlay defect (D1)
  DEMO_FIX_PHONE_VALIDATION=1   remove the profile phone validation defect (D2)
  DEMO_FIX_RECOMMENDATIONS=1    make the recommendations API succeed (D3)
  DEMO_VERIFICATION_TOKEN=...   serve this token at /.well-known/webxray-verification.txt
  DEMO_ALLOW_RESET=1            enable POST /__demo/reset (used by automated tests)
"""

from __future__ import annotations

import html
import os
import re
import secrets
import threading
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response


_RUNTIME_FLAGS: dict[str, bool] = {}


def _flag(name: str) -> bool:
    if name in _RUNTIME_FLAGS:
        return _RUNTIME_FLAGS[name]
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


PRODUCTS: dict[str, dict[str, Any]] = {
    "field-notebook": {"name": "Field Notebook", "price": 1400, "blurb": "Dot-grid, 120 pages, lay-flat binding."},
    "brass-pen": {"name": "Brass Pen", "price": 3200, "blurb": "Machined brass body, refillable."},
    "canvas-tote": {"name": "Canvas Tote", "price": 2600, "blurb": "Heavyweight 16oz canvas with inner pocket."},
    "desk-lamp": {"name": "Desk Lamp", "price": 8900, "blurb": "Dimmable warm LED, weighted base."},
}

TEST_CARD_APPROVED = "4242424242424242"
TEST_CARD_DECLINED = "4000000000000002"


@dataclass
class User:
    id: int
    name: str
    email: str
    password: str
    phone: str = ""
    onboarding_step: int = 1  # 1, 2, then 3 = complete
    interests: list[str] = field(default_factory=list)
    country: str = ""


@dataclass
class Session:
    user_id: int | None = None
    cart: dict[str, int] = field(default_factory=dict)


@dataclass
class Order:
    id: int
    user_id: int
    items: dict[str, int]
    total: int


class Store:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.users: dict[int, User] = {}
        self.sessions: dict[str, Session] = {}
        self.orders: dict[int, Order] = {}
        self._next_user = 1
        self._next_order = 1000

    def reset(self) -> None:
        self.__init__()

    def user_by_email(self, email: str) -> User | None:
        return next((u for u in self.users.values() if u.email == email.lower()), None)

    def add_user(self, name: str, email: str, password: str) -> User:
        with self.lock:
            user = User(self._next_user, name, email.lower(), password)
            self.users[user.id] = user
            self._next_user += 1
            return user

    def add_order(self, user_id: int, items: dict[str, int]) -> Order:
        with self.lock:
            total = sum(PRODUCTS[s]["price"] * q for s, q in items.items())
            order = Order(self._next_order, user_id, dict(items), total)
            self.orders[order.id] = order
            self._next_order += 1
            return order


store = Store()
app = FastAPI(title="Northwind Supply (WEB X-RAY benchmark)", docs_url=None, redoc_url=None, openapi_url=None)

SESSION_COOKIE = "nw_session"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --------------------------------------------------------------------------- helpers


def e(value: object) -> str:
    return html.escape(str(value), quote=True)


def money(cents: int) -> str:
    return f"${cents / 100:.2f}"


def get_session(request: Request) -> tuple[str, Session]:
    token = request.cookies.get(SESSION_COOKIE)
    if token and token in store.sessions:
        return token, store.sessions[token]
    token = secrets.token_urlsafe(24)
    store.sessions[token] = Session()
    return token, store.sessions[token]


def current_user(sess: Session) -> User | None:
    return store.users.get(sess.user_id) if sess.user_id else None


def with_cookie(resp: Response, token: str) -> Response:
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", path="/")
    return resp


STYLES = """
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#1d1d1f;background:#fafaf7;padding-bottom:24px}
a{color:#0b5cad}
header.site{display:flex;flex-wrap:wrap;align-items:center;gap:12px 20px;padding:14px 24px;border-bottom:1px solid #e3e3dc;background:#fff}
header.site .brand{font-weight:700;text-decoration:none;color:#1d1d1f;margin-right:auto}
header.site nav{display:flex;flex-wrap:wrap;gap:14px}
main{max-width:880px;margin:0 auto;padding:24px}
h1{font-size:28px;margin:0 0 16px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px}
.card{background:#fff;border:1px solid #e3e3dc;border-radius:8px;padding:16px}
.btn{display:inline-block;border:0;border-radius:6px;padding:12px 18px;font:inherit;font-weight:600;cursor:pointer;text-decoration:none;background:#e9e9e2;color:#1d1d1f}
.btn.primary{background:#14532d;color:#fff}
.btn.block{display:block;width:100%;text-align:center}
form .field{display:flex;flex-direction:column;gap:4px;margin-bottom:14px}
form input,form select{font:inherit;padding:10px;border:1px solid #c9c9c0;border-radius:6px;background:#fff;min-width:0;width:100%}
form input[type=checkbox],form input[type=radio]{width:auto}
.errors{border:1px solid #b42318;background:#fff4f2;color:#7a1a12;padding:10px 14px;border-radius:6px;margin-bottom:16px}
.notice{border:1px solid #c9c9c0;background:#fff;padding:10px 14px;border-radius:6px;margin-bottom:16px}
.row{display:flex;gap:12px}.row>.field{flex:1}
table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #e3e3dc;text-align:left}
footer.site{max-width:880px;margin:24px auto;padding:0 24px;color:#6b6b63;font-size:14px}
.help-bar{background:#1d1d1f;color:#fff;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;gap:12px;max-width:880px;margin:24px auto 0;border-radius:8px}
.help-bar a{color:#fff;font-weight:600}
@media (max-width:640px){
  header.site{padding:12px 16px}
  main{padding:16px}
  /* D1: on small screens the checkout help bar becomes a fixed overlay. */
  .help-bar{position:fixed;left:0;right:0;bottom:0;height:92px;margin:0;border-radius:0;z-index:40}
}
"""

FOOTER = '<footer class="site">Northwind Supply is a benchmark application for WEB X-RAY. Payments use the SimPay sandbox.</footer>'

FIXED_OVERLAY_STYLES = "@media (max-width:640px){body.has-help-bar{padding-bottom:132px}}"


def layout(request: Request, sess: Session, title: str, body: str, *, body_class: str = "", extra_head: str = "", show_footer: bool = True) -> str:
    user = current_user(sess)
    count = sum(sess.cart.values())
    if user:
        account = (
            '<a href="/account/profile">Account</a><a href="/orders">Orders</a>'
            '<a href="/logout">Log out</a>'
        )
    else:
        account = '<a href="/login">Log in</a><a href="/register">Create account</a>'
    fix = FIXED_OVERLAY_STYLES if _flag("DEMO_FIX_CHECKOUT_OVERLAY") else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Small-batch stationery and desk goods from Northwind Supply.">
<title>{e(title)} · Northwind Supply</title>
<style>{STYLES}{fix}</style>{extra_head}
</head><body class="{e(body_class)}">
<header class="site"><a class="brand" href="/">Northwind Supply</a>
<nav aria-label="Primary"><a href="/products">Shop</a><a href="/help">Help</a><a href="/about">About</a>
<a href="/cart">Cart (<span id="cart-count">{count}</span>)</a>{account}</nav></header>
<main>{body}</main>
{FOOTER if show_footer else ""}
</body></html>"""


def page(request: Request, title: str, body: str, *, status: int = 200, body_class: str = "", extra_head: str = "", show_footer: bool = True) -> HTMLResponse:
    token, sess = get_session(request)
    resp = HTMLResponse(layout(request, sess, title, body, body_class=body_class, extra_head=extra_head, show_footer=show_footer), status_code=status)
    with_cookie(resp, token)
    return resp


def redirect(request: Request, url: str) -> Response:
    token, _ = get_session(request)
    return with_cookie(RedirectResponse(url, status_code=303), token)


def errors_block(errors: list[str]) -> str:
    if not errors:
        return ""
    items = "".join(f"<li>{e(x)}</li>" for x in errors)
    return f'<div class="errors" role="alert"><strong>Please fix the following:</strong><ul>{items}</ul></div>'


def require_onboarded(request: Request) -> Response | None:
    _, sess = get_session(request)
    user = current_user(sess)
    if user is None:
        return redirect(request, f"/login?next={request.url.path}")
    if user.onboarding_step < 3:
        return redirect(request, "/onboarding")
    return None


RECOMMENDATIONS_SCRIPT = """
<script>
fetch('/api/recommendations').then(function (r) {
  if (!r.ok) throw new Error('Recommendations request failed with HTTP ' + r.status);
  return r.json();
}).then(function (data) {
  var el = document.getElementById('recs');
  if (el) el.textContent = 'Recommended: ' + data.items.join(', ');
}).catch(function (err) {
  console.error('[recommendations] ' + err.message);
  var el = document.getElementById('recs');
  if (el) el.textContent = 'Recommendations are unavailable right now.';
});
</script>"""


# --------------------------------------------------------------------------- public pages


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> Response:
    cards = "".join(
        f'<div class="card"><h2 style="font-size:18px;margin:0 0 6px"><a href="/products/{slug}">{e(p["name"])}</a></h2>'
        f'<p style="margin:0">{money(p["price"])}</p></div>'
        for slug, p in PRODUCTS.items()
    )
    body = f"""<h1>Tools for considered work</h1>
<p>Small-batch stationery and desk goods.</p>
<p><a class="btn primary" href="/products">Browse the shop</a></p>
<h2 style="font-size:20px">Featured</h2><div class="grid">{cards}</div>
<p id="recs" aria-live="polite" style="margin-top:24px;color:#6b6b63">Loading recommendations…</p>
{RECOMMENDATIONS_SCRIPT}"""
    return page(request, "Home", body)


@app.get("/products", response_class=HTMLResponse)
def products(request: Request, sort: str = "featured") -> Response:
    items = list(PRODUCTS.items())
    if sort == "price":
        items.sort(key=lambda kv: kv[1]["price"])
    elif sort == "name":
        items.sort(key=lambda kv: kv[1]["name"])
    cards = "".join(
        f'<div class="card"><h2 style="font-size:18px;margin:0 0 6px"><a href="/products/{slug}">{e(p["name"])}</a></h2>'
        f'<p style="margin:0 0 6px">{e(p["blurb"])}</p><strong>{money(p["price"])}</strong></div>'
        for slug, p in items
    )
    body = f"""<h1>Shop</h1>
<p>Sort: <a href="/products?sort=featured">Featured</a> · <a href="/products?sort=price">Price</a> ·
<a href="/products?sort=name">Name</a> · <a href="/products?sort=price&utm_source=newsletter">Newsletter picks</a></p>
<div class="grid">{cards}</div>"""
    return page(request, "Shop", body)


@app.get("/products/{slug}", response_class=HTMLResponse)
def product(request: Request, slug: str) -> Response:
    p = PRODUCTS.get(slug)
    if p is None:
        return page(request, "Not found", "<h1>Product not found</h1>", status=404)
    body = f"""<p><a href="/products">← Back to shop</a></p>
<h1>{e(p["name"])}</h1>
<p>{e(p["blurb"])}</p>
<p style="font-size:22px"><strong>{money(p["price"])}</strong></p>
<button type="button" class="btn primary" id="add-to-cart" data-slug="{e(slug)}">Add to cart</button>
<p id="cart-status" role="status" aria-live="polite"></p>
<p id="recs" aria-live="polite" style="color:#6b6b63">Loading recommendations…</p>
<script>
document.getElementById('add-to-cart').addEventListener('click', function (ev) {{
  var btn = ev.currentTarget;
  btn.disabled = true;
  fetch('/cart/add', {{method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{slug: btn.dataset.slug}})}})
    .then(function (r) {{ if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); }})
    .then(function (data) {{
      document.getElementById('cart-count').textContent = data.count;
      document.getElementById('cart-status').textContent = 'Added to cart. Your cart has ' + data.count + ' item(s).';
    }})
    .catch(function (err) {{ document.getElementById('cart-status').textContent = 'Could not add to cart: ' + err.message; }})
    .finally(function () {{ btn.disabled = false; }});
}});
</script>
{RECOMMENDATIONS_SCRIPT}"""
    return page(request, p["name"], body)


@app.get("/help", response_class=HTMLResponse)
def help_page(request: Request) -> Response:
    body = """<h1>Help</h1><p>Orders ship within two business days. Returns are accepted for 30 days.</p>
<p>Read our <a href="/journal?page=1">journal</a> for product stories.</p>"""
    return page(request, "Help", body)


@app.get("/journal", response_class=HTMLResponse)
def journal(request: Request, n: int = Query(1, alias="page", ge=1, le=1_000_000)) -> Response:
    # Unbounded pagination: a crawl trap used to verify crawl limits.
    body = f"""<h1>Journal — page {n}</h1><p>Entry {n}: notes on paper weights and ink.</p>
<p><a href="/journal?page={n + 1}">Older entries</a></p>"""
    return page(request, f"Journal {n}", body)


@app.get("/about", response_class=HTMLResponse)
def about(request: Request) -> Response:
    # Benchmark probes: an internal-address beacon and an off-site link.
    # A correctly isolated scanner must block the first and not crawl the second.
    body = """<h1>About</h1><p>Northwind Supply is a fictional shop used to benchmark WEB X-RAY.</p>
<p><a href="https://example.org/">Our parent company</a></p>
<img src="http://169.254.169.254/latest/meta-data/" alt="" width="1" height="1">"""
    return page(request, "About", body)


@app.get("/robots.txt")
def robots_txt() -> Response:
    # Briefing benchmark: account pages are off-limits to automated readers.
    return Response("User-agent: *\nDisallow: /orders\nDisallow: /account/\n", media_type="text/plain")


@app.get("/.well-known/webxray-verification.txt")
def verification() -> Response:
    token = os.environ.get("DEMO_VERIFICATION_TOKEN", "")
    if not token:
        return PlainTextResponse("not configured", status_code=404)
    return PlainTextResponse(token + "\n")


# --------------------------------------------------------------------------- auth


def auth_form(kind: str, errors: list[str], values: dict[str, str], next_url: str = "") -> str:
    if kind == "register":
        return f"""<h1>Create your account</h1>{errors_block(errors)}
<form method="post" action="/register" novalidate>
<div class="field"><label for="name">Full name</label><input id="name" name="name" autocomplete="name" required value="{e(values.get("name", ""))}"></div>
<div class="field"><label for="email">Email</label><input id="email" name="email" type="email" autocomplete="email" required value="{e(values.get("email", ""))}"></div>
<div class="field"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="new-password" required minlength="8"></div>
<div class="field"><label for="confirm">Confirm password</label><input id="confirm" name="confirm" type="password" autocomplete="new-password" required></div>
<div class="field" style="flex-direction:row;align-items:center;gap:8px"><input id="terms" name="terms" type="checkbox" value="yes" required><label for="terms">I agree to the terms of service</label></div>
<button class="btn primary" type="submit">Create account</button>
</form><p>Already have an account? <a href="/login">Log in</a></p>"""
    return f"""<h1>Log in</h1>{errors_block(errors)}
<form method="post" action="/login" novalidate>
<input type="hidden" name="next" value="{e(next_url)}">
<div class="field"><label for="email">Email</label><input id="email" name="email" type="email" autocomplete="username" required value="{e(values.get("email", ""))}"></div>
<div class="field"><label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required></div>
<button class="btn primary" type="submit">Log in</button>
</form><p>New here? <a href="/register">Create an account</a></p>"""


@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request) -> Response:
    return page(request, "Create account", auth_form("register", [], {}))


@app.post("/register")
async def register(request: Request) -> Response:
    form = await request.form()
    values = {k: str(form.get(k, "")) for k in ("name", "email", "password", "confirm", "terms")}
    errs: list[str] = []
    if not values["name"].strip():
        errs.append("Enter your full name.")
    if not EMAIL_RE.match(values["email"].strip()):
        errs.append("Enter a valid email address.")
    elif store.user_by_email(values["email"].strip()):
        errs.append("An account with this email already exists.")
    if len(values["password"]) < 8:
        errs.append("Password must be at least 8 characters.")
    if values["password"] != values["confirm"]:
        errs.append("Passwords do not match.")
    if values["terms"] != "yes":
        errs.append("You must accept the terms of service.")
    if errs:
        return page(request, "Create account", auth_form("register", errs, values), status=422)
    user = store.add_user(values["name"].strip(), values["email"].strip(), values["password"])
    _, sess = get_session(request)
    sess.user_id = user.id
    return redirect(request, "/onboarding")


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: str = "") -> Response:  # noqa: A002
    return page(request, "Log in", auth_form("login", [], {}, next))


@app.post("/login")
async def login(request: Request) -> Response:
    form = await request.form()
    email = str(form.get("email", "")).strip()
    password = str(form.get("password", ""))
    next_url = str(form.get("next", ""))
    user = store.user_by_email(email)
    if user is None or user.password != password:
        return page(request, "Log in", auth_form("login", ["Email or password is incorrect."], {"email": email}, next_url), status=401)
    _, sess = get_session(request)
    sess.user_id = user.id
    if user.onboarding_step < 3:
        return redirect(request, "/onboarding")
    safe_next = next_url if next_url.startswith("/") and not next_url.startswith("//") else "/products"
    return redirect(request, safe_next)


@app.get("/logout")
def logout(request: Request) -> Response:
    _, sess = get_session(request)
    sess.user_id = None
    return redirect(request, "/")


# --------------------------------------------------------------------------- onboarding


@app.get("/onboarding", response_class=HTMLResponse)
def onboarding(request: Request, error: str = "") -> Response:
    _, sess = get_session(request)
    user = current_user(sess)
    if user is None:
        return redirect(request, "/login")
    if user.onboarding_step >= 3:
        return redirect(request, "/products")
    err = errors_block([error]) if error else ""
    if user.onboarding_step == 1:
        opts = "".join(
            f'<div class="field" style="flex-direction:row;align-items:center;gap:8px">'
            f'<input type="checkbox" id="i-{v}" name="interests" value="{v}"><label for="i-{v}">{label}</label></div>'
            for v, label in [("writing", "Writing"), ("carry", "Everyday carry"), ("desk", "Desk setup")]
        )
        body = f"""<h1>Welcome, {e(user.name)}</h1><p>Step 1 of 2 — what are you shopping for?</p>{err}
<form method="post" action="/onboarding"><fieldset style="border:0;padding:0"><legend>Interests (choose at least one)</legend>{opts}</fieldset>
<button class="btn primary" type="submit">Continue</button></form>"""
    else:
        body = f"""<h1>Almost done</h1><p>Step 2 of 2 — where should we ship?</p>{err}
<form method="post" action="/onboarding">
<div class="field"><label for="country">Shipping country</label><select id="country" name="country" required>
<option value="">Select a country</option><option value="US">United States</option><option value="GB">United Kingdom</option><option value="DE">Germany</option></select></div>
<button class="btn primary" type="submit">Finish setup</button></form>"""
    return page(request, "Welcome", body)


@app.post("/onboarding")
async def onboarding_submit(request: Request) -> Response:
    _, sess = get_session(request)
    user = current_user(sess)
    if user is None:
        return redirect(request, "/login")
    form = await request.form()
    if user.onboarding_step == 1:
        interests = [str(v) for v in form.getlist("interests")]
        if not interests:
            return redirect(request, "/onboarding?error=Choose+at+least+one+interest.")
        user.interests = interests
        user.onboarding_step = 2
        return redirect(request, "/onboarding")
    if user.onboarding_step == 2:
        country = str(form.get("country", ""))
        if country not in {"US", "GB", "DE"}:
            return redirect(request, "/onboarding?error=Select+a+shipping+country.")
        user.country = country
        user.onboarding_step = 3
    return redirect(request, "/products?welcome=1")


# --------------------------------------------------------------------------- cart & checkout


@app.post("/cart/add")
async def cart_add(request: Request) -> Response:
    token, sess = get_session(request)
    data = await request.json()
    slug = str(data.get("slug", ""))
    if slug not in PRODUCTS:
        return JSONResponse({"error": "unknown product"}, status_code=404)
    sess.cart[slug] = sess.cart.get(slug, 0) + 1
    return with_cookie(JSONResponse({"count": sum(sess.cart.values())}), token)


@app.post("/cart/remove")
async def cart_remove(request: Request) -> Response:
    _, sess = get_session(request)
    form = await request.form()
    sess.cart.pop(str(form.get("slug", "")), None)
    return redirect(request, "/cart")


def cart_rows(sess: Session) -> tuple[str, int]:
    rows, total = "", 0
    for slug, qty in sess.cart.items():
        p = PRODUCTS[slug]
        total += p["price"] * qty
        rows += f"<tr><td>{e(p['name'])}</td><td>{qty}</td><td>{money(p['price'] * qty)}</td></tr>"
    return rows, total


@app.get("/cart", response_class=HTMLResponse)
def cart(request: Request) -> Response:
    _, sess = get_session(request)
    if not sess.cart:
        return page(request, "Cart", '<h1>Your cart</h1><p>Your cart is empty.</p><p><a href="/products">Continue shopping</a></p>')
    rows, total = cart_rows(sess)
    removes = "".join(
        f'<form method="post" action="/cart/remove" style="display:inline"><input type="hidden" name="slug" value="{e(s)}">'
        f'<button class="btn" type="submit">Remove {e(PRODUCTS[s]["name"])}</button></form> '
        for s in sess.cart
    )
    body = f"""<h1>Your cart</h1>
<table><thead><tr><th>Item</th><th>Qty</th><th>Subtotal</th></tr></thead><tbody>{rows}</tbody></table>
<p style="font-size:18px"><strong>Total: {money(total)}</strong></p>
<p><a class="btn primary" href="/checkout">Proceed to checkout</a></p><p>{removes}</p>"""
    return page(request, "Cart", body)


def checkout_form(sess: Session, user: User, errors: list[str], values: dict[str, str]) -> str:
    rows, total = cart_rows(sess)
    v = lambda k, d="": e(values.get(k, d))  # noqa: E731
    countries = "".join(
        f'<option value="{c}"{" selected" if values.get("country", user.country) == c else ""}>{n}</option>'
        for c, n in [("US", "United States"), ("GB", "United Kingdom"), ("DE", "Germany")]
    )
    return f"""<h1>Checkout</h1>{errors_block(errors)}
<form method="post" action="/checkout" id="checkout-form" novalidate>
<h2 style="font-size:18px">Contact</h2>
<div class="field"><label for="email">Email</label><input id="email" name="email" type="email" autocomplete="email" value="{v("email", user.email)}"></div>
<h2 style="font-size:18px">Shipping address</h2>
<div class="field"><label for="full_name">Full name</label><input id="full_name" name="full_name" autocomplete="name" value="{v("full_name", user.name)}"></div>
<div class="field"><label for="address">Street address</label><input id="address" name="address" autocomplete="street-address" value="{v("address")}"></div>
<div class="row"><div class="field"><label for="city">City</label><input id="city" name="city" autocomplete="address-level2" value="{v("city")}"></div>
<div class="field"><label for="postal">Postal code</label><input id="postal" name="postal" autocomplete="postal-code" value="{v("postal")}"></div></div>
<div class="field"><label for="country">Country</label><select id="country" name="country" autocomplete="country">{countries}</select></div>
<h2 style="font-size:18px">Payment</h2>
<p class="notice">SimPay sandbox — use test card 4242 4242 4242 4242. No real charges are made.</p>
<div class="field"><label for="card">Card number</label><input id="card" name="card" inputmode="numeric" autocomplete="cc-number" value=""></div>
<div class="row"><div class="field"><label for="exp">Expiry (MM/YY)</label><input id="exp" name="exp" autocomplete="cc-exp" value="{v("exp")}"></div>
<div class="field"><label for="cvc">CVC</label><input id="cvc" name="cvc" inputmode="numeric" autocomplete="cc-csc" value=""></div></div>
<h2 style="font-size:18px">Order summary</h2>
<table><tbody>{rows}</tbody></table>
<p><strong>Total: {money(total)}</strong></p>
<button class="btn primary block" type="submit" id="place-order">Place order</button>
</form>"""


# Checkout is "distraction-free": no site footer, only the help bar.
HELP_BAR = """<aside class="help-bar" aria-label="Checkout help"><span>Questions about your order?</span>
<a href="/help" id="help-chat">Chat with us</a></aside>"""


@app.get("/checkout", response_class=HTMLResponse)
def checkout(request: Request) -> Response:
    guard = require_onboarded(request)
    if guard:
        return guard
    _, sess = get_session(request)
    user = current_user(sess)
    assert user is not None
    if not sess.cart:
        return page(request, "Checkout", '<h1>Checkout</h1><p>Your cart is empty.</p><p><a href="/products">Continue shopping</a></p>')
    return page(request, "Checkout", checkout_form(sess, user, [], {}) + HELP_BAR, body_class="has-help-bar", show_footer=False)


@app.post("/checkout")
async def checkout_submit(request: Request) -> Response:
    guard = require_onboarded(request)
    if guard:
        return guard
    _, sess = get_session(request)
    user = current_user(sess)
    assert user is not None
    form = await request.form()
    values = {k: str(form.get(k, "")).strip() for k in ("email", "full_name", "address", "city", "postal", "country", "card", "exp", "cvc")}
    errs: list[str] = []
    if not sess.cart:
        errs.append("Your cart is empty.")
    for key, label in [("full_name", "full name"), ("address", "street address"), ("city", "city"), ("postal", "postal code")]:
        if not values[key]:
            errs.append(f"Enter your {label}.")
    if not EMAIL_RE.match(values["email"]):
        errs.append("Enter a valid email address.")
    card = re.sub(r"\D", "", values["card"])
    if not re.match(r"^(0[1-9]|1[0-2])/\d{2}$", values["exp"]):
        errs.append("Enter the expiry as MM/YY.")
    if not re.match(r"^\d{3,4}$", values["cvc"]):
        errs.append("Enter the 3 or 4 digit CVC.")
    if not errs:
        if card == TEST_CARD_DECLINED:
            errs.append("SimPay declined this card.")
        elif card != TEST_CARD_APPROVED:
            errs.append("SimPay sandbox only accepts test card 4242 4242 4242 4242.")
    if errs:
        return page(request, "Checkout", checkout_form(sess, user, errs, values) + HELP_BAR, status=422, body_class="has-help-bar", show_footer=False)
    order = store.add_order(user.id, sess.cart)
    sess.cart.clear()
    return redirect(request, f"/orders/{order.id}/confirmation")


@app.get("/orders/{order_id}/confirmation", response_class=HTMLResponse)
def confirmation(request: Request, order_id: int) -> Response:
    _, sess = get_session(request)
    order = store.orders.get(order_id)
    if order is None or order.user_id != sess.user_id:
        return page(request, "Not found", "<h1>Order not found</h1>", status=404)
    body = f"""<h1>Order confirmed</h1><p>Thank you! Your order #{order.id} is confirmed.</p>
<p>Total charged to SimPay sandbox: {money(order.total)}</p><p><a href="/orders">View your orders</a></p>"""
    return page(request, "Order confirmed", body)


@app.get("/orders", response_class=HTMLResponse)
def orders(request: Request) -> Response:
    guard = require_onboarded(request)
    if guard:
        return guard
    _, sess = get_session(request)
    mine = [o for o in store.orders.values() if o.user_id == sess.user_id]
    rows = "".join(f"<tr><td>#{o.id}</td><td>{money(o.total)}</td></tr>" for o in mine) or '<tr><td colspan="2">No orders yet.</td></tr>'
    return page(request, "Orders", f"<h1>Your orders</h1><table><tbody>{rows}</tbody></table>")


# --------------------------------------------------------------------------- account


PHONE_BUGGY = re.compile(r"^\d{10}$")
PHONE_OK = re.compile(r"^\+?[\d\s().-]{7,20}$")


def profile_form(user: User, errors: list[str], saved: bool, values: dict[str, str]) -> str:
    notice = '<div class="notice" role="status">Profile saved.</div>' if saved else ""
    return f"""<h1>Profile settings</h1>{notice}{errors_block(errors)}
<form method="post" action="/account/profile" novalidate>
<div class="field"><label for="name">Full name</label><input id="name" name="name" autocomplete="name" value="{e(values.get("name", user.name))}"></div>
<div class="field"><label for="phone">Phone number</label><input id="phone" name="phone" type="tel" autocomplete="tel" value="{e(values.get("phone", user.phone))}"></div>
<button class="btn primary" type="submit">Save changes</button></form>"""


@app.get("/account/profile", response_class=HTMLResponse)
def profile(request: Request, saved: int = 0) -> Response:
    guard = require_onboarded(request)
    if guard:
        return guard
    _, sess = get_session(request)
    user = current_user(sess)
    assert user is not None
    return page(request, "Profile", profile_form(user, [], bool(saved), {}))


@app.post("/account/profile")
async def profile_submit(request: Request) -> Response:
    guard = require_onboarded(request)
    if guard:
        return guard
    _, sess = get_session(request)
    user = current_user(sess)
    assert user is not None
    form = await request.form()
    values = {"name": str(form.get("name", "")).strip(), "phone": str(form.get("phone", "")).strip()}
    errs: list[str] = []
    if not values["name"]:
        errs.append("Enter your full name.")
    # D2: the buggy validator rejects valid international numbers such as "+44 20 7946 0958".
    phone_re = PHONE_OK if _flag("DEMO_FIX_PHONE_VALIDATION") else PHONE_BUGGY
    if values["phone"] and not phone_re.match(values["phone"]):
        errs.append("Enter a valid phone number.")
    if errs:
        return page(request, "Profile", profile_form(user, errs, False, values), status=422)
    user.name, user.phone = values["name"], values["phone"]
    return redirect(request, "/account/profile?saved=1")


# --------------------------------------------------------------------------- APIs


@app.get("/api/recommendations")
def recommendations() -> Response:
    if _flag("DEMO_FIX_RECOMMENDATIONS"):
        return JSONResponse({"items": [p["name"] for p in list(PRODUCTS.values())[:2]]})
    # D3: simulated upstream failure.
    return JSONResponse({"error": "recommendation engine unavailable"}, status_code=503)


@app.get("/api/cart")
def api_cart(request: Request) -> Response:
    token, sess = get_session(request)
    return with_cookie(JSONResponse({"count": sum(sess.cart.values())}), token)


@app.post("/__demo/reset")
def demo_reset() -> Response:
    if not os.environ.get("DEMO_ALLOW_RESET"):
        return PlainTextResponse("reset disabled", status_code=404)
    store.reset()
    _RUNTIME_FLAGS.clear()
    return PlainTextResponse("ok")


@app.post("/__demo/flags")
async def demo_flags(request: Request) -> Response:
    """Toggle fix flags at runtime (benchmark automation only; requires DEMO_ALLOW_RESET=1)."""
    if not os.environ.get("DEMO_ALLOW_RESET"):
        return PlainTextResponse("flags disabled", status_code=404)
    data = await request.json()
    for key, value in data.items():
        if key.startswith("DEMO_FIX_"):
            _RUNTIME_FLAGS[key] = bool(value)
    return JSONResponse({"flags": _RUNTIME_FLAGS})


@app.get("/__demo/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        # Lets benchmarks assert that a read-only visit created nothing.
        "users": len(store.users),
        "orders": len(store.orders),
        "defects": {
            "D1_mobile_checkout_overlay": not _flag("DEMO_FIX_CHECKOUT_OVERLAY"),
            "D2_phone_validation": not _flag("DEMO_FIX_PHONE_VALIDATION"),
            "D3_recommendations_api": not _flag("DEMO_FIX_RECOMMENDATIONS"),
        },
    }
