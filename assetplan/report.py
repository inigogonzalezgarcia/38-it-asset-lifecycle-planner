"""Outputs: report.html, asset-review.md (the pack for the monthly asset review, with the forecast ready for the budget), and the CSVs: the
one inventory, coverage, comms rooms, lifecycle, people, stock plan, forecast, actions and findings."""
from __future__ import annotations

import csv
import html
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

from .checks import (AREAS, COMMS_ORDER, CRITICAL, INFO, VERDICT, WARNING, Finding, _n, area_status, money, now_label, overall, state_counts,
                     summary)
from .model import STATES, Data, days, quarter_end

e = html.escape


# ---------------------------------------------------------------- csv

def _w(path: Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def _t(v) -> str:
    if not v:
        return ""
    return v.strftime("%Y-%m-%d %H:%M") if isinstance(v, datetime) else v.strftime("%Y-%m-%d")


def _iss(r: dict) -> str:
    return " | ".join(f"{i.code} {i.text}" for i in r["issues"])


def _c(v) -> str:
    return "" if v is None else f"{v:.2f}"


def write_findings(findings: list[Finding], path: Path) -> None:
    _w(path, ["severity", "area", "code", "subject", "detail", "next_step", "owner", "items"],
       [[f.severity, f.area, f.code, f.subject, f.detail, f.fix, f.owner, "; ".join(f.items)] for f in findings])


def write_actions(findings: list[Finding], path: Path) -> None:
    _w(path, ["ref", "action", "next_step", "owner", "severity", "due", "done"],
       [[f.code, f.subject, f.fix, f.owner, f.severity, "", ""] for f in findings if f.severity != INFO])


ASSET_HEAD = ["key", "serial", "name", "asset_tag", "category", "model", "manufacturer", "sources", "site", "room", "rack", "u_position", "owner",
              "state", "purchase_date", "warranty_end", "end_of_support", "replace_on", "replace_basis", "estimated", "unit_cost", "order", "vendor",
              "mdm_last_seen", "compliance", "os", "os_version"]


def _asset(a) -> list:
    return [a.key, a.serial, a.name, a.asset_tag, a.category, a.model, a.manufacturer, "; ".join(a.sources), a.site, a.room, a.rack, a.position, a.owner,
            a.state, _t(a.purchase_date), _t(a.warranty_end), _t(a.eos), _t(a.replace_on), a.basis, "yes" if a.estimated else "", _c(a.cost), a.order,
            a.vendor, _t(a.mdm_last), a.compliance, a.os, a.os_version]


def write_inventory(d: Data, rv: dict, path: Path) -> None:
    _w(path, ASSET_HEAD, [_asset(a) for a in rv["inv"]["assets"]])


def write_coverage(d: Data, rv: dict, path: Path) -> None:
    _w(path, ["serial", "name", "category", "model", "sources", "owner", "site", "state", "mdm_last_seen", "days_not_seen", "verdict", "issues"],
       [[r["asset"].serial, r["asset"].name or r["asset"].asset_tag, r["asset"].category, r["asset"].model, "; ".join(r["asset"].sources), r["asset"].owner,
         r["asset"].site, r["asset"].state, _t(r["asset"].mdm_last), days(r["asset"].mdm_last.date(), d.today) if r["asset"].mdm_last else "", r["verdict"],
         _iss(r)] for r in rv["coverage"]])


def write_comms(d: Data, rv: dict, path: Path) -> None:
    _w(path, ["name", "serial", "category", "model", "manufacturer", "site", "room", "rack", "u_position", "owner", "service_level", "os", "os_version",
              "purchase_date", "warranty_end", "warranty_days_left", "end_of_support", "eos_days_left", "replace_on", "verdict", "issues"],
       [[a.name, a.serial, a.category, a.model, a.manufacturer, a.site, a.room, a.rack, a.position, a.owner, a.service_level, a.os, a.os_version,
         _t(a.purchase_date), _t(a.warranty_end), days(d.today, a.warranty_end) if a.warranty_end else "", _t(a.eos),
         days(d.today, a.eos) if a.eos else "", _t(a.replace_on), r["verdict"], _iss(r)] for r in rv["comms"] for a in [r["asset"]]])


def write_lifecycle(d: Data, rv: dict, path: Path) -> None:
    _w(path, ["serial", "name", "category", "model", "site", "owner", "state", "purchase_date", "replace_on", "basis", "estimated", "quarter",
              "days_overdue", "unit_cost", "issues"],
       [[a.serial, a.name or a.asset_tag, a.category, a.model, a.site, a.owner, a.state, _t(a.purchase_date), _t(a.replace_on), a.basis,
         "yes" if a.estimated else "", _q(d, a.replace_on), max(0, days(a.replace_on, d.today)) if a.replace_on else "", f"{d.settings.cost(a.category):.0f}",
         _iss(r)] for r in rv["lifecycle"] for a in [r["asset"]]])


def _q(d: Data, when: date | None) -> str:
    if not when:
        return ""
    return "overdue" if when <= d.today else f"Q{(when.month - 1) // 3 + 1}-{when.year}"


def write_people(d: Data, rv: dict, path: Path) -> None:
    out = []
    for r in rv["people"]:
        p = r["person"]
        cnt = Counter(a.category for a in r["items"])
        out.append([p.employee_id if p else "", p.name if p else "", p.upn if p else r["upn"], p.site if p else "", p.status if p else "not in HR",
                    _t(p.start) if p else "", _t(p.end) if p else "", len(r["items"]), "; ".join(f"{n} {c}" for c, n in sorted(cnt.items())),
                    "; ".join(a.label for a in r["items"]), r["verdict"], _iss(r)])
    _w(path, ["employee_id", "name", "upn", "site", "status", "start_date", "leave_date", "devices", "by_category", "assigned", "verdict", "issues"], out)


def write_stock(d: Data, rv: dict, path: Path) -> None:
    _w(path, ["site", "category", "model", "on_hand", "minimum", "due_by_end_of_next_quarter", "overdue_backlog", "to_order", "verdict", "issues"],
       [[r["site"], r["category"], r["model"], r["on_hand"], r["minimum"], r["need"], r["backlog"], r["order"], r["verdict"], _iss(r)] for r in rv["stock"]])


def write_forecast(d: Data, rv: dict, path: Path) -> None:
    _w(path, ["bucket", "site", "category", "units", "unit_cost", "cost", "estimated_dates"],
       [[r["bucket"], r["site"], r["category"], r["units"], f"{r['unit_cost']:.0f}", f"{r['cost']:.0f}", r["estimated"]] for r in rv["forecast"]["rows"]])


# ---------------------------------------------------------------- the monthly pack

TODO = "**[TO COMPLETE]**"


def _label(b: str, d: Data) -> str:
    return "Overdue (backlog)" if b == "overdue" else f"{b} (rest)" if b == rv_current(d) else b


def rv_current(d: Data) -> str:
    return f"Q{(d.today.month - 1) // 3 + 1}-{d.today.year}"


def _matrix(rv: dict) -> tuple[list[str], dict]:
    fc = rv["forecast"]
    m = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
    for r in fc["rows"]:
        m[r["category"]][r["bucket"]][0] += r["units"]
        m[r["category"]][r["bucket"]][1] += r["cost"]
    cats = sorted(m, key=lambda c: COMMS_ORDER.get(c, 99))
    return cats, m


def pack_md(d: Data, rv: dict, findings: list[Finding], title: str) -> str:
    s, sm, st = d.settings, summary(d, rv), area_status(findings)
    fc = rv["forecast"]
    qs = fc["buckets"]
    out = [f"# {title}", "",
           f"> Generated by assetplan on {now_label(d.as_of)} from the exports listed under *Scope and evidence*. Read-only: nothing was changed in "
           f"Device42, Intune or Jamf Pro. Sections marked {TODO} are for the site IT lead before the pack is shared.", "",
           f"**Overall: {overall(findings).upper()}**", "",
           "| Area | Status | To act on |", "|---|---|---|"]
    for a in AREAS:
        n = sum(f.area == a and f.severity != INFO for f in findings)
        out.append(f"| {a} | {'ON TRACK' if st[a] == 'ok' else VERDICT[st[a]].upper()} | {n} |")
    out += ["", "## Headlines", "",
            f"- One inventory: {sm['items']} items across {', '.join(sm['sites'])} ({sm['comms']} in Device42, {sm['register']} in the office register, "
            f"{sm['purchased']} in the purchases, {sm['mdm']} seen in Intune or Jamf); {sm['personal']} personal devices left out.",
            f"- Coverage: {_n(sm['not_in_inventory'], 'device')} in MDM with no inventory record, {sm['not_seen']} not seen for {s.not_seen_days}+ days, "
            f"{sm['serial_issues']} with duplicate or mismatched serials, {sm['no_owner']} without owner or site.",
            f"- Comms rooms: {_n(sm['eos'], 'device')} past end of support, {sm['warranty_soon']} warranties ending within {s.warranty_warn_days} days, "
            f"{sm['warranty_ended']} ended; {sm['no_rack']} without rack position or owner, {sm['no_firmware']} without firmware recorded.",
            f"- Lifecycle: {sm['overdue']} replacements overdue, {sm['due_soon']} due in the next two quarters, {sm['no_date']} without a purchase date.",
            f"- People: {_n(sm['leavers_kept'], 'leaver')} with devices not returned after {s.leaver_return_days} days and {sm['leavers_pending']} pending, "
            f"{sm['over_policy']} over the device policy, {sm['no_computer']} active without a computer.",
            f"- Stock: {_n(sm['below_min'], 'line')} below the minimum; {sm['to_order']} units to order for the replacements due by "
            f"{quarter_end(d.today, 1):%d %b %Y}.",
            f"- Forecast: backlog {money(d, sm['backlog_cost'])} ({sm['backlog_units']} items); rest of {qs[1]} {money(d, sm['current_cost'])}; next "
            f"{len(qs) - 2} quarters {money(d, sm['next_cost'])} ({sm['next_units']} items).", "",
            "## Scope and evidence", "", f"- Organisation: {s.organisation}", f"- Reference date: {d.today:%d %b %Y}", "",
            "| Source | File | Records |", "|---|---|---|"]
    from .model import FILES
    out += [f"| {FILES.get(k, k)} | `{k}` | {v} |" for k, v in d.sources.items()]
    out += ["", "## Refresh policy (from `settings.json`)", "", "| Category | Replace after | Unit cost |", "|---|---|---|"]
    for c in sorted({a.category for a in rv["inv"]["assets"]}, key=lambda c: COMMS_ORDER.get(c, 99)):
        y = s.years(c)
        extra = " or end of support, whichever first" if c in ("switch", "router", "firewall", "server", "storage") else " (batteries)" if c == "ups" else ""
        out.append(f"| {c} | {f'{y:g} years' if y else 'not replaced on age'}{extra} | {money(d, s.cost(c))} |")
    out += ["", "## Forecast for the budget", "",
            "Replacement cost by category and quarter, from the refresh policy and the unit costs. The backlog is what is already overdue and is not "
            "in any quarter.", ""]
    cats, m = _matrix(rv)
    out.append("| Category | " + " | ".join(_label(b, d) for b in qs) + " |")
    out.append("|---|" + "---|" * len(qs))
    for c in cats:
        out.append(f"| {c} | " + " | ".join(f"{m[c][b][0]} · {money(d, m[c][b][1])}" if m[c][b][0] else "–" for b in qs) + " |")
    out.append("| **Total** | " + " | ".join(f"**{fc['totals'][b]['units']} · {money(d, fc['totals'][b]['cost'])}**" for b in qs) + " |")
    out += ["", "By site:", "", "| Site | " + " | ".join(_label(b, d) for b in qs) + " |", "|---|" + "---|" * len(qs)]
    bysite = defaultdict(lambda: defaultdict(float))
    for r in fc["rows"]:
        bysite[r["site"]][r["bucket"]] += r["cost"]
    for site in sorted(bysite):
        out.append(f"| {site} | " + " | ".join(money(d, bysite[site][b]) if bysite[site][b] else "–" for b in qs) + " |")
    est = sum(r["estimated"] for r in fc["rows"])
    if est:
        out += ["", f"{est} of the items have no purchase record: their date is estimated from the MDM enrolment date."]
    out += ["", "## Stock orders", "", "| Site | Category | On hand | Minimum | Due by end of next quarter | Overdue backlog | To order |",
            "|---|---|---|---|---|---|---|"]
    out += [f"| {r['site']} | {r['category']} | {r['on_hand']} | {r['minimum']} | {r['need']} | {r['backlog']} | {r['order']} |" for r in rv["stock"]]
    out += ["", "## Findings", ""]
    for f in findings:
        if f.severity == INFO:
            continue
        out += [f"### {f.code} · {f.subject} ({f.severity})", "", f.detail.replace("|", "/"), "", f"Next step: {f.fix} Owner: {f.owner}.", ""]
    out += ["## Actions", "", "| Ref | Action | Next step | Owner | Due |", "|---|---|---|---|---|"]
    out += [f"| {f.code} | {f.subject} | {f.fix} | {f.owner} | {TODO if f.severity == CRITICAL else ''} |" for f in findings if f.severity != INFO]
    out += ["", "## Notes", "",
            "- Device42 covers the comms rooms only; the office hardware comes from the purchases, the office register and MDM, joined by serial number.",
            "- MDM last sync: a laptop that has not synced for weeks may be in a drawer, broken, lost or with a leaver; the CSV lists each one.",
            "- Replacement dates are purchase date plus the policy years, or the end-of-support date for comms room equipment when it comes first. "
            "Items with no purchase record use the MDM enrolment date, marked as estimated.",
            f"- Decisions and accepted risks: {TODO}", "",
            "## Sign-off", "", f"- Prepared by (site IT): {TODO}", f"- Reviewed by (IT budget owner): {TODO}", f"- Date: {TODO}", ""]
    return "\n".join(out)


# ---------------------------------------------------------------- html

CSS = """
:root{--bg:#f6f7f8;--card:#fff;--ink:#1b2128;--muted:#66717c;--line:#e2e5e9;--ok:#1e7a4c;--warn:#a46200;--bad:#b42318;--info:#0b6bcb;--bar:#3d6fb4}
@media (prefers-color-scheme:dark){:root{--bg:#13171b;--card:#1b2127;--ink:#e7eaee;--muted:#9aa5b0;--line:#2b333b;--ok:#4cc38a;--warn:#f0a83a;--bad:#f2685c;--info:#5aa9f0;--bar:#6c9be0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 12px}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile b{display:block;font-size:26px}
.overall{display:inline-block;margin-top:14px;padding:6px 14px;border-radius:99px;font-weight:700;border:2px solid currentColor}
.areas{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.area{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--ok);border-radius:10px;padding:10px 14px}
.area.critical{border-left-color:var(--bad)}.area.warning{border-left-color:var(--warn)}
.area .lbl{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);margin-bottom:4px}.area .cnt{display:block;font-size:13px;color:var(--muted);margin-top:4px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.tot td{font-weight:700}
.pill{display:inline-block;white-space:nowrap;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.critical{color:var(--bad)}.warning{color:var(--warn)}.info{color:var(--info)}.ok{color:var(--ok)}
.area.critical,.area.warning,.area.ok{color:inherit}
.pill.on-track{color:var(--ok)}.pill.attention{color:var(--warn)}.pill.action-needed{color:var(--bad)}
td.subj{min-width:190px}td.nw{white-space:nowrap}td.fix{font-size:13px;color:var(--muted);min-width:200px;max-width:380px}td.sm{font-size:13px}
.brk{overflow-wrap:anywhere;word-break:break-word}
.bars{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;align-items:end;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 16px 12px;margin-bottom:12px}
.col{display:flex;flex-direction:column;align-items:stretch;text-align:center;font-size:13px}.col .b{background:var(--bar);border-radius:4px 4px 0 0;min-height:2px}
.col .b.over{background:var(--bad)}.col .v{font-variant-numeric:tabular-nums;font-weight:600;margin-bottom:4px}.col .k{color:var(--muted);margin-top:6px}
footer{margin-top:40px;font-size:13px}
"""


def _pill(cls: str, text: str) -> str:
    return f"<span class='pill {cls}'>{e(text)}</span>"


def _vpill(v: str) -> str:
    return _pill(v.replace(" ", "-"), v.upper())


def _issues(r: dict) -> str:
    xs = sorted(r["issues"], key=lambda x: (x.severity != CRITICAL, x.severity == INFO))
    return "<br>".join(f"<span class='{x.severity}'>●</span> <b>{e(x.code)}</b> {e(x.text)}" for x in xs) or "<span class='muted'>–</span>"


def _table(head: list[str], rows: list[str]) -> str:
    return "<div class='wrap'><table><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr>" + "".join(rows) + "</table></div>"


def _sect(h: list, n: int, title: str, area: str, st: dict, note: str) -> None:
    lab = "on track" if st[area] == "ok" else VERDICT[st[area]]
    h.append(f"<h2>{n}. {e(title)} {_vpill(lab)}</h2><p class='muted'>{e(note)}</p>")


def render_html(d: Data, rv: dict, findings: list[Finding], title: str) -> str:
    s, sm, st = d.settings, summary(d, rv), area_status(findings)
    ov = overall(findings)
    fc = rv["forecast"]
    qs = fc["buckets"]
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>One inventory of the comms rooms, the end-user devices and the office hardware · "
         f"{e(', '.join(sm['sites']))} · as of {now_label(d.as_of)}</p>",
         f"<span class='overall {'critical' if ov == 'action needed' else 'warning' if ov == 'attention' else 'ok'}'>Overall: {e(ov.upper())}</span>"
         "<div class='tiles'>"]
    tiles = [("Items", str(sm["items"]), f"{sm['inventoried']} with an inventory record"),
             ("Not in inventory", str(sm["not_in_inventory"]), "seen in Intune or Jamf"),
             ("Not seen", str(sm["not_seen"]), f"for {s.not_seen_days}+ days"),
             ("End of support", str(sm["eos"]), "comms room devices past it"),
             ("Warranty soon", str(sm["warranty_soon"]), f"within {s.warranty_warn_days} days"),
             ("Overdue", str(sm["overdue"]), f"backlog {money(d, sm['backlog_cost'])}"),
             ("Leavers' devices", str(sm["leaver_devices"]), f"{sm['leavers_kept']} leavers past {s.leaver_return_days} days"),
             ("Stock below min", str(sm["below_min"]), f"{sm['to_order']} units to order"),
             (f"Next {len(qs) - 2} quarters", money(d, sm["next_cost"]), f"{sm['next_units']} replacements")]
    h += [f"<div class='tile'><span class='muted'>{e(a)}</span><b>{e(x)}</b><span class='muted'>{e(y)}</span></div>" for a, x, y in tiles]
    h.append("</div><h2>Status by area</h2><div class='areas'>")
    for a in AREAS:
        n = sum(f.area == a and f.severity != INFO for f in findings)
        h.append(f"<div class='area {st[a]}'><span class='lbl'>{e(a)}</span>{_pill(st[a], 'ON TRACK' if st[a] == 'ok' else VERDICT[st[a]].upper())}"
                 f"<span class='cnt'>{n} to act on</span></div>")
    h.append("</div>")
    crit = [f for f in findings if f.severity == CRITICAL]
    if crit:
        h.append("<h2>Fix first</h2>")
        h.append(_table(["Subject", "What", "Next step", "Owner"],
                        [f"<tr><td class='subj'><b>{e(f.subject)}</b><br><span class='muted'>{e(f.area)} · {e(f.code)}</span></td><td class='sm'>{e(f.detail)}</td>"
                         f"<td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in crit]))
    # 1 coverage
    _sect(h, 1, "Coverage: one inventory", "Coverage", st,
          f"Devices in Intune or Jamf with no inventory record, inventory devices not seen in MDM for {s.not_seen_days}+ days, duplicate or mismatched "
          "serials, and items without owner or site. Every item is in inventory.csv.")
    h.append(_table(["Item", "Category", "Sources", "Owner · site", "Last MDM sync", "Issues"],
                    [f"<tr><td class='nw'><b>{e(a.name or a.asset_tag or a.serial)}</b><br><span class='muted'>{e(a.serial or '–')}</span></td>"
                     f"<td>{e(a.category)}<br><span class='muted'>{e(a.model)}</span></td><td class='sm'>{e(', '.join(a.sources))}</td>"
                     f"<td class='sm brk'>{e(a.owner or '–')}<br><span class='muted'>{e(a.site or 'no site')}</span></td><td class='nw'>{_t(a.mdm_last) or '–'}</td>"
                     f"<td class='sm'>{_issues(r)}</td></tr>" for r in rv["coverage"] for a in [r["asset"]]]))
    # 2 comms rooms
    _sect(h, 2, "Comms rooms (Device42)", "Comms rooms", st,
          "End of support and warranty, rack position and owner, and whether the firmware is recorded. Only devices with something to act on are listed; "
          "every Device42 device is in comms-rooms.csv.")
    rows = [r for r in rv["comms"] if r["severity"]]
    h.append(_table(["Device", "Model", "Location", "Owner", "Warranty", "End of support", "Status", "Issues"],
                    [f"<tr><td class='nw'><b>{e(a.name)}</b><br><span class='muted'>{e(a.category)}</span></td><td class='sm'>{e(a.model)}</td>"
                     f"<td class='sm'>{e(a.site)} · {e(a.room)}<br><span class='muted'>{e(a.rack or 'no rack')} · U{e(a.position or '?')}</span></td>"
                     f"<td class='sm'>{e(a.owner or '–')}</td><td class='nw'>{_t(a.warranty_end) or '–'}</td><td class='nw'>{_t(a.eos) or '–'}</td>"
                     f"<td>{_vpill(r['verdict'])}</td><td class='sm'>{_issues(r)}</td></tr>" for r in rows for a in [r["asset"]]]))
    # 3 lifecycle
    _sect(h, 3, "Lifecycle: state and replacement date", "Lifecycle", st,
          "Every item has one state and, where the policy replaces it on age, one replacement date. Overdue and due in the next two quarters by "
          "category; the list is in lifecycle.csv.")
    sc = state_counts(rv["inv"])
    horizon = quarter_end(d.today, 2)
    due = defaultdict(lambda: [0, 0])
    for r in rv["lifecycle"]:
        for i in r["issues"]:
            if i.code == "LCM-01":
                due[r["asset"].category][0] += 1
            elif i.code == "LCM-02":
                due[r["asset"].category][1] += 1
    h.append(_table(["Category"] + list(STATES) + ["Overdue", f"Due by {horizon:%d %b %Y}"],
                    [f"<tr><td><b>{e(c)}</b></td>" + "".join(f"<td class='num'>{v[x] or '–'}</td>" for x in STATES)
                     + f"<td class='num {'warning' if due[c][0] else ''}'>{due[c][0] or '–'}</td><td class='num'>{due[c][1] or '–'}</td></tr>"
                     for c, v in sc.items()]))
    other = [r for r in rv["lifecycle"] if any(i.code in ("LCM-03", "LCM-04") for i in r["issues"])]
    if other:
        h.append("<p class='muted'>Items without a date or with a state that does not match what MDM sees:</p>")
        h.append(_table(["Item", "Category", "State", "Issues"],
                        [f"<tr><td class='nw'><b>{e(a.name or a.asset_tag)}</b><br><span class='muted'>{e(a.serial)}</span></td><td>{e(a.category)}</td>"
                         f"<td>{e(a.state)}</td><td class='sm'>{'<br>'.join(f'<b>{e(i.code)}</b> {e(i.text)}' for i in r['issues'] if i.code in ('LCM-03', 'LCM-04'))}</td></tr>"
                         for r in other for a in [r["asset"]]]))
    # 4 people
    _sect(h, 4, "People", "People", st,
          f"Devices of leavers (returned within {s.leaver_return_days} days), more devices than the policy allows, active people without a computer, "
          "devices assigned to someone HR does not know. Every person is in people.csv.")
    pr = [r for r in rv["people"] if r["issues"]]
    h.append(_table(["Person", "Site", "Status", "Devices", "Issues"],
                    [f"<tr><td class='sm brk'><b>{e(p.name if p else r['upn'])}</b><br><span class='muted'>{e(p.upn if p else 'not in HR')}</span></td>"
                     f"<td>{e(p.site if p else '–')}</td><td class='nw'>{e(p.status if p else '–')}{'<br><span class=muted>left ' + _t(p.end) + '</span>' if p and p.end else ''}</td>"
                     f"<td class='num'>{len(r['items'])}</td><td class='sm'>{_issues(r)}</td></tr>" for r in pr for p in [r["person"]]]))
    # 5 stock
    _sect(h, 5, "Stock", "Stock", st,
          f"Stock per site against the minimum, and the replacements due by {quarter_end(d.today, 1):%d %b %Y}. To order = due + minimum − on hand.")
    h.append(_table(["Site", "Category", "Model", "On hand", "Minimum", "Due", "Backlog", "To order", "Issues"],
                    [f"<tr><td class='nw'><b>{e(r['site'])}</b></td><td>{e(r['category'])}</td><td class='sm'>{e(r['model'] or '–')}</td>"
                     f"<td class='num {'warning' if r['on_hand'] < r['minimum'] else ''}'>{r['on_hand']}</td><td class='num'>{r['minimum']}</td>"
                     f"<td class='num'>{r['need'] or '–'}</td><td class='num'>{r['backlog'] or '–'}</td><td class='num'><b>{r['order'] or '–'}</b></td>"
                     f"<td class='sm'>{_issues(r)}</td></tr>" for r in rv["stock"]]))
    # 6 forecast
    _sect(h, 6, "Forecast for the budget", "Forecast", st,
          "Replacement cost by quarter from the refresh policy and the unit costs in settings.json. The overdue backlog is kept apart: it is not in any "
          "quarter yet. forecast.csv has every line by site and category.")
    top = max((fc["totals"][b]["cost"] for b in qs), default=0) or 1
    h.append("<div class='bars'>" + "".join(
        f"<div class='col'><span class='v'>{e(money(d, fc['totals'][b]['cost']))}</span><span class='b{' over' if b == 'overdue' else ''}' "
        f"style='height:{max(2, round(160 * fc['totals'][b]['cost'] / top))}px'></span><span class='k'>{e(_label(b, d))}<br>"
        f"{fc['totals'][b]['units']} items</span></div>" for b in qs) + "</div>")
    cats, m = _matrix(rv)
    rows = [f"<tr><td><b>{e(c)}</b></td>" + "".join(f"<td class='num'>{m[c][b][0] or '–'}{'<br><span class=muted>' + e(money(d, m[c][b][1])) + '</span>' if m[c][b][0] else ''}</td>" for b in qs) + "</tr>"
            for c in cats]
    rows.append("<tr class='tot'><td>Total</td>" + "".join(f"<td class='num'>{fc['totals'][b]['units']}<br>{e(money(d, fc['totals'][b]['cost']))}</td>" for b in qs) + "</tr>")
    h.append(_table(["Category"] + [_label(b, d) for b in qs], rows))
    bysite = defaultdict(lambda: defaultdict(float))
    for r in fc["rows"]:
        bysite[r["site"]][r["bucket"]] += r["cost"]
    h.append("<p class='muted'>By site:</p>")
    h.append(_table(["Site"] + [_label(b, d) for b in qs],
                    [f"<tr><td><b>{e(site)}</b></td>" + "".join(f"<td class='num'>{e(money(d, bysite[site][b])) if bysite[site][b] else '–'}</td>" for b in qs) + "</tr>"
                     for site in sorted(bysite)]))
    h.append("<h2>All findings</h2>")
    h.append(_table(["Severity", "Area", "Subject", "Detail", "Next step", "Owner"],
                    [f"<tr><td>{_pill(f.severity, f.severity.upper())}</td><td class='nw'>{e(f.area)}</td><td>{e(f.subject)}</td>"
                     f"<td class='sm'>{e(f.detail)}</td><td class='fix'>{e(f.fix)}</td><td class='nw'>{e(f.owner)}</td></tr>" for f in findings]))
    h.append("<footer class='muted'>Generated by assetplan. Fictional demo data unless you ran it on your own exports. The monthly pack is "
             "asset-review.md.</footer></main></body></html>")
    return "".join(h)


__all__ = ["render_html", "pack_md", "WARNING"]
