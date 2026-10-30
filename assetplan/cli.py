"""Command line: `demo` writes the fictional Contoso Markets offices to sample_data/ and builds the outputs; `review` runs on your own exports."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import report, simulate
from .checks import money, overall, review, run_all, summary
from .model import load, parse_dt

OUTPUTS = ("report.html", "asset-review.md", "inventory.csv", "coverage.csv", "comms-rooms.csv", "lifecycle.csv", "people.csv", "stock-plan.csv",
           "forecast.csv", "actions.csv", "findings.csv")


def run(data: Path, out: Path, title: str, as_of: datetime | None = None) -> dict:
    d = load(data, as_of)
    rv = review(d)
    findings = run_all(d, rv)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.html").write_text(report.render_html(d, rv, findings, title), encoding="utf-8")
    (out / "asset-review.md").write_text(report.pack_md(d, rv, findings, title), encoding="utf-8")
    report.write_inventory(d, rv, out / "inventory.csv")
    report.write_coverage(d, rv, out / "coverage.csv")
    report.write_comms(d, rv, out / "comms-rooms.csv")
    report.write_lifecycle(d, rv, out / "lifecycle.csv")
    report.write_people(d, rv, out / "people.csv")
    report.write_stock(d, rv, out / "stock-plan.csv")
    report.write_forecast(d, rv, out / "forecast.csv")
    report.write_actions(findings, out / "actions.csv")
    report.write_findings(findings, out / "findings.csv")
    sm = summary(d, rv)
    sm.update(overall=overall(findings), critical=sum(f.severity == "critical" for f in findings), warning=sum(f.severity == "warning" for f in findings),
              money=lambda v: money(d, v))
    return sm


def _when(value: str) -> datetime:
    d = parse_dt(value)
    if not d:
        raise argparse.ArgumentTypeError(f"not a date (YYYY-MM-DD or 'YYYY-MM-DD HH:MM'): {value}")
    return d


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="assetplan", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    dm = sub.add_parser("demo", help="write the fictional offices to sample_data/ and build the outputs")
    dm.add_argument("--data", type=Path, default=Path("sample_data"))
    dm.add_argument("--out", type=Path, default=Path("output"))
    rv = sub.add_parser("review", help="build the outputs from your own exports")
    rv.add_argument("data", type=Path, nargs="?", help="folder with device42-devices.csv, office-register.csv and/or purchases.csv, and the optional files")
    rv.add_argument("--data", dest="data_opt", type=Path, help="same as the positional folder")
    rv.add_argument("--out", type=Path, default=Path("output"))
    rv.add_argument("--title", default="Monthly IT asset review")
    rv.add_argument("--as-of", type=_when, help="reference date (default: settings.json, or today)")
    a = p.parse_args(argv)
    if a.cmd == "demo":
        simulate.write(a.data)
        sm = run(a.data, a.out, f"{simulate.ORG} · IT asset review, October 2026")
    else:
        folder = a.data or a.data_opt
        if not folder:
            print("error: give the folder with the exports", file=sys.stderr)
            return 2
        try:
            sm = run(folder, a.out, a.title, a.as_of)
        except (FileNotFoundError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    m = sm["money"]
    print(f"{sm['overall'].upper()} · {sm['items']} items · not in inventory {sm['not_in_inventory']} · not seen {sm['not_seen']} · "
          f"past end of support {sm['eos']} · warranty soon {sm['warranty_soon']} · overdue {sm['overdue']} ({m(sm['backlog_cost'])}) · "
          f"leavers not returned {sm['leavers_kept']} · stock below min {sm['below_min']} · next quarters {m(sm['next_cost'])} · "
          f"{sm['critical']} critical, {sm['warning']} warnings")
    print(f"outputs in {a.out}/: {', '.join(OUTPUTS)}")
    return 0
