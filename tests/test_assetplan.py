import csv
import hashlib
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from assetplan import cli
from assetplan.checks import CRITICAL, INFO, ORDER, WARNING, area_status, buckets, inventory, overall, review, run_all
from assetplan.model import (CommsDevice, Data, MdmDevice, Person, Purchase, RegisterItem, StockLine, category_of, load, load_device42, load_hr,
                             load_mdm, load_purchases, load_register, quarter_end, serial_key, settings_from_dict, state_of)

AS_OF = datetime(2026, 10, 30, 9, 0)
D = "contoso.example"


def write(path: Path, header: list[str], rows: list[list], delimiter: str = ",") -> Path:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=delimiter)
        w.writerow(header)
        w.writerows(rows)
    return path


def ago(n: float) -> datetime:
    return AS_OF - timedelta(days=n)


def data(comms=None, mdm=None, purchases=None, register=None, people=None, stock=None, **raw) -> Data:
    return Data(settings_from_dict(raw), AS_OF, comms or [], mdm or [], purchases or [], register or [], people or [], stock or [])


def laptop(serial, user="ana@" + D, last=1, bought=date(2024, 5, 6), **kw):
    """A purchased laptop seen in Intune."""
    return (Purchase(serial, "Latitude 7450", "laptop", "DLL-1", bought, None, 1450.0, "Dell", kw.pop("site", "Madrid")),
            MdmDevice("Intune", f"PC-{serial}", serial, kw.pop("model", "Latitude 7450"), "Dell Inc.", "Windows", "10.0.26100", user,
                      ago(last) if last is not None else None, datetime.combine(bought, datetime.min.time()), kw.pop("owner_type", "company")))


def codes(rows: list[dict], code: str) -> list:
    return [i for r in rows for i in r["issues"] if i.code == code]


def person(upn, site="Madrid", **kw) -> Person:
    base = dict(name=upn.split("@")[0].title(), upn=upn, site=site, status="Active", start=date(2020, 1, 1))
    base.update(kw)
    return Person(upn.split("@")[0], **base)


