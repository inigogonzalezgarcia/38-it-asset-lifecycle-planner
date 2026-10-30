"""The checks. First one inventory is built: every Device42 device, office register item, vendor purchase and MDM device joined by serial
number, with one state (in stock, deployed, in repair, to be retired, retired) and one replacement date from the refresh policy. Then six
areas: coverage (what MDM sees that the inventory does not, items not seen for weeks, duplicate or mismatched serials, items without owner
or site), the comms rooms (end of support, warranty, rack position, owner, firmware recorded), lifecycle (overdue and due replacements),
people (leavers' devices, more devices than the policy allows, people without a computer), stock (below minimum and what next quarter's
replacements need) and the forecast by quarter for the budget. Each finding says what to do and who owns it."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from .model import (COMMS_CATEGORIES, MDM_CATEGORIES, NETWORK_CATEGORIES, STATES, Data, _norm, add_years, days, key, mdm_category, quarter,
                    quarter_end, serial_key)

CRITICAL, WARNING, INFO = "critical", "warning", "info"
ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}
AREAS = ("Coverage", "Comms rooms", "Lifecycle", "People", "Stock", "Forecast")
VERDICT = {CRITICAL: "action needed", WARNING: "attention", None: "on track"}


@dataclass
class Finding:
    severity: str
    area: str
    code: str
    subject: str
    detail: str
    fix: str
    owner: str = ""
    items: list[str] = field(default_factory=list)


@dataclass
class Issue:
    severity: str
    code: str
    text: str


@dataclass
class Asset:
    """One item of the joined inventory."""
    key: str
    serial: str = ""
    name: str = ""
    asset_tag: str = ""
    category: str = "other"
    model: str = ""
    manufacturer: str = ""
    sources: list[str] = field(default_factory=list)
    site: str = ""
    room: str = ""
    rack: str = ""
    position: str = ""
    owner: str = ""
    service_level: str = ""
    os: str = ""
    os_version: str = ""
    declared_state: str = ""
    in_service: bool = True
    purchase_date: date | None = None
    warranty_end: date | None = None
    eos: date | None = None
    cost: float | None = None
    order: str = ""
    vendor: str = ""
    mdm_last: datetime | None = None
    mdm_enrolled: datetime | None = None
    mdm_records: int = 0
    mdm_model: str = ""
    compliance: str = ""
    bad_serial: str = ""            # serial reported by MDM that cannot be matched ('To be filled by O.E.M.')
    ship_site: str = ""
    state: str = ""
    replace_on: date | None = None
    basis: str = ""
    estimated: bool = False

    @property
    def label(self) -> str:
        n = self.name or self.asset_tag or self.serial
        return f"{n} ({self.serial})" if self.serial and n != self.serial else n

    @property
    def inventoried(self) -> bool:
        return any(s in self.sources for s in ("Device42", "Register", "Purchases"))

    @property
    def active(self) -> bool:
        return self.state in ("deployed", "in repair", "to be retired")


def _n(k: int, word: str, plural: str | None = None) -> str:
    return f"{k} {word if k == 1 else (plural or word + 's')}"


def _top(items: list[str], k: int = 6, sep: str = ", ") -> str:
    return sep.join(items[:k]) + (f" and {len(items) - k} more" if len(items) > k else "")


def _d(v) -> str:
    return v.strftime("%d %b %Y") if v else "never"


def money(d: Data, v: float) -> str:
    return f"{d.settings.currency}{v:,.0f}"


def worst(issues: list[Issue]) -> str | None:
    sev = {i.severity for i in issues}
    return CRITICAL if CRITICAL in sev else WARNING if WARNING in sev else None


def _row(**kw) -> dict:
    kw.setdefault("issues", [])
    kw["severity"] = worst(kw["issues"])
    kw["verdict"] = VERDICT[kw["severity"]]
    return kw


# ---------------------------------------------------------------- one inventory

MAKERS = {"dell", "apple", "hp", "hpe", "lenovo", "samsung", "google", "logitech", "cisco", "asus", "asustek", "microsoft", "inc", "technologies",
          "computer", "electronics"}


def _family(model: str) -> tuple[str, set[str]]:
    """'Dell Latitude 7450' -> ('latitude', {'7450'}); years are not model numbers."""
    words = [w for w in _norm(model).split() if w not in MAKERS]
    fam = next((w for w in words if w.isalpha()), "")
    nums = {w for w in words if len(w) == 4 and w.isdigit() and not (w.startswith("19") or w.startswith("20"))}
    return fam, nums


def model_mismatch(a: str, b: str) -> bool:
    if not a or not b:
        return False
    (fa, na), (fb, nb) = _family(a), _family(b)
    return (fa and fb and fa != fb) or bool(na and nb and na != nb)


def inventory(d: Data) -> dict:
    """Joins every source by serial. Returns the assets, plus the facts found while joining (duplicates, placeholders, personal devices)."""
    s, today = d.settings, d.today
    assets: dict[str, Asset] = {}
    dup_register, dup_purchase, mismatch, placeholder, personal = defaultdict(list), defaultdict(list), [], [], []

    def get(k: str, serial: str = "") -> Asset:
        if k not in assets:
            assets[k] = Asset(k, serial)
        return assets[k]

    for c in d.comms:
        k = serial_key(c.serial) or f"D42:{key(c.name)}"
        a = get(k, c.serial)
        a.sources.append("Device42")
        a.name, a.asset_tag, a.category, a.model, a.manufacturer = c.name, c.asset_tag, c.category, c.model, c.manufacturer
        a.site, a.room, a.rack, a.position, a.owner, a.service_level = c.building, c.room, c.rack, c.position, c.owner, c.service_level
        a.os, a.os_version, a.in_service = c.os, c.os_version, c.in_service
        a.purchase_date, a.warranty_end, a.eos = c.purchase_date, c.warranty_end, c.eos
        if not c.in_service:
            a.declared_state = "in stock"
    reg_tags = defaultdict(list)
    for r in d.register:
        reg_tags[serial_key(r.serial) or f"TAG:{key(r.asset_tag)}"].append(r.asset_tag)
    dup_register.update(reg_tags)
    for r in d.register:
        k = serial_key(r.serial) or f"TAG:{key(r.asset_tag)}"
        if k in assets and "Register" in assets[k].sources:
            continue
        a = get(k, r.serial)
        a.sources.append("Register")
        a.asset_tag = a.asset_tag or r.asset_tag
        a.category = a.category if a.category != "other" else r.category
        a.model, a.manufacturer = a.model or r.model, a.manufacturer or r.manufacturer
        a.site, a.room = a.site or r.site, a.room or r.room
        a.owner = a.owner or r.assigned
        a.declared_state = r.state or a.declared_state
        a.purchase_date = a.purchase_date or r.purchase_date
    for p in d.purchases:
        k = serial_key(p.serial)
        if not k:
            continue
        dup_purchase[k].append(p.order or "?")
        if len(dup_purchase[k]) > 1:
            continue
        a = get(k, p.serial)
        a.sources.append("Purchases")
        if a.model and model_mismatch(a.model, p.model):
            mismatch.append((a, "purchase", p.model, a.model))
        a.category = a.category if a.category != "other" else p.category
        a.model = a.model or p.model
        a.purchase_date = a.purchase_date or p.purchase_date
        a.warranty_end = a.warranty_end or p.warranty_end
        a.cost, a.order, a.vendor = p.cost, p.order, p.vendor
        a.ship_site = p.site
    # MDM: the most recent record per serial wins; older ones are duplicates (re-enrolments)
    by_serial: dict[str, list] = defaultdict(list)
    for m in d.mdm:
        if m.personal:
            personal.append(m)
            continue
        k = serial_key(m.serial)
        if not k:
            placeholder.append(m)
            k = f"MDM:{key(m.source)}:{key(m.name)}"
        by_serial[k].append(m)
    for k, ms in by_serial.items():
        ms.sort(key=lambda m: m.last_seen or datetime.min, reverse=True)
        m = ms[0]
        a = get(k, m.serial if serial_key(m.serial) else "")
        for x in ms:
            if x.source not in a.sources:
                a.sources.append(x.source)
        a.mdm_records = len(ms)
        a.name = a.name or m.name
        a.mdm_model = m.model
        if not serial_key(m.serial):
            a.bad_serial = m.serial
        if a.model and model_mismatch(a.model, m.model):
            mismatch.append((a, m.source, m.model, a.model))
        a.model, a.manufacturer = a.model or m.model, a.manufacturer or m.manufacturer
        if a.category == "other":
            a.category = mdm_category(m.model, m.os, m.name)
        a.os, a.os_version = a.os or m.os, a.os_version or m.os_version
        a.mdm_last, a.mdm_enrolled, a.compliance = m.last_seen, m.enrolled, m.compliance
        if m.user and (a.category in MDM_CATEGORIES or not a.owner):
            a.owner = m.user        # the MDM user is the live assignment of a computer or phone
    # site, state and replacement date
    for a in assets.values():
        if not a.site:
            p = d.person(a.owner) if "@" in a.owner else None
            a.site = (p.site if p else "") or a.ship_site
        a.state = _state(d, a)
        _replacement(d, a)
    out = sorted(assets.values(), key=lambda a: (COMMS_ORDER.get(a.category, 99), a.site, a.category, a.label))
    return dict(assets=out, dup_register={k: v for k, v in dup_register.items() if len(v) > 1},
                dup_purchase={k: v for k, v in dup_purchase.items() if len(v) > 1}, mismatch=mismatch, placeholder=placeholder, personal=personal)


COMMS_ORDER = {c: i for i, c in enumerate(("laptop", "desktop", "phone", "tablet", "monitor", "dock", "meeting room", "printer", "switch", "router",
                                           "firewall", "server", "storage", "pdu", "ups", "patch panel", "other"))}


def _state(d: Data, a: Asset) -> str:
    if a.declared_state:
        return a.declared_state
    if "Device42" in a.sources:
        return "deployed" if a.in_service else "in stock"
    return "deployed"


def _replacement(d: Data, a: Asset) -> None:
    s = d.settings
    years = s.years(a.category)
    start, basis = a.purchase_date, "purchase"
    if not start and a.mdm_enrolled:
        start, basis, a.estimated = a.mdm_enrolled.date(), "enrolment (estimated)", True
    cands = []
    if years and start:
        cands.append((add_years(start, years), f"{basis} + {years:g} y"))
    if a.eos and a.category in COMMS_CATEGORIES:
        cands.append((a.eos, "end of support"))
    if cands:
        a.replace_on, a.basis = min(cands)
    elif years:
        a.basis = "no purchase date"


def _seen_days(d: Data, a: Asset) -> int | None:
    return days(a.mdm_last.date(), d.today) if a.mdm_last else None


# ---------------------------------------------------------------- 1. coverage

def coverage(d: Data, inv: dict) -> list[dict]:
    s, rows = d.settings, []
    extra = defaultdict(list)
    for a, src, got, expected in inv["mismatch"]:
        extra[a.key].append(Issue(WARNING, "COV-03", f"{a.label}: model {got} in {src}, {expected} in the inventory: wrong serial on one of the records"))
    for a in inv["assets"]:
        if a.category in COMMS_CATEGORIES and "Device42" in a.sources:
            continue
        iss = []
        mdm = "/".join(x for x in a.sources if x in ("Intune", "Jamf"))
        seen = _seen_days(d, a)
        if a.bad_serial:
            iss.append(Issue(WARNING, "COV-03", f"{a.label}: {mdm} reports the serial as '{a.bad_serial}' ({a.model}): it cannot be matched to the "
                                                 "inventory; read it from the label or the BIOS and add it to the register"))
        elif not a.inventoried:
            iss.append(Issue(WARNING, "COV-01", f"{a.label}: {a.category} {a.model} in {mdm} (user {a.owner or 'none'}, last sync {_d(a.mdm_last)}) "
                                                 "but in no inventory record: not in the register, not in the purchases"))
        if a.category in MDM_CATEGORIES and a.state == "deployed" and a.inventoried:
            if seen is None:
                iss.append(Issue(WARNING, "COV-02", f"{a.label}: {a.category} {a.model} deployed in the inventory but never seen in Intune or Jamf"
                                                     + (f" (bought {_d(a.purchase_date)}, order {a.order})" if a.order else "")))
            elif seen > s.not_seen_days:
                iss.append(Issue(WARNING, "COV-02", f"{a.label}: {a.category} of {a.owner or 'nobody'} last seen in {mdm} {seen} days ago ({_d(a.mdm_last)})"))
        if a.mdm_records > 1:
            iss.append(Issue(INFO, "COV-03", f"{a.label}: {a.mdm_records} MDM records for the same serial (re-enrolled); delete the stale one"))
        for what, dup in (("register", inv["dup_register"]), ("purchase", inv["dup_purchase"])):
            if a.key in dup:
                iss.append(Issue(WARNING, "COV-03", f"{a.label}: serial on {len(dup[a.key])} {what} lines ({', '.join(dup[a.key])})"))
        iss += extra.get(a.key, [])
        if a.state in ("deployed", "in repair"):
            miss = [w for w, v in (("owner", a.owner), ("site", a.site)) if not v]
            if miss:
                iss.append(Issue(WARNING, "COV-04", f"{a.label}: {a.category} {a.model} without {' and '.join(miss)}"))
        if iss:
            rows.append(_row(asset=a, issues=iss))
    return sorted(rows, key=lambda r: (ORDER.get(r["severity"], 3), min(i.code for i in r["issues"]), r["asset"].site, r["asset"].label))


# ---------------------------------------------------------------- 2. comms rooms

def comms(d: Data, inv: dict) -> list[dict]:
    s, today, rows = d.settings, d.today, []
    for a in inv["assets"]:
        if "Device42" not in a.sources or a.state == "retired":
            continue
        iss = []
        crit_sl = _norm(a.service_level) in s.critical_service_levels or any(c and c in _norm(a.service_level) for c in s.critical_service_levels)
        if a.eos:
            left = days(today, a.eos)
            if left < 0:
                iss.append(Issue(CRITICAL if a.category in NETWORK_CATEGORIES or crit_sl else WARNING, "CR-01",
                                 f"{a.name}: {a.model} past end of support since {_d(a.eos)} ({-left} days): no fixes or security patches"))
            elif left <= s.eos_warn_days:
                iss.append(Issue(INFO, "CR-01", f"{a.name}: {a.model} end of support on {_d(a.eos)} ({left} days)"))
        if a.warranty_end:
            left = days(today, a.warranty_end)
            if left < 0:
                iss.append(Issue(WARNING if a.category not in ("pdu", "patch panel") else INFO, "CR-02", f"{a.name}: out of warranty since {_d(a.warranty_end)}"
                                                   + (" and no end of support recorded" if not a.eos and a.category in NETWORK_CATEGORIES + ("server", "storage") else "")))
            elif left <= s.warranty_warn_days:
                sev = CRITICAL if crit_sl and left <= s.warranty_critical_days else WARNING
                iss.append(Issue(sev, "CR-02", f"{a.name}: warranty ends {_d(a.warranty_end)} ({left} days)"
                                               + (f", service level {a.service_level}" if a.service_level else "")))
        elif a.category not in ("patch panel",):
            iss.append(Issue(INFO, "CR-02", f"{a.name}: no warranty end date in Device42 or in the purchases"))
        if a.category in s.rack_categories and (not a.rack or not a.position):
            iss.append(Issue(WARNING, "CR-03", f"{a.name}: {a.category} in {a.room or '?'} with no " + ("rack" if not a.rack else "U position")))
        if not a.owner:
            iss.append(Issue(WARNING, "CR-03", f"{a.name}: {a.category} with no owner (customer) in Device42"))
        if a.category in NETWORK_CATEGORIES + ("server", "storage") and not a.os_version:
            iss.append(Issue(WARNING, "CR-04", f"{a.name}: {a.model} with no OS or firmware version in Device42: advisories cannot be matched"))
        if a.category in NETWORK_CATEGORIES and not a.eos:
            iss.append(Issue(INFO, "CR-04", f"{a.name}: no end-of-support date recorded for {a.model}"))
        rows.append(_row(asset=a, issues=iss))
    return rows


# ---------------------------------------------------------------- 3. lifecycle

def lifecycle(d: Data, inv: dict) -> list[dict]:
    s, today, rows = d.settings, d.today, []
    horizon = quarter_end(today, 2)
    for a in inv["assets"]:
        iss = []
        if a.state in ("deployed", "in repair", "to be retired") and a.replace_on:
            if a.replace_on <= today:
                iss.append(Issue(WARNING, "LCM-01", f"{a.label}: {a.category} {a.model} at {a.site or '?'} due for replacement on {_d(a.replace_on)} "
                                                     f"({a.basis}), {days(a.replace_on, today)} days overdue"))
            elif a.replace_on <= horizon:
                iss.append(Issue(INFO, "LCM-02", f"{a.label}: {a.category} at {a.site or '?'} due {_d(a.replace_on)} ({quarter(a.replace_on)})"))
        if a.state in ("deployed", "in repair") and a.basis == "no purchase date":
            iss.append(Issue(WARNING, "LCM-03", f"{a.label}: {a.category} {a.model} with no purchase or enrolment date: no replacement date"))
        if a.state == "retired" and a.mdm_last and days(a.mdm_last.date(), today) <= s.not_seen_days:
            iss.append(Issue(WARNING, "LCM-04", f"{a.label}: retired in the register but still syncing with {'/'.join(x for x in a.sources if x in ('Intune', 'Jamf'))} "
                                                 f"on {_d(a.mdm_last)} (user {a.owner or '?'})"))
        if a.state == "in stock" and a.replace_on and a.replace_on <= today:
            iss.append(Issue(INFO, "LCM-04", f"{a.label}: spare {a.category} past its replacement date ({_d(a.replace_on)}): retire it rather than deploy it"))
        if iss:
            rows.append(_row(asset=a, issues=iss))
    return sorted(rows, key=lambda r: (ORDER.get(r["severity"], 3), r["asset"].replace_on or date.max, r["asset"].label))


def state_counts(inv: dict) -> dict:
    c = defaultdict(Counter)
    for a in inv["assets"]:
        c[a.category][a.state] += 1
    return {k: {st: c[k][st] for st in STATES} for k in sorted(c, key=lambda x: COMMS_ORDER.get(x, 99))}


# ---------------------------------------------------------------- 4. people

def assigned(inv: dict) -> dict[str, list[Asset]]:
    out = defaultdict(list)
    for a in inv["assets"]:
        if "@" in a.owner and a.state in ("deployed", "in repair", "to be retired"):
            out[key(a.owner)].append(a)
    return out


def people(d: Data, inv: dict) -> list[dict]:
    s, today, rows = d.settings, d.today, []
    by = assigned(inv)
    known = set()
    for p in d.people:
        k = key(p.upn)
        known.add(k)
        items = by.get(k, [])
        iss = []
        who = f"{p.name} ({p.upn})"
        if p.left(today) and items:
            gone = days(p.end, today) if p.end else None
            after = [a for a in items if a.mdm_last and p.end and a.mdm_last.date() > p.end]
            txt = f"{who}: left {_d(p.end)}, still assigned {', '.join(f'{a.category} {a.label}' for a in items)}"
            if after:
                txt += "; still syncing after leaving: " + ", ".join(f"{a.label} on {_d(a.mdm_last)}" for a in after)
            if gone is None or gone > s.leaver_return_days:
                iss.append(Issue(CRITICAL, "PPL-02", txt + (f"; not returned {gone} days after leaving" if gone is not None else "")))
            else:
                iss.append(Issue(WARNING, "PPL-01", txt + f"; return due by {_d(p.end + timedelta(days=s.leaver_return_days))}"))
        if not p.left(today):
            cnt = Counter(a.category for a in items)
            over = [c for c, n in sorted(cnt.items()) if c in s.max_per_person and n > int(s.max_per_person[c])]
            if over:
                iss.append(Issue(WARNING, "PPL-03", f"{who}: " + "; ".join(f"{cnt[c]} {c}s (policy {int(s.max_per_person[c])}): "
                                                                          + ", ".join(a.label for a in items if a.category == c) for c in over)))
        if s.computer_required and p.active(today) and not any(a.category in ("laptop", "desktop") for a in items):
            iss.append(Issue(WARNING, "PPL-04", f"{who}: active at {p.site or '?'} since {_d(p.start)} with no laptop or desktop assigned"))
        rows.append(_row(person=p, items=items, issues=iss))
    if d.people:
        for k, items in sorted(by.items()):
            if k not in known:
                rows.append(_row(person=None, upn=k, items=items, issues=[Issue(WARNING, "PPL-05", f"{k}: {_n(len(items), 'device')} assigned to someone "
                                                                                                f"not in the HR roster: {_top([a.label for a in items], 3)}")]))
    return sorted(rows, key=lambda r: (ORDER.get(r["severity"], 3), r["person"].site if r["person"] else "", r["person"].name if r["person"] else r["upn"]))


# ---------------------------------------------------------------- 5. stock

def stock(d: Data, inv: dict) -> list[dict]:
    s, today = d.settings, d.today
    nq = quarter_end(today, 1)
    need, backlog = Counter(), Counter()
    for a in inv["assets"]:
        if a.category not in s.stock_categories or not a.replace_on or a.state not in ("deployed", "in repair", "to be retired"):
            continue
        if a.replace_on <= today:
            backlog[(a.site, a.category)] += 1
        elif a.replace_on <= nq:
            need[(a.site, a.category)] += 1
    lines = {(x.site, x.category): x for x in d.stock}
    rows = []
    for site, cat in sorted(set(lines) | {k for k in need if k[0]}, key=lambda k: (k[0], COMMS_ORDER.get(k[1], 99))):
        x = lines.get((site, cat))
        on, mn, n = (x.on_hand if x else 0), (x.minimum if x else 0), need[(site, cat)]
        iss = []
        if x and on < mn:
            iss.append(Issue(CRITICAL if on == 0 else WARNING, "STK-01", f"{site} · {cat}: {on} in stock, minimum {mn}"))
        order = max(0, n + mn - on)
        if n and on - mn < n:
            iss.append(Issue(WARNING, "STK-02", f"{site} · {cat}: {_n(n, 'replacement')} due by {_d(nq)}, {max(0, on - mn)} above the minimum in stock: "
                                                 f"order {order}" + (f" (plus {backlog[(site, cat)]} overdue in the backlog)" if backlog[(site, cat)] else "")
                                                 + ("" if x else "; no stock line for this item")))
        rows.append(_row(site=site, category=cat, model=x.model if x else "", on_hand=on, minimum=mn, need=n, backlog=backlog[(site, cat)],
                         order=order, issues=iss))
    return rows


# ---------------------------------------------------------------- 6. forecast

def buckets(d: Data) -> list[str]:
    today = d.today
    out = ["overdue", quarter(today)]
    q = quarter_end(today, 0)
    for _ in range(d.settings.forecast_quarters):
        q = quarter_end(q + timedelta(days=1), 0)
        out.append(quarter(q))
    return out


def bucket_of(d: Data, when: date) -> str | None:
    if when <= d.today:
        return "overdue"
    b = quarter(when)
    return b if b in buckets(d) else None


def forecast(d: Data, inv: dict) -> dict:
    s = d.settings
    lines = defaultdict(lambda: [0, 0.0, 0])        # (bucket, site, category) -> units, cost, estimated
    for a in inv["assets"]:
        if a.state not in ("deployed", "in repair", "to be retired") or not a.replace_on:
            continue
        b = bucket_of(d, a.replace_on)
        if not b:
            continue
        c = s.cost(a.category)
        if not c:
            continue
        x = lines[(b, a.site or "?", a.category)]
        x[0] += 1
        x[1] += c
        x[2] += a.estimated
    rows = [dict(bucket=b, site=site, category=cat, units=v[0], cost=v[1], estimated=v[2], unit_cost=s.cost(cat))
            for (b, site, cat), v in lines.items()]
    order = {b: i for i, b in enumerate(buckets(d))}
    rows.sort(key=lambda r: (order[r["bucket"]], r["site"], COMMS_ORDER.get(r["category"], 99)))
    tot = {b: dict(units=sum(r["units"] for r in rows if r["bucket"] == b), cost=sum(r["cost"] for r in rows if r["bucket"] == b)) for b in buckets(d)}
    return dict(rows=rows, totals=tot, buckets=buckets(d))


# ---------------------------------------------------------------- run

def review(d: Data) -> dict:
    inv = inventory(d)
    return dict(inv=inv, coverage=coverage(d, inv), comms=comms(d, inv), lifecycle=lifecycle(d, inv), people=people(d, inv), stock=stock(d, inv),
                forecast=forecast(d, inv))


CODES = {  # code: (area, owner key, subject, next step)
    "COV-01": ("Coverage", "coverage", "devices in Intune or Jamf missing from the inventory",
               "Find the order or the receipt, add each device to the register with its asset tag, and fix the buying route that skipped the register."),
    "COV-02": ("Coverage", "coverage", "inventory devices not seen in MDM within the policy",
               "Ask the user or the site: in a drawer, broken, lost or never enrolled. Recover it, enrol it, or record it as lost and wipe it."),
    "COV-03": ("Coverage", "coverage", "duplicate or mismatched serial numbers",
               "Check the label on the device, correct the wrong record and delete stale MDM records after a re-enrolment."),
    "COV-04": ("Coverage", "coverage", "items without an owner or a site",
               "Record who has it or the room it is in; an item nobody owns is the first one to disappear."),
    "CR-01": ("Comms rooms", "comms", "comms room devices past end of support",
              "Plan the replacement in a change window now; until then, restrict management access and watch the vendor's advisories."),
    "CR-02": ("Comms rooms", "comms", "comms room warranties ended or ending soon",
              "Renew the support contract before the end date (or confirm the replacement date), and keep the contract number in Device42."),
    "CR-03": ("Comms rooms", "comms", "comms room devices without rack position or owner",
              "Walk the room, record the rack and U position and the owner (customer) of each device in Device42."),
    "CR-04": ("Comms rooms", "comms", "OS or firmware not recorded in Device42",
              "Record the running version (show version, iDRAC/iLO) or let discovery fill it, so advisories can be matched to devices."),
    "LCM-01": ("Lifecycle", "lifecycle", "replacements overdue",
               "Schedule the overdue replacements with the users, oldest and out-of-warranty first, and fund them as backlog."),
    "LCM-02": ("Lifecycle", "lifecycle", "replacements due in the next two quarters",
               "Order with the lead time in mind and book the deployment slots with the users."),
    "LCM-03": ("Lifecycle", "lifecycle", "items without a purchase date",
               "Find the order in the vendor portal by serial (service tag) and add the date; without it there is no replacement date."),
    "LCM-04": ("Lifecycle", "lifecycle", "state inconsistencies (retired but syncing, old spares)",
               "Find the retired device still syncing and wipe or retire it in MDM; take old spares out of stock."),
    "PPL-01": ("People", "people", "devices assigned to leavers, return pending",
               "Book the return with the leaver's manager before the deadline."),
    "PPL-02": ("People", "people", "leavers with devices not returned",
               "Escalate to the manager and HR, lock or wipe the device in MDM, and record it as lost if it does not come back."),
    "PPL-03": ("People", "people", "people with more devices than the policy allows",
               "Recover the extra device (often the old one after a refresh) and put it back in stock or retire it."),
    "PPL-04": ("People", "people", "active people with no laptop or desktop",
               "Check with the manager: a shared desk, a device under someone else's name, or a joiner waiting for kit."),
    "PPL-05": ("People", "people", "devices assigned to people not in HR",
               "Correct the user on the record (contractor, shared mailbox, typo) or recover the device."),
    "STK-01": ("Stock", "stock", "stock below the minimum",
               "Order to the minimum, or move spares from another site."),
    "STK-02": ("Stock", "stock", "stock short of next quarter's replacements",
               "Place the order now with the vendor's lead time, sized for the replacements plus the minimum."),
    "FC-02": ("Forecast", "forecast", "a refresh wave in one quarter",
              "Spread the wave: start part of it a quarter earlier, or agree the budget and the deployment capacity for that quarter now."),
}


def run_all(d: Data, rv: dict | None = None) -> list[Finding]:
    rv = rv if rv is not None else review(d)
    s = d.settings
    out: list[Finding] = []
    hits = defaultdict(list)
    for name in ("coverage", "comms", "lifecycle", "people", "stock"):
        for r in rv[name]:
            for i in r["issues"]:
                hits[i.code].append(i)
    for code, (area, owner, subject, fix) in CODES.items():
        for sev in (CRITICAL, WARNING, INFO):
            xs = list({i.text: i for i in hits.get(code, []) if i.severity == sev}.values())
            if not xs:
                continue
            word = "line" if code.startswith("STK") else "person" if code in ("PPL-01", "PPL-02", "PPL-03", "PPL-04", "PPL-05") else "item"
            plural = "people" if word == "person" else None
            subj = f"{_n(len(xs), word, plural)}: {subject}" if sev != INFO else f"{_n(len(xs), word, plural)} for information ({code})"
            out.append(Finding(sev, area, code, subj, _top([i.text for i in xs], 8, "; "),
                               fix if sev != INFO else "No action unless it changes before the next review.", s.owner(owner),
                               [i.text.split(":")[0] for i in xs]))
    fc = rv["forecast"]
    qs = fc["buckets"][2:]
    total = sum(fc["totals"][b]["cost"] for b in qs)
    if total:
        peak = max(qs, key=lambda b: fc["totals"][b]["cost"])
        share = fc["totals"][peak]["cost"] / total
        cats = Counter()
        for r in fc["rows"]:
            if r["bucket"] == peak:
                cats[r["category"]] += r["units"]
        if share >= s.wave_share:
            out.append(Finding(WARNING, "Forecast", "FC-02", f"Refresh wave in {peak}: {share:.0%} of the next {len(qs)} quarters' cost",
                               f"{fc['totals'][peak]['units']} items, {money(d, fc['totals'][peak]['cost'])} in {peak}: " +
                               ", ".join(f"{n} {c}" for c, n in cats.most_common()), CODES["FC-02"][3], s.owner("forecast")))
        bl = fc["totals"]["overdue"]
        cur = fc["totals"][fc["buckets"][1]]
        out.append(Finding(INFO, "Forecast", "FC-01", f"Next {len(qs)} quarters: {money(d, total)} for {sum(fc['totals'][b]['units'] for b in qs)} replacements",
                           f"Backlog (overdue) {bl['units']} items, {money(d, bl['cost'])}; rest of {fc['buckets'][1]}: {cur['units']} items, "
                           f"{money(d, cur['cost'])}; " + "; ".join(f"{b}: {fc['totals'][b]['units']} items, {money(d, fc['totals'][b]['cost'])}" for b in qs),
                           "Take forecast.csv to the budget review.", s.owner("forecast")))
    sm = summary(d, rv)
    out.append(Finding(INFO, "Coverage", "MET-01", f"{sm['items']} items in one inventory, {sm['inventoried']} with an inventory record",
                       f"{sm['comms']} in Device42, {sm['register']} in the office register, {sm['purchased']} in the purchases, {sm['mdm']} seen in MDM; "
                       f"{sm['personal']} personal (BYOD) devices left out", "Track the trend month by month.", s.owner("coverage")))
    out.sort(key=lambda f: (ORDER[f.severity], AREAS.index(f.area), f.code))
    return out


def summary(d: Data, rv: dict) -> dict:
    inv = rv["inv"]
    A = inv["assets"]
    has = lambda name, c, sev=None: sum(1 for r in rv[name] if any(i.code == c and (i.severity == sev if sev else i.severity != INFO) for i in r["issues"]))  # noqa: E731
    fc = rv["forecast"]
    qs = fc["buckets"][2:]
    return dict(
        items=len(A), inventoried=sum(a.inventoried for a in A), comms=sum("Device42" in a.sources for a in A),
        register=sum("Register" in a.sources for a in A), purchased=sum("Purchases" in a.sources for a in A),
        mdm=sum(any(x in a.sources for x in ("Intune", "Jamf")) for a in A), personal=len(inv["personal"]),
        sites=sorted({a.site for a in A if a.site}),
        not_in_inventory=has("coverage", "COV-01"), not_seen=has("coverage", "COV-02"), serial_issues=has("coverage", "COV-03"),
        no_owner=has("coverage", "COV-04"),
        eos=has("comms", "CR-01", CRITICAL) + has("comms", "CR-01", WARNING), warranty_soon=sum(1 for r in rv["comms"] for i in r["issues"]
                                                                                              if i.code == "CR-02" and i.severity != INFO and "ends" in i.text),
        warranty_ended=sum(1 for r in rv["comms"] for i in r["issues"] if i.code == "CR-02" and i.severity != INFO and "since" in i.text),
        no_rack=has("comms", "CR-03"), no_firmware=has("comms", "CR-04"),
        overdue=has("lifecycle", "LCM-01"), due_soon=has("lifecycle", "LCM-02", INFO), no_date=has("lifecycle", "LCM-03"),
        states=Counter(a.state for a in A),
        leavers_pending=has("people", "PPL-01"), leavers_kept=has("people", "PPL-02"), over_policy=has("people", "PPL-03"),
        no_computer=has("people", "PPL-04"), leaver_devices=sum(len(r["items"]) for r in rv["people"] if any(i.code in ("PPL-01", "PPL-02") for i in r["issues"])),
        below_min=has("stock", "STK-01"), to_order=sum(r["order"] for r in rv["stock"]),
        backlog_units=fc["totals"]["overdue"]["units"], backlog_cost=fc["totals"]["overdue"]["cost"],
        next_units=sum(fc["totals"][b]["units"] for b in qs), next_cost=sum(fc["totals"][b]["cost"] for b in qs),
        current_units=fc["totals"][fc["buckets"][1]]["units"], current_cost=fc["totals"][fc["buckets"][1]]["cost"],
    )


def area_status(findings: list[Finding]) -> dict[str, str]:
    st = {}
    for a in AREAS:
        sev = [f.severity for f in findings if f.area == a and f.severity != INFO]
        st[a] = CRITICAL if CRITICAL in sev else WARNING if sev else "ok"
    return st


def overall(findings: list[Finding]) -> str:
    st = set(area_status(findings).values())
    return VERDICT[CRITICAL] if CRITICAL in st else VERDICT[WARNING] if WARNING in st else VERDICT[None]


def now_label(when: datetime) -> str:
    return f"{when:%a %d %b %Y}"


__all__ = ["AREAS", "CRITICAL", "WARNING", "INFO", "Asset", "Finding", "Issue", "review", "run_all", "summary", "area_status", "overall"]
