"""Turn what a briefing visit read into a plain-language description of a website.

Everything here is deterministic and works only from what was observed on the
pages that were read: titles, headings, meta tags, structured data, links,
buttons and forms. Each statement carries the signals (and pages) it is based
on, so the dashboard can always answer "how do you know?". Nothing is looked up
elsewhere and nothing is guessed when the signals are missing.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

# --------------------------------------------------------------------------- input


@dataclass
class ReadPage:
    url: str
    path: str
    status: int | None
    title: str
    kind: str  # crawler.classify() result
    inventory: dict[str, Any]  # dom.INVENTORY_JS output
    meta: dict[str, Any]  # BRIEFING_META_JS output
    text: str = ""
    signed_in: bool = False  # read after signing in with the user's account


@dataclass
class Visit:
    origin: str
    pages: list[ReadPage]
    question: str = ""
    notes: list[str] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    duration_ms: int = 0
    # Sign-in outcome when the user supplied an account (None = not requested).
    auth_status: str | None = None
    auth_detail: str | None = None
    signed_in_as: str | None = None


# --------------------------------------------------------------------------- page picking

# Pages that explain a site best, in the order we'd read them. Each entry is
# (category, path/label pattern).
PRIORITY: list[tuple[str, re.Pattern[str]]] = [
    ("about", re.compile(r"\b(about|about-us|who-we-are|company|our-story|mission)\b", re.I)),
    ("product", re.compile(r"\b(features?|product|products|platform|how-it-works|solutions?|services?|what-we-do)\b", re.I)),
    ("pricing", re.compile(r"\b(pricing|plans?|prices?)\b", re.I)),
    ("shop", re.compile(r"\b(shop|store|catalog|collections?|menu)\b", re.I)),
    ("docs", re.compile(r"\b(docs?|documentation|developers?|api|guides?)\b", re.I)),
    ("help", re.compile(r"\b(help|faq|support|shipping|returns?)\b", re.I)),
    ("contact", re.compile(r"\b(contact|contact-us|locations?|find-us)\b", re.I)),
    ("blog", re.compile(r"\b(blog|news|articles?|stories|press|journal)\b", re.I)),
    ("careers", re.compile(r"\b(careers?|jobs|join-us|hiring)\b", re.I)),
]

_STOPWORDS = set(
    "a an and are as at be by can do does for from have how i in is it its me my of on or our so that the their "
    "there they this to was we what when where which who why will with you your page pages site website web any".split()
)


def question_terms(question: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9'-]{1,}", question.lower())
    return [w for w in dict.fromkeys(words) if w not in _STOPWORDS and len(w) > 2][:8]


def pick_pages(links: list[dict[str, Any]], *, limit: int, question: str = "") -> list[tuple[str, str]]:
    """Choose which same-origin links to read next.

    ``links`` items are ``{"url", "text", "in_nav"}``. Returns ``(url, reason)``
    pairs: one page per explanatory category first, then pages matching the
    user's question, then remaining navigation links.
    """
    chosen: list[tuple[str, str]] = []
    seen: set[str] = set()

    def take(url: str, reason: str) -> None:
        if url not in seen and len(chosen) < limit:
            seen.add(url)
            chosen.append((url, reason))

    def label(link: dict[str, Any]) -> str:
        return f"{urlsplit(link['url']).path} {link.get('text') or ''}".replace("/", " ").replace("_", " ")

    terms = question_terms(question)
    if terms:
        for link in links:
            hay = label(link).lower()
            if any(t in hay for t in terms):
                take(link["url"], "mentions your question")
                break
    for category, pattern in PRIORITY:
        ordered = sorted(links, key=lambda lk: (not lk.get("in_nav"), len(urlsplit(lk["url"]).path)))
        for link in ordered:
            if pattern.search(label(link)):
                take(link["url"], f"looks like the {category} page")
                break
    for link in links:
        if link.get("in_nav"):
            take(link["url"], "in the main navigation")
    for link in links:
        take(link["url"], "linked from the home page")
    return chosen


# --------------------------------------------------------------------------- helpers


def _clean(s: Any, n: int = 300) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _article(phrase: str) -> str:
    return ("an " if phrase[:1].lower() in "aeiou" else "a ") + phrase


def _jsonld_types(page: ReadPage) -> set[str]:
    return {str(t) for t in page.meta.get("jsonld_types") or []}


def _texts(page: ReadPage, key: str) -> list[str]:
    inv = page.inventory
    if key == "buttons":
        return [b.get("text", "") for b in inv.get("buttons", []) if b.get("text")]
    if key == "links":
        return [lk.get("text", "") for lk in inv.get("links", []) if lk.get("text")]
    return []


def _any_text(pages: list[ReadPage], pattern: re.Pattern[str], key: str) -> list[str]:
    return [p.path for p in pages if any(pattern.search(t) for t in _texts(p, key))]


def _paths_like(pages: list[ReadPage], pattern: re.Pattern[str]) -> list[str]:
    return [p.path for p in pages if pattern.search(p.path)]


def _link_paths(pages: list[ReadPage], pattern: re.Pattern[str]) -> list[str]:
    hits: list[str] = []
    for p in pages:
        for lk in p.inventory.get("links", []):
            path = urlsplit(lk.get("href", "")).path
            if pattern.search(path) or pattern.search(lk.get("text", "")):
                hits.append(p.path)
                break
    return hits


def _dedupe(paths: list[str]) -> list[str]:
    return list(dict.fromkeys(paths))


# --------------------------------------------------------------------------- name & description


_GENERIC_TITLE = re.compile(
    r"^(home|homepage|welcome|log ?in|sign ?in|sign ?up|register|dashboard|account|my account|index|main|page|portal)$", re.I
)
_TITLE_SPLIT = re.compile(r"\s+[|–—\-·:]\s+")


def _public(visit: Visit) -> list[ReadPage]:
    return [p for p in visit.pages if not p.signed_in]


def site_name(visit: Visit) -> tuple[str, str]:
    home = visit.pages[0] if visit.pages else None
    if home:
        for key, source in (("og_site_name", "the site's og:site_name tag"), ("application_name", "the application-name tag")):
            if _clean(home.meta.get(key)):
                return _clean(home.meta.get(key), 80), source
        for name in home.meta.get("jsonld_names") or []:
            if _clean(name):
                return _clean(name, 80), "the site's structured data"
    segments: Counter[str] = Counter()
    for p in _public(visit):
        parts = [x.strip() for x in _TITLE_SPLIT.split(p.title or "") if x.strip()]
        if len(parts) > 1:
            # Page words ("Login", "Home") are never the site's name.
            for part in dict.fromkeys([parts[0], parts[-1]]):
                if not _GENERIC_TITLE.match(part):
                    segments[part] += 1
    if segments:
        name, count = segments.most_common(1)[0]
        if count >= 2 or len(visit.pages) == 1:
            return name[:80], "the page titles"
    if home and home.title:
        parts = [x.strip() for x in _TITLE_SPLIT.split(home.title) if x.strip() and not _GENERIC_TITLE.match(x.strip())]
        if parts:
            return parts[0][:80], "the home page title"
    host = urlsplit(visit.origin).hostname or visit.origin
    return host.removeprefix("www."), "the web address"


def site_description(visit: Visit) -> tuple[str | None, str | None]:
    home = visit.pages[0] if visit.pages else None
    if not home:
        return None, None
    for key, source in (
        ("description", "the home page's description tag"),
        ("og_description", "the home page's social-sharing description"),
    ):
        text = _clean(home.meta.get(key), 400)
        if len(text) >= 20:
            return text, source
    for para in home.meta.get("paragraphs") or []:
        text = _clean(para, 400)
        if len(text) >= 40:
            return text, "the first paragraph of the home page"
    return None, None


# --------------------------------------------------------------------------- site type


_ADD_TO_CART = re.compile(r"\badd to (cart|bag|basket)\b|\bbuy now\b", re.I)
_SIGNUP = re.compile(r"\b(sign ?up|register|create (an |your )?account|start (for )?free|free trial|get started|try (it )?free)\b", re.I)
_LOGIN = re.compile(r"\b(log ?in|sign ?in)\b", re.I)
_DONATE = re.compile(r"\bdonat(e|ion)\b", re.I)
_BOOK = re.compile(r"\b(book (a|an|now|online)|reserve|reservation|schedule (a|an)|appointment|book a table)\b", re.I)
_SUBSCRIBE = re.compile(r"\b(subscribe|newsletter|join (our|the) (list|mailing))\b", re.I)
_PER_PERIOD = re.compile(r"/\s?(mo|month|yr|year|user)\b|per (month|year|user)", re.I)


@dataclass
class TypeScore:
    key: str
    label: str
    score: int = 0
    reasons: list[str] = field(default_factory=list)

    def add(self, points: int, reason: str) -> None:
        self.score += points
        self.reasons.append(reason)


def site_types(visit: Visit) -> list[TypeScore]:
    pages = visit.pages
    host = (urlsplit(visit.origin).hostname or "").lower()
    types = {t.key: t for t in (
        TypeScore("online_store", "Online store"),
        TypeScore("software", "Software product or app"),
        TypeScore("publication", "Blog, news or publication"),
        TypeScore("documentation", "Documentation site"),
        TypeScore("local_business", "Local business"),
        TypeScore("nonprofit", "Nonprofit or charity"),
        TypeScore("personal", "Personal site or portfolio"),
        TypeScore("community", "Community or forum"),
        TypeScore("institution", "Government or education"),
        TypeScore("company", "Company or service business"),
        TypeScore("members_only", "Members-only service"),
    )}
    all_types = set().union(*(_jsonld_types(p) for p in pages)) if pages else set()

    cart_buttons = _dedupe(_any_text(pages, _ADD_TO_CART, "buttons"))
    if cart_buttons:
        types["online_store"].add(3, f"'Add to cart' style buttons on {_plural(len(cart_buttons), 'page')}")
    shop_pages = _dedupe([p.path for p in pages if p.kind in {"cart", "checkout", "product", "listing"}])
    if shop_pages:
        types["online_store"].add(2, f"shop pages such as {shop_pages[0]}")
    if all_types & {"Product", "Offer", "AggregateOffer"}:
        types["online_store"].add(3, "structured data describing products for sale")
    priced = [p.path for p in pages if p.meta.get("prices")]
    if len(priced) >= 2 and not any(_PER_PERIOD.search(" ".join(p.meta.get("prices") or [])) for p in pages):
        types["online_store"].add(1, f"prices shown on {_plural(len(priced), 'page')}")

    pricing = _dedupe(_paths_like(pages, re.compile(r"/(pricing|plans)\b", re.I)) + _link_paths(pages, re.compile(r"^/?(pricing|plans)$", re.I)))
    if pricing:
        types["software"].add(2, "a pricing or plans page")
    signups = _dedupe(_any_text(pages, _SIGNUP, "buttons") + _any_text(pages, _SIGNUP, "links"))
    if signups and not cart_buttons:
        types["software"].add(2, "sign-up or free-trial calls to action")
    if any(_PER_PERIOD.search(" ".join(p.meta.get("prices") or [])) for p in pages):
        types["software"].add(2, "subscription prices (per month, year or user)")
    if all_types & {"SoftwareApplication", "WebApplication", "MobileApplication"}:
        types["software"].add(3, "structured data describing a software application")
    if _paths_like(pages, re.compile(r"/(features|integrations|platform)\b", re.I)):
        types["software"].add(1, "a features or integrations page")

    if all_types & {"Article", "BlogPosting", "NewsArticle", "Blog"}:
        types["publication"].add(3, "structured data describing articles")
    blog = _dedupe(_paths_like(pages, re.compile(r"/(blog|news|articles?|posts?)\b", re.I)))
    if blog:
        types["publication"].add(2, f"article sections such as {blog[0]}")

    docs = _dedupe(_paths_like(pages, re.compile(r"/(docs?|documentation|reference|guides?)\b", re.I)))
    if pages and len(docs) >= max(2, len(pages) // 2):
        types["documentation"].add(4, "most of the pages read are documentation")
    elif docs:
        types["documentation"].add(1, f"documentation at {docs[0]}")
    if host.startswith(("docs.", "developer.", "developers.")):
        types["documentation"].add(3, "the address starts with docs/developer")

    if all_types & {"LocalBusiness", "Restaurant", "Store", "MedicalBusiness", "Dentist", "Hotel", "FoodEstablishment"}:
        types["local_business"].add(4, "structured data describing a local business")
    if any(p.meta.get("address") for p in pages):
        types["local_business"].add(1, "a street address on the site")
    booking = _dedupe(_any_text(pages, _BOOK, "buttons") + _any_text(pages, _BOOK, "links"))
    if booking:
        types["local_business"].add(2, "booking or reservation links")

    donate = _dedupe(_any_text(pages, _DONATE, "buttons") + _any_text(pages, _DONATE, "links"))
    if donate:
        types["nonprofit"].add(3, "donation links or buttons")
    if all_types & {"NGO", "NonprofitOrganization"} or host.endswith(".org") and donate:
        types["nonprofit"].add(2, "nonprofit structured data or a .org address with donations")

    if all_types & {"Person", "ProfilePage"}:
        types["personal"].add(3, "structured data describing a person")
    if _paths_like(pages, re.compile(r"/(portfolio|work|projects|resume|cv)\b", re.I)):
        types["personal"].add(1, "portfolio or résumé pages")

    if _paths_like(pages, re.compile(r"/(forum|community|discussions?|threads?|topics?)\b", re.I)):
        types["community"].add(3, "forum or community pages")

    if re.search(r"\.(gov|edu|mil|ac\.[a-z]{2}|gov\.[a-z]{2})$", host):
        types["institution"].add(4, f"a {host.rsplit('.', 1)[-1]} web address")

    company_signals = _dedupe(_paths_like(pages, re.compile(r"/(about|services?|contact|careers|team)\b", re.I)))
    if company_signals:
        types["company"].add(1, f"company pages such as {company_signals[0]}")
    if all_types & {"Organization", "Corporation"}:
        types["company"].add(1, "structured data describing an organization")

    home = pages[0] if pages else None
    if home is not None and home.kind == "login":
        types["members_only"].add(3, "the home page is a sign-in form")
        if len([p for p in pages if not p.signed_in]) <= 2:
            types["members_only"].add(1, "there's almost nothing public to read")

    ranked = sorted((t for t in types.values() if t.score > 0), key=lambda t: -t.score)
    if not ranked:
        fallback = types["company"]
        fallback.reasons.append("no strong signals; this is our best general description")
        ranked = [fallback]
    return ranked


def confidence(score: int) -> str:
    return "high" if score >= 5 else "medium" if score >= 3 else "low"


# --------------------------------------------------------------------------- capabilities


def capabilities(visit: Visit) -> list[dict[str, Any]]:
    pages = visit.pages
    out: list[dict[str, Any]] = []

    member_only = {p.path for p in pages if p.signed_in} - {p.path for p in pages if not p.signed_in}

    def add(key: str, label: str, detail: str, paths: list[str]) -> None:
        if paths:
            unique = _dedupe(paths)
            out.append({"key": key, "label": label, "detail": detail, "pages": unique[:5],
                        "signed_in_only": all(x in member_only for x in unique)})

    listing = [p.path for p in pages if p.kind in {"listing", "product"}]
    add("browse_products", "Browse products", "Product or catalogue pages", listing)
    buy = _any_text(pages, _ADD_TO_CART, "buttons") + [p.path for p in pages if p.kind in {"cart", "checkout"}]
    add("buy", "Buy things online", "'Add to cart' buttons, a cart or a checkout", buy)
    register = [p.path for p in pages if p.kind == "register"] + _any_text(pages, _SIGNUP, "links") + _any_text(pages, _SIGNUP, "buttons")
    add("sign_up", "Create an account", "Sign-up links, buttons or forms", register)
    login = [p.path for p in pages if p.kind == "login"] + _any_text(pages, _LOGIN, "links")
    add("log_in", "Sign in to an account", "Sign-in links or a sign-in form", login)
    add("search", "Search the site", "A search box", [p.path for p in pages if p.meta.get("has_search")])
    pricing = _paths_like(pages, re.compile(r"/(pricing|plans)\b", re.I))
    add("view_pricing", "See prices and plans", "A pricing page", pricing)
    contact_forms = [
        p.path for p in pages
        if any(any(f.get("type") == "email" for f in form.get("fields", [])) and any(f.get("tag") == "textarea" for f in form.get("fields", []))
               for form in p.inventory.get("forms", []))
    ]
    contact = contact_forms + _paths_like(pages, re.compile(r"/contact", re.I)) + [p.path for p in pages if p.meta.get("emails")]
    add("contact", "Get in touch", "A contact page, form or email address", contact)
    newsletter = [
        p.path for p in pages
        if any(len(form.get("fields", [])) <= 2 and any(f.get("type") == "email" for f in form.get("fields", []))
               and any(_SUBSCRIBE.search(s.get("text", "")) for s in form.get("submits", []))
               for form in p.inventory.get("forms", []))
    ] + _any_text(pages, _SUBSCRIBE, "buttons")
    add("newsletter", "Sign up for emails", "A newsletter or mailing-list form", newsletter)
    add("read", "Read articles", "Blog, news or article pages", _paths_like(pages, re.compile(r"/(blog|news|articles?|posts?)\b", re.I)))
    add("docs", "Read documentation", "Documentation or developer guides", _paths_like(pages, re.compile(r"/(docs?|documentation|developers?|guides?)\b", re.I)))
    add("help", "Get help", "Help, FAQ or support pages", [p.path for p in pages if p.kind == "support"])
    add("book", "Book or reserve", "Booking, reservation or appointment links", _any_text(pages, _BOOK, "buttons") + _any_text(pages, _BOOK, "links"))
    add("donate", "Donate", "Donation links or buttons", _any_text(pages, _DONATE, "buttons") + _any_text(pages, _DONATE, "links"))
    add("app", "Download a mobile app", "Links to an app store", [p.path for p in pages if p.meta.get("app_links")])
    add("careers", "Apply for jobs", "Careers or jobs pages", _paths_like(pages, re.compile(r"/(careers?|jobs)\b", re.I)) + _link_paths(pages, re.compile(r"^/?(careers?|jobs)$", re.I)))
    return out


# --------------------------------------------------------------------------- organization & tech


_COPYRIGHT = re.compile(r"(?:©|\(c\)|copyright)\s*(?:\d{4}(?:\s*[-–]\s*\d{4})?)?\s*,?\s*([A-Z][\w&.,' -]{1,60}?)(?:\.|\s+all rights|\s*\||$)", re.I)

SOCIAL_NAMES = {
    "twitter.com": "X (Twitter)", "x.com": "X (Twitter)", "facebook.com": "Facebook", "instagram.com": "Instagram",
    "linkedin.com": "LinkedIn", "youtube.com": "YouTube", "github.com": "GitHub", "tiktok.com": "TikTok",
    "pinterest.com": "Pinterest", "threads.net": "Threads", "mastodon.social": "Mastodon", "discord.gg": "Discord",
    "discord.com": "Discord", "reddit.com": "Reddit", "bsky.app": "Bluesky",
}


def organization(visit: Visit) -> dict[str, Any]:
    emails: list[str] = []
    phones: list[str] = []
    social: dict[str, str] = {}
    address = None
    copyright_holder = None
    org_names: list[str] = []
    for p in visit.pages:
        emails += p.meta.get("emails") or []
        phones += p.meta.get("phones") or []
        for url in p.meta.get("social") or []:
            host = (urlsplit(url).hostname or "").removeprefix("www.")
            name = SOCIAL_NAMES.get(host)
            if name and name not in social:
                social[name] = url
        address = address or (_clean(p.meta.get("address"), 200) or None)
        org_names += [n for n in p.meta.get("jsonld_org_names") or [] if n]
        if not copyright_holder:
            m = _COPYRIGHT.search(p.meta.get("footer") or "")
            if m:
                copyright_holder = _clean(m.group(1), 80).rstrip(",. ")
    return {
        "name": _clean(org_names[0], 80) if org_names else None,
        "copyright": copyright_holder,
        "emails": _dedupe([e.lower() for e in emails])[:5],
        "phones": _dedupe(phones)[:5],
        "address": address,
        "social": [{"network": k, "url": v} for k, v in social.items()][:10],
    }


TECH_LABELS = {
    "next": "Next.js", "nuxt": "Nuxt", "gatsby": "Gatsby", "wordpress": "WordPress", "shopify": "Shopify",
    "wix": "Wix", "squarespace": "Squarespace", "webflow": "Webflow", "drupal": "Drupal", "angular": "Angular",
    "vue": "Vue", "react": "React", "svelte": "Svelte", "jquery": "jQuery", "astro": "Astro", "remix": "Remix",
    "ghost": "Ghost", "hubspot": "HubSpot", "framer": "Framer",
}


def technology(visit: Visit) -> list[dict[str, str]]:
    found: dict[str, str] = {}
    for p in visit.pages:
        for key in p.meta.get("tech") or []:
            if key in TECH_LABELS and TECH_LABELS[key] not in found:
                found[TECH_LABELS[key]] = f"seen in the page code of {p.path}"
        gen = _clean(p.meta.get("generator"), 80)
        if gen and gen not in found:
            found[gen] = "declared in the page's generator tag"
        for header in ("server", "x-powered-by"):
            val = _clean((p.meta.get("headers") or {}).get(header), 60)
            if val and val not in found:
                found[val] = f"reported by the server ({header} header)"
    # React is implied by Next.js/Gatsby/Remix; keep the list short and specific.
    if "React" in found and any(x in found for x in ("Next.js", "Gatsby", "Remix")):
        found.pop("React")
    return [{"name": k, "evidence": v} for k, v in list(found.items())[:8]]


# --------------------------------------------------------------------------- question answering


def answer_pages(visit: Visit, question: str) -> list[dict[str, str]]:
    """Pages whose address or title matches the question's key words."""
    terms = question_terms(question)
    out = []
    for p in visit.pages:
        hay = f"{p.path} {p.title}".lower().replace("/", " ")
        if terms and any(t in hay for t in terms):
            out.append({"page": p.path, "title": p.title})
    return out[:5]