class TestLoading(unittest.TestCase):
    def test_device42_and_mdm_exports(self):
        with tempfile.TemporaryDirectory() as t:
            p = write(Path(t) / "d42.csv", ["name", "serial_no", "hw_model", "manufacturer", "building", "room", "rack", "start_at", "in_service", "customer",
                                            "osver", "Warranty end", "End of support"],
                      [["mad-sw01", "FOC1234X0AB", "Cisco Catalyst 9300-48P", "Cisco", "MAD-HQ", "CR-1", "R01", "40", "yes", "Network", "17.12.4",
                        "2027-02-21", ""],
                       ["mad-pp-1", "", "Cat6A 24-port patch panel", "Panduit", "MAD-HQ", "CR-1", "R01", "44", "yes", "", "", "", ""],
                       ["mad-ups", "AS99", "APC Smart-UPS SRT 10kVA", "APC", "MAD-HQ", "CR-1", "", "", "no", "", "", "", ""]])
            cm = load_device42(p, settings_from_dict({"site_aliases": {"MAD-HQ": "Madrid"}, "end_of_support": {"Cisco Catalyst 9300-48P": "2030-10-31"}}))
            i = write(Path(t) / "i.csv", ["deviceName", "serialNumber", "model", "operatingSystem", "userPrincipalName", "lastSyncDateTime",
                                          "managedDeviceOwnerType"],
                      [["PC1", "7XK2L93", "Latitude 7450", "Windows", "a@x", "2026-10-29T08:12:44.1234567Z", "company"],
                       ["ana_iPhone", "F2LX", "iPhone 15", "iOS", "a@x", "2026-10-29T08:12:44Z", "personal"]])
            j = write(Path(t) / "j.csv", ["general.name", "hardware.serialNumber", "hardware.model", "userAndLocation.email", "general.lastContactTime"],
                      [["MAC1", "C02XK1JHMD6R", "MacBook Pro (14-inch, Nov 2023)", "b@x", "2026-10-28T17:00:00.000Z"]], delimiter=";")
            mi, mj = load_mdm(i, "Intune"), load_mdm(j, "Jamf")
        self.assertEqual([(c.category, c.building, c.position, c.in_service) for c in cm],
                         [("switch", "Madrid", "40", True), ("patch panel", "Madrid", "44", True), ("ups", "Madrid", "", False)])
        self.assertEqual((cm[0].warranty_end, cm[0].eos), (date(2027, 2, 21), date(2030, 10, 31)))
        self.assertEqual((mi[0].last_seen, mi[1].personal, mj[0].os, mj[0].manufacturer, mj[0].user), (datetime(2026, 10, 29, 8, 12, 44), True, "macOS", "Apple", "b@x"))

    def test_purchases_register_hr_in_spanish(self):
        with tempfile.TemporaryDirectory() as t:
            p = write(Path(t) / "p.csv", ["Pedido", "Número de serie", "Modelo", "Fecha compra", "Fin garantía", "Precio"],
                      [["PO-1", "7xk2-l93", "Dell Latitude 7450", "06/05/2024", "06/05/2027", "1.450,00 €"]], delimiter=";")
            r = write(Path(t) / "r.csv", ["Etiqueta", "Número de serie", "Tipo", "Sede", "Asignado a", "Estado"],
                      [["CM-1", "SN1234", "Pantalla", "Madrid", "ana@x", "En uso"], ["CM-2", "SN9999", "Portátil", "Madrid", "", "Almacén"],
                       ["CM-3", "SN5555", "Base", "París", "", "Reparación (RMA)"]], delimiter=";")
            h = write(Path(t) / "h.csv", ["Numero empleado", "Nombre", "Correo", "Sede", "Estado", "Fecha alta", "Fecha baja"],
                      [["E1", "Ana Ruiz", "ana@x", "Madrid", "Baja", "2020-01-07", "2026-09-30"]])
            ps, rs, hs = load_purchases(p), load_register(r), load_hr(h)
        self.assertEqual((ps[0].cost, ps[0].purchase_date, ps[0].category, serial_key(ps[0].serial)), (1450.0, date(2024, 5, 6), "laptop", "7XK2L93"))
        self.assertEqual([(x.category, x.state) for x in rs], [("monitor", "deployed"), ("laptop", "in stock"), ("dock", "in repair")])
        self.assertTrue(hs[0].left(date(2026, 10, 30)))
        self.assertEqual((category_of("", "Precision 3680 Tower"), category_of("", "Precision 5690"), category_of("FortiGate 200F"), state_of("Disposed")),
                         ("desktop", "laptop", "firewall", "retired"))
        self.assertEqual((serial_key("To be filled by O.E.M."), serial_key("0"), serial_key("Default string")), ("", "", ""))

    def test_settings_quarters_and_required_files(self):
        s = settings_from_dict({"refresh_years": {"Portátil": 5, "patch panel": None}, "unit_costs": {"laptop": "1.500"}, "owners": {"stock": "Office manager"}})
        self.assertEqual((s.years("laptop"), s.years("patch panel"), s.cost("laptop"), s.owner("stock"), s.owner("people")),
                         (5.0, None, 1500.0, "Office manager", "Service desk lead"))
        self.assertEqual((quarter_end(date(2026, 10, 30)), quarter_end(date(2026, 10, 30), 1), quarter_end(date(2026, 10, 30), 2)),
                         (date(2026, 12, 31), date(2027, 3, 31), date(2027, 6, 30)))
        self.assertEqual(buckets(data()), ["overdue", "Q4-2026", "Q1-2027", "Q2-2027", "Q3-2027", "Q4-2027"])
        with tempfile.TemporaryDirectory() as t, self.assertRaises(FileNotFoundError):
            write(Path(t) / "hr.csv", ["UPN"], [["a@x"]])
            load(Path(t))


class TestCoverage(unittest.TestCase):
    def test_mdm_devices_missing_and_personal_left_out(self):
        p1, m1 = laptop("AAA1111")
        _, m2 = laptop("BBB2222", user="bob@" + D)                       # in Intune only
        _, m3 = laptop("CCC3333", owner_type="personal")
        rv = review(data(purchases=[p1], mdm=[m1, m2, m3]))
        miss = codes(rv["coverage"], "COV-01")
        self.assertEqual([i.text.split(":")[0] for i in miss], ["PC-BBB2222 (BBB2222)"])
        self.assertEqual(len(rv["inv"]["personal"]), 1)
        self.assertEqual(len(rv["inv"]["assets"]), 2)

    def test_not_seen_duplicates_mismatch_placeholder_and_owner(self):
        pa, ma = laptop("AAA1111", last=45)
        pb, _ = laptop("BBB2222")                                          # never enrolled
        pc, mc = laptop("CCC3333", model="Latitude 5440")                  # wrong model in Intune
        mold = MdmDevice("Intune", "PC-OLD", "AAA1111", "Latitude 7450", "Dell Inc.", "Windows", "", "ana@" + D, ago(90))
        mph = MdmDevice("Intune", "MR-PC01", "To be filled by O.E.M.", "NUC 13 Pro Kit", "ASUS", "Windows", "", "", ago(1))
        reg = [RegisterItem("T1", "MON001", "monitor", "P2723DE", "Dell", "Madrid", "", "ana@" + D, "deployed"),
               RegisterItem("T2", "MON001", "monitor", "P2723DE", "Dell", "Madrid", "", "bob@" + D, "deployed"),
               RegisterItem("T3", "MON002", "monitor", "P2723DE", "Dell", "", "", "", "deployed"),
               RegisterItem("T4", "LAP009", "laptop", "Latitude 7450", "Dell", "Madrid", "IT store", "", "in stock")]
        rv = review(data(purchases=[pa, pb, pc], mdm=[ma, mold, mc, mph], register=reg))
        cov = rv["coverage"]
        self.assertEqual(sorted(i.text.split(":")[0] for i in codes(cov, "COV-02")), ["BBB2222", "PC-AAA1111 (AAA1111)"])
        c3 = [i for i in codes(cov, "COV-03")]
        self.assertEqual(sorted((i.severity, i.text.split(":")[0]) for i in c3),
                         [(INFO, "PC-AAA1111 (AAA1111)"), (WARNING, "MR-PC01"), (WARNING, "PC-CCC3333 (CCC3333)"), (WARNING, "T1 (MON001)")])
        self.assertNotIn("MR-PC01", [i.text.split(":")[0] for i in codes(cov, "COV-01")])
        self.assertIn("T3 (MON002): monitor P2723DE without owner and site", [i.text for i in codes(cov, "COV-04")])
        self.assertNotIn("T4", " ".join(i.text for i in codes(cov, "COV-02") + codes(cov, "COV-04")))   # spares are not expected in MDM


class TestInventory(unittest.TestCase):
    def test_one_inventory_joined_by_serial(self):
        cm = [CommsDevice("mad-esx01", "8kq2-ab1", category="server", model="PowerEdge R650", building="Madrid", room="CR-1", rack="R04", position="20",
                          owner="Infrastructure", os_version="8.0.3")]
        pur = [Purchase("8KQ2AB1", "PowerEdge R650", "server", "DLL-9", date(2022, 10, 3), date(2027, 10, 3), 10800.0, "Dell", "Madrid"),
               Purchase("MON777", "Dell P2723DE", "monitor", "DLL-8", date(2023, 3, 2), None, 240.0, "Dell", "Paris")]
        reg = [RegisterItem("CM-7", "mon777", "monitor", "Dell P2723DE", "Dell", "", "Open office", "ana@" + D, "In use")]
        p, m = laptop("LAP1234", site="Paris")
        inv = inventory(data(comms=cm, purchases=pur + [p], register=reg, mdm=[m], people=[person("ana@" + D, site="Amsterdam")]))
        a = {x.key: x for x in inv["assets"]}
        self.assertEqual(sorted(a), ["8KQ2AB1", "LAP1234", "MON777"])
        self.assertEqual((a["8KQ2AB1"].sources, a["8KQ2AB1"].warranty_end, a["8KQ2AB1"].replace_on), (["Device42", "Purchases"], date(2027, 10, 3),
                                                                                                        date(2027, 10, 3)))
        self.assertEqual((a["MON777"].sources, a["MON777"].site, a["MON777"].asset_tag), (["Register", "Purchases"], "Amsterdam", "CM-7"))
        self.assertEqual((a["LAP1234"].owner, a["LAP1234"].site, a["LAP1234"].category, a["LAP1234"].state), ("ana@" + D, "Amsterdam", "laptop", "deployed"))