def answer_passages(visit: Visit, question: str, limit: int = 5) -> list[dict[str, str]]:
    """Sentences from the pages read that mention the question's key words."""
    terms = question_terms(question)
    if not terms:
        return []
    scored: list[tuple[int, str, str]] = []
    for p in visit.pages:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", p.text or ""):
            s = _clean(sentence, 320)
            if len(s) < 25:
                continue
            low = s.lower()
            hits = sum(1 for t in terms if t in low)
            if hits:
                scored.append((hits, s, p.path))
    scored.sort(key=lambda x: -x[0])
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, s, path in scored:
        if s not in seen:
            seen.add(s)
            out.append({"text": s, "page": path})
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- briefing


def build_briefing(visit: Visit) -> dict[str, Any]:
    name, name_source = site_name(visit)
    description, description_source = site_description(visit)
    ranked = site_types(visit)
    primary = ranked[0]
    caps = capabilities(visit)
    org = organization(visit)
    tech = technology(visit)
    home = visit.pages[0] if visit.pages else None

    sections: list[dict[str, str]] = []
    if home:
        seen: set[str] = set()
        for lk in home.inventory.get("links", []):
            # "Cart (0)" → "Cart"; the logo/home link and sign-in links are not sections.
            text = re.sub(r"\s*[(\[]\d+[)\]]\s*$", "", _clean(lk.get("text"), 40))
            try:
                parts = urlsplit(lk.get("href", ""))
                same = parts.netloc == urlsplit(visit.origin).netloc
            except ValueError:
                continue
            if not (lk.get("inNav") and same and len(text) > 1) or parts.path in {"", "/"}:
                continue
            if _LOGIN.search(text) or _SIGNUP.search(text) or text.lower() in seen:
                continue
            seen.add(text.lower())
            sections.append({"label": text, "url": lk["href"]})
        sections = sections[:12]

    prices: list[dict[str, str]] = []
    for p in visit.pages:
        for price in (p.meta.get("prices") or [])[:6]:
            if len(prices) < 12 and not any(x["text"] == price for x in prices):
                prices.append({"text": price, "page": p.path})

    # Plain-language summary, built only from the facts above.
    kind_phrase = primary.label[0].lower() + primary.label[1:]
    hedge = {"high": "is", "medium": "looks like", "low": "appears to be"}[confidence(primary.score)]
    sentences = [f"{name} {hedge} {_article(kind_phrase)}."]
    if description:
        sentences.append(f"It describes itself as: “{description.rstrip('.')}.”")
    if caps:
        verbs = [c["label"][0].lower() + c["label"][1:] for c in caps[:5]]
        public_count = len(_public(visit))
        where = _plural(public_count, "public page") if public_count != len(visit.pages) else _plural(public_count, "page")
        sentences.append(f"On the {where} we read, visitors can {_join(verbs)}.")
    if sections:
        sentences.append(f"The main sections are {_join([s['label'] for s in sections[:5]])}.")
    owner = org["name"] or org["copyright"]
    if owner and owner.lower() != name.lower():
        sentences.append(f"The site credits {owner} as its owner.")
    member_pages = [p for p in visit.pages if p.signed_in]
    if visit.auth_status == "authenticated":
        titled = [(_TITLE_SPLIT.split(p.title)[0].strip() or p.path) for p in member_pages[:3]]
        who = visit.signed_in_as or "your account"
        if member_pages:
            sentences.append(f"After signing in as {who}, we also read {_plural(len(member_pages), 'members-only page')}: {_join(titled)}.")
        else:
            sentences.append(f"We signed in as {who}, but that didn't reveal any new pages.")

    notes = list(visit.notes)
    errors = [p for p in visit.pages if (p.status or 0) >= 400]
    if errors:
        notes.append(f"{_plural(len(errors), 'page')} answered with an error ({', '.join(f'{p.path} → {p.status}' for p in errors[:3])}).")
    if any(p.inventory.get("captcha") for p in visit.pages):
        notes.append("A bot check (CAPTCHA) appeared. We don't try to get past those, so some content may be missing.")
    if home is not None and home.kind == "login" and len(_public(visit)) == 1:
        notes.append("The home page is a sign-in page with no links, so almost everything here is for members only."
                     + ("" if visit.auth_status == "authenticated" else " Add an account when you ask to see what members see."))
    elif visit.auth_status is None and any(p.kind == "login" for p in visit.pages):
        notes.append("Some content is behind a sign-in. Add an account when you ask, and the briefing can read that part too.")
    if member_pages:
        notes.append("Signed-in pages were read on your behalf with your account, so robots.txt (which is meant for public crawlers) "
                     "wasn't applied to them. They may include your own account details; this briefing is visible to your workspace.")

    return {
        "name": name,
        "name_source": name_source,
        "headline": _clean((home.inventory.get("h1") or [None])[0], 200) if home and home.inventory.get("h1") else None,
        "description": description,
        "description_source": description_source,
        "summary": " ".join(sentences),
        "site_type": {
            "key": primary.key, "label": primary.label, "confidence": confidence(primary.score), "reasons": primary.reasons[:5],
        },
        "other_types": [{"key": t.key, "label": t.label, "reasons": t.reasons[:3]} for t in ranked[1:3] if t.score >= 2],
        "capabilities": caps,
        "sections": sections,
        "organization": org,
        "prices": prices,
        "technology": tech,
        "languages": _dedupe([str(p.meta.get("lang")).split("-")[0].lower() for p in visit.pages if p.meta.get("lang")])[:5],
        "question": visit.question or None,
        "answer": answer_passages(visit, visit.question) if visit.question else [],
        "answer_pages": answer_pages(visit, visit.question) if visit.question else [],
        "pages": [
            {
                "url": p.url, "path": p.path, "title": p.title, "status": p.status, "kind": p.kind, "signed_in": p.signed_in,
                "description": _clean(p.meta.get("description") or (p.inventory.get("h1") or [""])[0], 200) or None,
            }
            for p in visit.pages
        ],
        "sign_in": None if visit.auth_status is None else {
            "status": visit.auth_status,
            "detail": visit.auth_detail,
            "as": visit.signed_in_as,
            "pages": [p.path for p in member_pages],
        },
        "notes": notes,
        "skipped": visit.skipped[:20],
        "stats": {"pages_read": len(visit.pages), "duration_ms": visit.duration_ms},
    }