class TestCommsRooms(unittest.TestCase):
    def test_end_of_support_warranty_rack_owner_and_firmware(self):
        cm = [CommsDevice("core1", "FOC1", category="switch", model="Catalyst 9500", building="Madrid", room="CR-1", rack="R01", position="40", owner="Network",
                          service_level="Production - critical", os_version="17.12.4", purchase_date=date(2021, 12, 13), warranty_end=date(2026, 12, 11)),
              CommsDevice("acc1", "FOC2", category="switch", model="Catalyst 3850-48P", building="Madrid", room="CR-1", rack="R03", position="38", owner="Network",
                          purchase_date=date(2017, 3, 6), warranty_end=date(2025, 10, 31), eos=date(2025, 10, 31)),
              CommsDevice("srv1", "SRV1", category="server", model="PowerEdge R650", building="Paris", room="ST", rack="R02", position="", owner="",
                          os_version="", purchase_date=date(2022, 1, 17), warranty_end=date(2027, 1, 15)),
              CommsDevice("pdu1", "PDU1", category="pdu", model="AP8941", building="Madrid", room="CR-1", rack="R01", position="0", owner="Infra",
                          warranty_end=date(2022, 9, 1))]
        rv = review(data(comms=cm, critical_service_levels=["Production - critical"]))
        got = {(i.code, i.severity, i.text.split(":")[0]) for r in rv["comms"] for i in r["issues"]}
        self.assertIn(("CR-02", CRITICAL, "core1"), got)                   # 42 days, critical service level
        self.assertIn(("CR-01", CRITICAL, "acc1"), got)
        self.assertIn(("CR-02", WARNING, "srv1"), got)                     # 77 days
        self.assertIn(("CR-02", INFO, "pdu1"), got)                        # PDU warranty: information only
        self.assertEqual(sorted(x[0] + x[2] for x in got if x[0] in ("CR-03", "CR-04") and x[1] == WARNING), ["CR-03srv1", "CR-04acc1", "CR-04srv1"])
        acc = next(a for a in rv["inv"]["assets"] if a.name == "acc1")
        self.assertEqual((acc.replace_on, acc.basis), (date(2024, 3, 6), "purchase + 7 y"))
        core = next(a for a in rv["inv"]["assets"] if a.name == "core1")
        self.assertEqual(core.replace_on, date(2028, 12, 13))


class TestLifecycle(unittest.TestCase):
    def test_states_replacement_dates_and_inconsistencies(self):
        p_old, m_old = laptop("OLD0001", bought=date(2022, 3, 1))
        p_due, m_due = laptop("DUE0001", bought=date(2023, 5, 10), user="bob@" + D)
        _, m_est = laptop("EST0001", bought=date(2023, 1, 20), user="eva@" + D)          # no purchase: date from enrolment
        p_ret, m_ret = laptop("RET0001", bought=date(2021, 1, 1), last=5, user="old@" + D)
        reg = [RegisterItem("T1", "RET0001", "laptop", state="retired"), RegisterItem("T2", "", "printer", "MFP", site="Madrid", assigned="Print 1",
                                                                                     state="deployed"),
               RegisterItem("T3", "SPR0001", "laptop", state="in stock", site="Madrid", purchase_date=date(2022, 4, 1))]
        rv = review(data(purchases=[p_old, p_due, p_ret], mdm=[m_old, m_due, m_est, m_ret], register=reg))
        a = {x.key: x for x in rv["inv"]["assets"]}
        self.assertEqual([a[k].state for k in ("OLD0001", "RET0001", "SPR0001", "TAG:t2")], ["deployed", "retired", "in stock", "deployed"])
        self.assertEqual((a["OLD0001"].replace_on, a["DUE0001"].replace_on, a["EST0001"].estimated, a["EST0001"].replace_on),
                         (date(2026, 3, 1), date(2027, 5, 10), True, date(2027, 1, 20)))
        lc = rv["lifecycle"]
        self.assertEqual([i.text.split(":")[0] for i in codes(lc, "LCM-01")], ["PC-OLD0001 (OLD0001)"])
        self.assertEqual(sorted(i.text.split(":")[0] for i in codes(lc, "LCM-02")), ["PC-DUE0001 (DUE0001)", "PC-EST0001 (EST0001)"])
        self.assertEqual([i.text.split(":")[0] for i in codes(lc, "LCM-03")], ["T2"])
        self.assertEqual(sorted((i.severity, i.text.split(":")[0]) for i in codes(lc, "LCM-04")), [(INFO, "T3 (SPR0001)"), (WARNING, "PC-RET0001 (RET0001)")])


class TestPeople(unittest.TestCase):
    def test_leavers_policy_no_computer_and_unknown_users(self):
        hr = [person("gone@" + D, status="Leaver", end=date(2026, 9, 30)), person("recent@" + D, status="Leaver", end=date(2026, 10, 26)),
              person("two@" + D), person("none@" + D), person("future@" + D, start=date(2026, 11, 9))]
        devs = [laptop("GON0001", user="gone@" + D, last=2), laptop("REC0001", user="recent@" + D, last=4),
                laptop("TWO0001", user="two@" + D), laptop("TWO0002", user="two@" + D, bought=date(2022, 2, 1)), laptop("EXT0001", user="ext@" + D)]
        rv = review(data(purchases=[p for p, _ in devs], mdm=[m for _, m in devs], people=hr))
        pp = rv["people"]
        c = codes(pp, "PPL-02")
        self.assertEqual((len(c), c[0].severity), (1, CRITICAL))
        self.assertIn("not returned 30 days after leaving", c[0].text)
        self.assertIn("still syncing after leaving", c[0].text)
        self.assertIn("return due by 09 Nov 2026", codes(pp, "PPL-01")[0].text)
        self.assertIn("2 laptops (policy 1)", codes(pp, "PPL-03")[0].text)
        self.assertEqual([i.text.split(" (")[0] for i in codes(pp, "PPL-04")], ["None"])        # the future joiner is not flagged yet
        self.assertEqual([i.text.split(":")[0] for i in codes(pp, "PPL-05")], ["ext@" + D])


class TestStockAndForecast(unittest.TestCase):
    def test_stock_below_minimum_and_next_quarter_needs(self):
        devs = [laptop(f"Q1{n:05d}", bought=date(2023, 2, 1)) for n in range(4)] + [laptop("OVD0001", bought=date(2022, 1, 5))]
        stock = [StockLine("Madrid", "laptop", "Latitude 7450", 3, 2), StockLine("Madrid", "monitor", "P2725HE", 3, 10), StockLine("Paris", "dock", "", 0, 2)]
        rv = review(data(purchases=[p for p, _ in devs], mdm=[m for _, m in devs], stock=stock))
        st = {(r["site"], r["category"]): r for r in rv["stock"]}
        self.assertEqual((st[("Madrid", "laptop")]["need"], st[("Madrid", "laptop")]["backlog"], st[("Madrid", "laptop")]["order"]), (4, 1, 3))
        self.assertEqual(st[("Madrid", "monitor")]["order"], 7)
        sev = {(i.code, i.text.split(":")[0]): i.severity for r in rv["stock"] for i in r["issues"]}
        self.assertEqual(sev, {("STK-02", "Madrid · laptop"): WARNING, ("STK-01", "Madrid · monitor"): WARNING, ("STK-01", "Paris · dock"): CRITICAL})

    def test_forecast_buckets_costs_and_wave(self):
        devs = ([laptop(f"W{n:06d}", bought=date(2023, 5, 10)) for n in range(6)] + [laptop("OVD0001", bought=date(2022, 1, 5))]
                + [laptop("NOW0001", bought=date(2022, 12, 1)), laptop("Q3A0001", bought=date(2023, 8, 1))])
        cm = [CommsDevice("sw1", "FOC9", category="switch", model="Catalyst 9300", building="Madrid", owner="Network", rack="R1", position="1",
                          os_version="17", purchase_date=date(2020, 2, 3), warranty_end=date(2028, 1, 1))]
        d = data(purchases=[p for p, _ in devs], mdm=[m for _, m in devs], comms=cm)
        rv = review(d)
        t = rv["forecast"]["totals"]
        self.assertEqual({b: t[b]["units"] for b in t}, {"overdue": 1, "Q4-2026": 1, "Q1-2027": 1, "Q2-2027": 6, "Q3-2027": 1, "Q4-2027": 0})
        self.assertEqual((t["Q2-2027"]["cost"], t["Q1-2027"]["cost"]), (8700.0, 6500.0))
        f = {x.code: x for x in run_all(d, rv)}
        self.assertEqual(f["FC-02"].severity, WARNING)
        self.assertIn("Q2-2027", f["FC-02"].subject)
        self.assertIn("€16,650", f["FC-01"].subject)


class TestVerdict(unittest.TestCase):
    def test_status_by_area_and_overall(self):
        p, m = laptop("AAA1111", user="ana@" + D, bought=date(2025, 6, 2))
        clean = data(purchases=[p], mdm=[m], people=[person("ana@" + D)], stock=[StockLine("Madrid", "laptop", "", 3, 2)])
        f = run_all(clean)
        self.assertEqual((overall(f), set(area_status(f).values())), ("on track", {"ok"}))
        _, m2 = laptop("BBB2222", user="ana@" + D)
        f = run_all(data(purchases=[p], mdm=[m, m2], people=[person("ana@" + D)]))
        self.assertEqual((overall(f), area_status(f)["Coverage"], area_status(f)["People"]), ("attention", WARNING, WARNING))
        f = run_all(data(purchases=[p], mdm=[m], people=[person("ana@" + D, status="Leaver", end=date(2026, 9, 1))]))
        self.assertEqual((overall(f), area_status(f)["People"]), ("action needed", CRITICAL))


class TestDemo(unittest.TestCase):
    def test_demo_end_to_end_is_deterministic(self):
        hashes = []
        with tempfile.TemporaryDirectory() as t:
            for k in range(2):
                out = Path(t) / f"out{k}"
                self.assertEqual(cli.main(["demo", "--data", str(Path(t) / f"data{k}"), "--out", str(out)]), 0)
                self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(cli.OUTPUTS))
                hashes.append({n: hashlib.sha1((out / n).read_bytes()).hexdigest() for n in cli.OUTPUTS}
                              | {n.name: hashlib.sha1(n.read_bytes()).hexdigest() for n in (Path(t) / f"data{k}").iterdir()})
            self.assertEqual(hashes[0], hashes[1])
            d = load(Path(t) / "data0")
        rv = review(d)
        f = run_all(d, rv)
        self.assertEqual([x.severity for x in f], sorted((x.severity for x in f), key=ORDER.get))
        self.assertEqual(overall(f), "action needed")
        got = {x.code for x in f}
        for c in ("COV-01", "COV-02", "COV-03", "COV-04", "CR-01", "CR-02", "CR-03", "CR-04", "LCM-01", "LCM-03", "LCM-04", "PPL-01", "PPL-02", "PPL-03",
                  "PPL-04", "PPL-05", "STK-01", "STK-02", "FC-01", "FC-02"):
            self.assertIn(c, got)
        self.assertEqual(len(codes(rv["coverage"], "COV-01")), 9)
        self.assertEqual(sorted(i.text.split(":")[0] for i in codes(rv["comms"], "CR-01") if i.severity == CRITICAL), ["mad-acc-sw01", "mad-acc-sw02", "mad-acc-sw03"])
        self.assertEqual([i.text.split(":")[0] for i in codes(rv["comms"], "CR-02") if i.severity == CRITICAL], ["mad-core-sw01"])
        self.assertEqual((len(codes(rv["people"], "PPL-02")), len(codes(rv["people"], "PPL-01"))), (4, 1))
        self.assertEqual([i.text.split(":")[0] for i in codes(rv["stock"], "STK-01")], ["Madrid · monitor", "Paris · dock"])
        self.assertIn("Refresh wave in Q2-2027", next(x for x in f if x.code == "FC-02").subject)
        self.assertEqual(d.settings.organisation, "Contoso Markets")

    def test_review_reports_missing_inventory(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(cli.main(["review", t, "--out", str(Path(t) / "o")]), 2)
            self.assertEqual(cli.main(["review", "--out", str(Path(t) / "o")]), 2)


if __name__ == "__main__":
    unittest.main()
