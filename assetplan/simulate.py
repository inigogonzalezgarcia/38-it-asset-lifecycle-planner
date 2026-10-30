"""Fictional demo: Contoso Markets, a made-up broker with offices in Madrid (about 120 people and a trading floor), Paris and Amsterdam and
comms rooms in Madrid and Paris, reviewed on Friday 30 October 2026: the Device42 export of the comms rooms, Intune and Jamf Pro devices,
the vendor purchases, the office register, the HR roster and the stock register, with the problems placed on purpose among the everyday
records. Every name, serial number, order and address is made up."""
from __future__ import annotations

import csv
import json
import random
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

ORG = "Contoso Markets"
AS_OF = datetime(2026, 10, 30, 9, 0)
SEED = 38
DOMAIN = "contosomarkets.example"
SITES = {"Madrid": ("MAD", 120), "Paris": ("PAR", 45), "Amsterdam": ("AMS", 25)}
DEPTS = {"Madrid": [("Trading", 24), ("Sales", 26), ("Operations", 22), ("Risk", 12), ("Technology", 16), ("Finance", 10), ("Marketing", 6),
                    ("People", 4)],
         "Paris": [("Sales", 18), ("Research", 12), ("Operations", 15)],
         "Amsterdam": [("Sales", 13), ("Operations", 12)]}
FIRST = ["Adrian", "Alba", "Alice", "Amir", "Ana", "Andrea", "Arturo", "Beatriz", "Bruno", "Camille", "Carlos", "Chloe", "Clara", "Cristina", "David",
         "Diego", "Elena", "Emma", "Erik", "Eva", "Felix", "Fiona", "Gabriel", "Grace", "Hannah", "Hugo", "Ines", "Isaac", "Ivan", "Jakob", "Javier",
         "Julia", "Karin", "Laura", "Leo", "Lucas", "Lucia", "Maria", "Marta", "Martin", "Mateo", "Mia", "Nicolas", "Nora", "Oliver", "Olga", "Pablo",
         "Patricia", "Pedro", "Raquel", "Rosa", "Ruben", "Sara", "Sergio", "Sofia", "Teresa", "Tobias", "Victor", "Yara", "Zoe", "Margot", "Louis",
         "Sanne", "Daan", "Femke", "Bram", "Juliette", "Hélène", "Noémie", "Théo"]
LAST = ["Abad", "Aldana", "Arnaiz", "Bauer", "Benitez", "Blanco", "Brandt", "Cano", "Carvalho", "Castro", "Cortes", "Delgado", "Dietrich", "Duarte",
        "Eriksen", "Escobar", "Ferrer", "Fischer", "Fuentes", "Gallardo", "Garrido", "Hartmann", "Herrera", "Iglesias", "Jansen", "Keane", "Klein",
        "Lorenzo", "Lozano", "Madsen", "Marin", "Mendez", "Molina", "Navarro", "Nieto", "Ortega", "Pardo", "Pascual", "Peters", "Quintana", "Ramos",
        "Reyes", "Rojas", "Romero", "Rubio", "Sanz", "Schmidt", "Serrano", "Soler", "Suarez", "Torres", "Urquijo", "Vega", "Vidal", "Vogel", "Weber",
        "Winter", "Zamora", "Dubois", "Lefevre", "Moreau", "Girard", "de Vries", "Bakker", "Visser", "Smit", "Meijer"]
ROOMS = {"Madrid": ["Sala Retiro", "Sala Prado", "Sala Cibeles", "Sala Atocha", "Sala Sol", "Boardroom"], "Paris": ["Salle Seine", "Salle Marais", "Salle Opéra"],
         "Amsterdam": ["Room Amstel", "Room Jordaan"]}
DELL = "Dell"
APPLE = "Proseware (Apple reseller)"
MOBILE = "Wingtip Mobile"
D42_FILE_HEADER = ["name", "serial_no", "asset_no", "hw_model", "manufacturer", "building", "room", "rack", "start_at", "in_service", "customer",
                   "service_level", "os", "osver", "last_updated", "Purchase date", "Warranty end", "End of support"]

SETTINGS = {
    "organisation": ORG,
    "as_of": "2026-10-30 09:00",
    "currency": "€",
    "not_seen_days": 30,
    "warranty_warn_days": 90,
    "warranty_critical_days": 45,
    "eos_warn_days": 365,
    "critical_service_levels": ["Production - critical"],
    "leaver_return_days": 14,
    "refresh_years": {"laptop": 4, "desktop": 5, "phone": 3, "tablet": 4, "monitor": 6, "dock": 5, "meeting room": 5, "printer": 6, "switch": 7,
                      "router": 7, "firewall": 7, "server": 5, "storage": 5, "pdu": 10, "ups": 4, "patch panel": None},
    "unit_costs": {"laptop": 1450, "desktop": 1650, "phone": 750, "tablet": 650, "monitor": 260, "dock": 230, "meeting room": 3800, "printer": 1400,
                   "switch": 6500, "router": 4800, "firewall": 9000, "server": 11000, "storage": 25000, "pdu": 900, "ups": 1600, "patch panel": 0},
    "max_per_person": {"laptop": 1, "desktop": 1, "phone": 1, "tablet": 1, "monitor": 2, "dock": 1},
    "computer_required": True,
    "end_of_support": {"Cisco Catalyst 3850-48P": "2025-10-31"},
    "rack_categories": ["switch", "router", "firewall", "server", "storage", "pdu", "patch panel"],
    "stock_categories": ["laptop", "desktop", "phone", "monitor", "dock"],
    "forecast_quarters": 4,
    "wave_share": 0.4,
    "site_aliases": {"MAD-HQ": "Madrid", "PAR-01": "Paris"},
    "owners": {"coverage": "Site IT lead", "comms": "Network & infrastructure lead", "lifecycle": "Site IT lead", "people": "Service desk lead",
               "stock": "Site IT lead", "forecast": "IT budget owner"},
}
FILES = {
    "device42-devices.csv": ("d42", D42_FILE_HEADER),
    "intune-devices.csv": ("intune", ["deviceName", "serialNumber", "model", "manufacturer", "operatingSystem", "osVersion", "userPrincipalName",
                                      "lastSyncDateTime", "enrolledDateTime", "managedDeviceOwnerType", "complianceState"]),
    "jamf-computers.csv": ("jamf", ["general.name", "hardware.serialNumber", "hardware.model", "operatingSystem.version", "userAndLocation.email",
                                    "general.lastContactTime", "general.lastEnrolledDate"]),
    "purchases.csv": ("purchases", ["Order number", "Vendor", "Serial", "Model", "Category", "Purchase date", "Warranty end", "Unit cost", "Ship to site"]),
    "office-register.csv": ("register", ["Asset tag", "Serial", "Category", "Model", "Manufacturer", "Site", "Room", "Assigned to", "State", "Purchase date"]),
    "hr.csv": ("hr", ["Employee ID", "Name", "UPN", "Site", "Department", "Status", "Start date", "Leave date"]),
    "stock.csv": ("stock", ["Site", "Category", "Model", "On hand", "Minimum"]),
}


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _iso(t: datetime | None) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else ""


def _d(t: date | None) -> str:
    return t.isoformat() if t else ""


def _rows() -> dict[str, list]:
    rnd = random.Random(SEED)
    today = AS_OF.date()
    out = {k: [] for k, _ in FILES.values()}
    used_serials: set[str] = set()
    tags = {"seq": 1000}

    def dell_tag() -> str:
        while True:
            s = "".join(rnd.choice("BCDFGHJKLMNPQRSTVWXYZ0123456789") for _ in range(7))
            if s not in used_serials and not s.isdigit():
                used_serials.add(s)
                return s

    def apple_serial() -> str:
        while True:
            s = rnd.choice(["C02", "FVF", "H4T", "K9X"]) + "".join(rnd.choice("CDFGHJKLMNPQRTVWXY0123456789") for _ in range(7 if rnd.random() < .5 else 9))
            if s not in used_serials:
                used_serials.add(s)
                return s

    def other_serial(prefix: str) -> str:
        while True:
            s = prefix + "".join(rnd.choice("0123456789ABCDEF") for _ in range(8))
            if s not in used_serials:
                used_serials.add(s)
                return s

    def tag() -> str:
        tags["seq"] += 1
        return f"CM-{tags['seq']:05d}"

    def day(a: date, b: date) -> date:
        return a + timedelta(days=rnd.randint(0, (b - a).days))

    def recent(max_days: float = 5) -> datetime:
        return AS_OF - timedelta(minutes=rnd.randint(20, int(max_days * 1440)))

    def buy(vendor, order, serial, model, cat, when, years, cost, site):
        out["purchases"].append([order, vendor, serial, model, cat, _d(when), _d(when.replace(year=when.year + years)), f"{cost:.2f}", site])

    # ---------------------------------------------------------------- people
    names = [f"{f} {l}" for f in FIRST for l in LAST]
    rnd.shuffle(names)
    people = []
    emp = [20100]

    def person(name, site, dept, status="Active", start=None, end=None):
        emp[0] += rnd.choice([1, 2, 3])
        f, l_ = name.split(" ", 1)
        upn = _ascii(f"{f}.{l_.replace(' ', '')}@{DOMAIN}").lower()
        p = dict(id=f"CM{emp[0]}", name=name, upn=upn, site=site, dept=dept, status=status,
                 start=start or day(date(2014, 1, 1), date(2026, 6, 30)), end=end)
        people.append(p)
        return p

    k = 0
    for site, depts in DEPTS.items():
        for dept, n in depts:
            for _ in range(n):
                person(names[k], site, dept)
                k += 1
    # joiners with no laptop yet (PPL-04): the last three people of the roster are replaced by recent starters
    joiners = []
    for site, dept, start in (("Madrid", "Sales", date(2026, 10, 19)), ("Madrid", "Operations", date(2026, 10, 26)), ("Paris", "Sales", date(2026, 10, 26))):
        p = next(x for x in reversed(people) if x["site"] == site and x["dept"] == dept and x not in joiners)
        p["start"] = start
        joiners.append(p)
    leavers = []
    for site, dept, end in (("Madrid", "Sales", date(2026, 9, 18)), ("Madrid", "Trading", date(2026, 9, 30)), ("Paris", "Research", date(2026, 10, 2)),
                            ("Amsterdam", "Sales", date(2026, 10, 9)), ("Madrid", "Operations", date(2026, 10, 26))):
        leavers.append(person(names[k], site, dept, "Leaver", day(date(2017, 1, 1), date(2024, 1, 1)), end))
        k += 1
    for site, dept, end in (("Madrid", "Finance", date(2026, 8, 31)), ("Paris", "Sales", date(2026, 9, 15)), ("Madrid", "Technology", date(2026, 10, 16))):
        person(names[k], site, dept, "Leaver", day(date(2017, 1, 1), date(2024, 1, 1)), end)
        k += 1
    active = [p for p in people if p["status"] == "Active"]

    # ---------------------------------------------------------------- end-user computers
    computers = []          # (person, kind, serial)

    def laptop_model(when: date, mac: bool) -> str:
        if mac:
            return ("MacBook Pro (14-inch, 2021)" if when < date(2023, 2, 1) else "MacBook Pro (14-inch, 2023)" if when < date(2024, 1, 1)
                    else "MacBook Pro (14-inch, Nov 2023)" if when < date(2025, 4, 1) else "MacBook Air (13-inch, M4, 2025)")
        return ("Latitude 7420" if when < date(2022, 4, 1) else "Latitude 7430" if when.year <= 2022 else "Latitude 7440" if when.year == 2023
                else "Latitude 7450")

    def windows_laptop(p, when, order, in_mdm=True, last=None, user=None, enrolled=None, purchase=True, model=None):
        st = dell_tag()
        model = model or laptop_model(when, False)
        if purchase:
            buy(DELL, order, st, model, "Laptop", when, 3, 1380.0 if when.year < 2024 else 1450.0, p["site"] if p else "Madrid")
        if in_mdm:
            code = SITES[p["site"]][0]
            out["intune"].append([f"CM-{code}-L{len(computers) + 101:04d}", st, model, "Dell Inc.", "Windows",
                                  rnd.choice(["10.0.26100.6899", "10.0.26100.6584", "10.0.22631.5909"]), user if user is not None else p["upn"],
                                  _iso(last or recent()), _iso(enrolled or datetime.combine(when + timedelta(days=rnd.randint(5, 30)), datetime.min.time()) + timedelta(hours=10)),
                                  "company", "compliant" if rnd.random() < .95 else "noncompliant"])
        computers.append((p, "laptop", st))
        return st

    def mac_laptop(p, when, order):
        sn = apple_serial()
        model = laptop_model(when, True)
        buy(APPLE, order, sn, model, "Laptop", when, 3, 2350.0, p["site"])
        code = SITES[p["site"]][0]
        out["jamf"].append([f"CM-{code}-M{len(computers) + 101:04d}", sn, model, rnd.choice(["15.7.1", "26.0.1", "15.6.1"]), p["upn"], _iso(recent(3)),
                            _iso(datetime.combine(when + timedelta(days=rnd.randint(5, 20)), datetime.min.time()) + timedelta(hours=11))])
        computers.append((p, "laptop", sn))

    windows = [p for p in active if p not in joiners and not (p["dept"] in ("Research", "Marketing"))]
    macs = [p for p in active if p not in joiners and p["dept"] in ("Research", "Marketing")]
    # the nine laptops in Intune that no inventory record knows (COV-01): bought outside the Dell portal
    missing = [p for p in windows if p["dept"] in ("Sales", "Operations")]
    rnd.shuffle(missing)
    missing = sorted([p for p in missing if p["site"] == "Madrid"][:6] + [p for p in missing if p["site"] == "Paris"][:2]
                     + [p for p in missing if p["site"] == "Amsterdam"][:1], key=lambda p: p["id"])
    madrid = [p for p in windows if p["site"] == "Madrid" and p not in missing]
    others = [p for p in windows if p["site"] != "Madrid" and p not in missing]
    rnd.shuffle(madrid)
    rnd.shuffle(others)
    # Madrid: the refresh wave of May-June 2023 (due Q2-2027), the Q1-2023 batch (due Q1-2027), late 2022 and an overdue tail
    plan = ([(date(2023, 5, 8), date(2023, 6, 23), "DLL-2023-05")] * 70 + [(date(2023, 1, 9), date(2023, 3, 24), "DLL-2023-01")] * 14
            + [(date(2022, 11, 7), date(2022, 12, 16), "DLL-2022-11")] * 4 + [(date(2022, 3, 1), date(2022, 9, 30), "DLL-2022-03")] * 7)
    for i, p in enumerate(madrid):
        a, b, o = plan[i] if i < len(plan) else (date(2024, 2, 1), date(2026, 6, 30), "DLL-2024-02")
        when = day(a, b)
        windows_laptop(p, when, f"{o}{rnd.randint(100, 999)}")
    for i, p in enumerate(others):
        a, b, o = ((date(2022, 2, 1), date(2022, 6, 30), "DLL-2022-02") if i < 3 else (date(2023, 9, 4), date(2023, 12, 15), "DLL-2023-09") if i < 12
                   else (date(2024, 1, 8), date(2026, 5, 29), "DLL-2024-01"))
        windows_laptop(p, day(a, b), f"{o}{rnd.randint(100, 999)}")
    for p in missing:
        windows_laptop(p, day(date(2025, 2, 3), date(2026, 6, 12)), "", purchase=False, model="Latitude 7450")
    for p in macs:
        when = day(date(2022, 4, 1), date(2026, 3, 31))
        mac_laptop(p, when, f"PRW-{when.year}-{rnd.randint(1000, 9999)}")
    # trading floor desktops, bought together in June 2022 (due Q2-2027)
    traders = [p for p in active if p["dept"] == "Trading"]
    for i, p in enumerate(traders):
        st = dell_tag()
        when = date(2022, 6, 14)
        buy(DELL, "DLL-2022-06-TF", st, "Precision 3660 Tower", "Desktop", when, 5, 1890.0, "Madrid")
        out["intune"].append([f"CM-MAD-TD{i + 1:03d}", st, "Precision 3660 Tower", "Dell Inc.", "Windows", "10.0.26100.6899", p["upn"], _iso(recent(1)),
                              "2022-06-28T10:00:00Z", "company", "compliant"])
        computers.append((p, "desktop", st))

    # planted on end-user devices --------------------------------------------------------------
    by_person = {}
    for p, kind, sn in computers:
        by_person.setdefault(p["id"], []).append(sn)
    intune_by_serial = {r[1]: r for r in out["intune"]}
    # not seen for 30+ days (COV-02)
    stale = [p for p in madrid[90:94]]
    for p, ago in zip(stale, (38, 52, 95, 140)):
        intune_by_serial[by_person[p["id"]][0]][7] = _iso(AS_OF - timedelta(days=ago, hours=3))
    # bought, never enrolled, in nobody's hands (COV-02 and COV-04)
    buy(DELL, "DLL-2025-03417", dell_tag(), "Latitude 7450", "Laptop", date(2025, 3, 12), 3, 1450.0, "Paris")
    # re-enrolled laptop: two Intune records for one serial (COV-03, information)
    dup = intune_by_serial[by_person[others[5]["id"]][0]]
    out["intune"].append([dup[0] + "-OLD", dup[1], dup[2], dup[3], dup[4], "10.0.22631.4317", dup[6], _iso(AS_OF - timedelta(days=61)), "2024-03-11T09:12:00Z",
                          "company", "noncompliant"])
    # model mismatch: the purchase says Latitude 7440, Intune says Latitude 5440 (COV-03)
    mm = by_person[madrid[30]["id"]][0]
    intune_by_serial[mm][2] = "Latitude 5440"
    # meeting room mini PC with a placeholder serial (COV-03)
    out["intune"].append(["CM-MAD-MR-PC01", "To be filled by O.E.M.", "NUC 13 Pro Kit", "ASUSTeK COMPUTER INC.", "Windows", "10.0.26100.6899",
                          "", _iso(recent(1)), "2025-01-20T12:00:00Z", "company", "compliant"])
    # two people still holding their old laptop after the refresh (PPL-03): old 2022 laptop still in Intune under their name
    for p in (madrid[5], madrid[20]):
        windows_laptop(p, day(date(2022, 2, 1), date(2022, 2, 25)), f"DLL-2022-02{rnd.randint(100, 999)}", last=recent(9))
    # leavers: four past the 14 days, one inside it (PPL-01/02); the first still syncing after leaving and with a phone
    for i, p in enumerate(leavers):
        when = day(date(2024, 1, 8), date(2025, 12, 12))
        last = AS_OF - timedelta(days=3, hours=2) if i == 0 else datetime.combine(p["end"], datetime.min.time()) - timedelta(hours=rnd.randint(2, 30))
        if p["dept"] == "Research":
            sn = apple_serial()
            buy(APPLE, f"PRW-{when.year}-{rnd.randint(1000, 9999)}", sn, laptop_model(when, True), "Laptop", when, 3, 2350.0, p["site"])
            out["jamf"].append([f"CM-PAR-M{len(computers) + 101:04d}", sn, laptop_model(when, True), "15.7.1", p["upn"], _iso(last), _iso(datetime.combine(when, datetime.min.time()))])
            computers.append((p, "laptop", sn))
        else:
            windows_laptop(p, when, f"DLL-{when.year}-{rnd.randint(10000, 99999)}", last=last)
    # a laptop retired in the register but still syncing (LCM-04)
    retired_sn = windows_laptop(madrid[44], date(2022, 1, 18), "DLL-2022-01377", last=AS_OF - timedelta(days=9))

    # ---------------------------------------------------------------- phones
    phone_people = [p for p in active if p["dept"] in ("Trading", "Sales", "Technology") and p not in joiners]
    rnd.shuffle(phone_people)
    phone_people = sorted(phone_people[:70], key=lambda p: p["id"]) + [leavers[0]]
    for i, p in enumerate(phone_people):
        android = i % 7 == 3
        when = day(date(2023, 11, 1), date(2026, 6, 30))
        model = (("Galaxy S24" if when >= date(2024, 2, 1) else "Galaxy S23") if android else "iPhone 16" if when >= date(2024, 10, 1)
                 else "iPhone 15")
        sn = other_serial("R5C" if android else "F")
        buy(MOBILE, f"WM-{when.year}{when.month:02d}-{rnd.randint(100, 999)}", sn, ("Samsung " if android else "Apple ") + model, "Phone", when, 2,
            690.0 if android else 790.0, p["site"])
        out["intune"].append([f"{p['upn'].split('@')[0]}_{'Android' if android else 'iPhone'}", sn, model, "samsung" if android else "Apple",
                              "Android" if android else "iOS", "15" if android else rnd.choice(["18.7", "26.0.1"]), p["upn"],
                              _iso(AS_OF - timedelta(days=2, hours=4) if p is leavers[0] else recent(2)),
                              _iso(datetime.combine(when + timedelta(days=3), datetime.min.time())), "company", "compliant"])
    # personal (BYOD) phones: left out of the inventory
    for p in sorted(rnd.sample([x for x in active if x not in phone_people], 25), key=lambda p: p["id"]):
        android = rnd.random() < .4
        out["intune"].append([f"{p['upn'].split('@')[0]}_{'Android' if android else 'iPhone'}", other_serial("P"), "Pixel 8" if android else "iPhone 13",
                              "Google" if android else "Apple", "Android" if android else "iOS", "15" if android else "18.6", p["upn"], _iso(recent(4)),
                              "2025-05-06T08:00:00Z", "personal", "compliant"])

    # ---------------------------------------------------------------- office register: monitors, docks, rooms, printers, spares
    reg = out["register"]

    def item(cat, model, maker, site, room, assigned, state, when, vendor=DELL, years=3, cost=None, order=None, serial=None, buy_it=True):
        sn = serial or (dell_tag() if maker == "Dell" else other_serial(maker[:2].upper()))
        reg.append([tag(), sn, cat, model, maker, site, room, assigned, state, _d(when) if not buy_it else ""])
        if buy_it and when:
            buy(vendor, order or f"DLL-{when.year}-{rnd.randint(10000, 99999)}", sn, model, cat, when, years, cost or SETTINGS["unit_costs"][cat.lower()], site)
        return sn

    desk = [p for p in active if p["dept"] != "Trading" and p not in joiners]
    for i, p in enumerate(desk):
        site = p["site"]
        if site == "Madrid" and i % 4 == 0 and i < 100:
            when = day(date(2020, 9, 1), date(2020, 10, 15))           # the 2020 batch: overdue
            mon = "P2720D"
        else:
            when = day(date(2021, 3, 1), date(2025, 11, 28))
            mon = "P2720D" if when.year < 2022 else "P2723DE" if when.year < 2025 else "P2725HE"
        item("Monitor", f"Dell {mon}", "Dell", site, "Open office", p["upn"], "Deployed", when)
        if p["dept"] not in ("Research", "Marketing"):
            dwhen = when if when.year >= 2023 else day(date(2021, 4, 1), date(2021, 6, 30)) if i % 5 == 0 else day(date(2023, 1, 9), date(2025, 6, 30))
            item("Dock", "Dell WD19S" if dwhen.year < 2023 else "Dell WD22TB4", "Dell", site, "Open office", p["upn"], "Deployed", dwhen)
    # one person with three monitors (PPL-03)
    for _ in range(2):
        item("Monitor", "Dell P2723DE", "Dell", "Madrid", "Open office", madrid[60]["upn"], "Deployed", date(2024, 4, 22))
    # trading floor: four monitors per desk, assigned to the desk
    for i, p in enumerate(traders):
        for _ in range(4):
            item("Monitor", "Dell U2722D", "Dell", "Madrid", "Trading floor", f"Desk MAD-TF-{i + 1:02d}", "Deployed", date(2022, 6, 14), order="DLL-2022-06-TF")
    # monitors with no site and nobody (COV-04), docks with nobody (COV-04)
    for _ in range(3):
        item("Monitor", "Dell P2723DE", "Dell", "", "", "", "Deployed", date(2023, 11, 6))
    for _ in range(2):
        item("Dock", "Dell WD22TB4", "Dell", "Paris", "Open office", "", "Deployed", date(2024, 2, 19))
    # a monitor typed twice in the register (COV-03)
    dsn = item("Monitor", "Dell P2723DE", "Dell", "Madrid", "Open office", madrid[70]["upn"], "Deployed", date(2023, 3, 2))
    reg.append([tag(), dsn, "Monitor", "Dell P2723DE", "Dell", "Madrid", "Open office", madrid[71]["upn"], "Deployed", ""])
    # a dock lent to a contractor HR does not know (PPL-05)
    item("Dock", "Dell WD22TB4", "Dell", "Madrid", "Open office", f"ext.tom.hale@{DOMAIN}", "Deployed", date(2024, 9, 9))
    # meeting rooms
    for site, rooms in ROOMS.items():
        for j, room in enumerate(rooms):
            when = date(2021, 5, 17) if (site == "Madrid" and j < 2) else day(date(2022, 1, 10), date(2024, 10, 30))
            no_date = site == "Amsterdam" and j == 1
            item("Meeting room", "Logitech Rally Bar", "Logitech", site, room, room, "Deployed", None if no_date else when, vendor="Northwind AV",
                 years=2, cost=3800, buy_it=not no_date)
            item("Meeting room", "Samsung QM65R display", "Samsung", site, room, room, "Deployed", when, vendor="Northwind AV", years=3, cost=1900)
    # printers
    for site, n in (("Madrid", 3), ("Paris", 2), ("Amsterdam", 1)):
        for j in range(n):
            no_date = site == "Paris" and j == 1
            when = day(date(2019, 6, 1), date(2022, 6, 30))
            item("Printer", "HP Color LaserJet Enterprise MFP M480f" if j % 2 == 0 else "Canon imageRUNNER ADVANCE C3525i III",
                 "HP" if j % 2 == 0 else "Canon", site, "Print area", f"Print area {site} {j + 1}", "Deployed", None if no_date else when,
                 vendor="Fabrikam Office Supplies", years=3, cost=1400, buy_it=not no_date)
    # spare laptops in stock, two in repair, the retired one
    for site, n in (("Madrid", 6), ("Paris", 3), ("Amsterdam", 2)):
        for _ in range(n):
            item("Laptop", "Latitude 7450", "Dell", site, "IT store", "", "In stock", day(date(2025, 11, 3), date(2026, 9, 25)), cost=1450)
    item("Laptop", "Latitude 7430", "Dell", "Madrid", "IT store", "", "In stock", date(2022, 4, 11), cost=1380)       # old spare (LCM-04)
    for p in (madrid[50], madrid[51]):
        sn = by_person[p["id"]][0]
        r = intune_by_serial[sn]
        r[7] = _iso(AS_OF - timedelta(days=rnd.randint(33, 45)))
        reg.append([tag(), sn, "Laptop", r[2], "Dell", "Madrid", "IT store", p["upn"], "In repair (Dell RMA)", ""])
    reg.append([tag(), retired_sn, "Laptop", "Latitude 7430", "Dell", "Madrid", "IT store", "", "Retired", ""])

    # ---------------------------------------------------------------- comms rooms (Device42)
    d42 = out["d42"]

    def dev(name, model, maker, bld, room, rack, u, owner, level, os_, ver, when, warranty, eos="", serial=None, vendor=None, cost=None, years=5):
        sn = serial if serial is not None else (dell_tag() if maker == "Dell" else other_serial({"Cisco": "FOC", "Fortinet": "FG", "APC": "AS",
                                                                                                 "HPE": "CZ", "Supermicro": "SM"}.get(maker, "X")))
        d42.append([name, sn, "", model, maker, bld, room, rack, u, "yes", owner, level, os_, ver, "2026-10-29T22:00:00Z",
                    "" if vendor else _d(when), "" if vendor else _d(warranty), eos])
        if vendor:
            buy(vendor, f"DLL-{when.year}-SRV{rnd.randint(100, 999)}", sn, model, "Server", when, years, cost, "Madrid" if bld == "MAD-HQ" else "Paris")
        return sn

    M, P = ("MAD-HQ", "Comms room CR-1"), ("PAR-01", "Salle technique")
    NET, INF, TT = "Network", "Infrastructure", "Trading Technology"
    crit = "Production - critical"
    dev("mad-core-sw01", "Cisco Catalyst 9500-24Y4C", "Cisco", *M, "R01", "40", NET, crit, "IOS-XE", "17.12.4", date(2021, 12, 13), date(2026, 12, 11))
    dev("mad-core-sw02", "Cisco Catalyst 9500-24Y4C", "Cisco", *M, "R02", "40", NET, crit, "IOS-XE", "17.12.4", date(2021, 12, 13), date(2027, 9, 30))
    for i in range(3):        # past end of support (CR-01); one with no firmware recorded (CR-04)
        dev(f"mad-acc-sw0{i + 1}", "Cisco Catalyst 3850-48P", "Cisco", *M, "R03", str(38 - i * 2), NET, "Production", "IOS-XE",
            "" if i == 2 else "16.12.11", date(2017, 3, 6), date(2025, 10, 31))
    for i in range(6):
        when = date(2022, 9, 5) if i < 3 else date(2024, 2, 12)
        dev(f"mad-acc-sw{i + 4:02d}", "Cisco Catalyst 9300-48P", "Cisco", *M, "R03" if i < 2 else "R04", str(30 - i * 2), NET, "Production", "IOS-XE",
            "17.12.4", when, when.replace(year=when.year + 5))
    dev("mad-tf-sw01", "Cisco Catalyst 9300-48UXM", "Cisco", *M, "R02", "36", TT, crit, "IOS-XE", "17.12.4", date(2022, 6, 14), date(2027, 6, 14))
    for i in range(2):
        dev(f"mad-rtr0{i + 1}", "Cisco ISR 4431", "Cisco", *M, "R01" if i == 0 else "R02", "42", NET, crit, "IOS-XE", "17.9.6a", date(2020, 2, 3), date(2027, 2, 2))
        dev(f"mad-fw0{i + 1}", "FortiGate 200F", "Fortinet", *M, "R01" if i == 0 else "R02", "38", NET, crit, "FortiOS", "7.4.8", date(2023, 3, 20), date(2028, 3, 20))
    for i in range(4):
        dev(f"mad-esx0{i + 1}", "PowerEdge R650", "Dell", *M, "R04", str(20 - i * 2), INF, "Production", "VMware ESXi", "8.0.3", date(2022, 10, 3), None,
            vendor=DELL, cost=10800)
    dev("mad-file01", "PowerEdge R640", "Dell", *M, "R04", "10", INF, "Production", "Windows Server 2019", "1809", date(2019, 5, 20), None, vendor=DELL,
        cost=8900)                                                                                    # out of warranty, overdue
    for i in range(2):
        dev(f"mad-app0{i + 1}", "ProLiant DL380 Gen10", "HPE", *M, "R03", str(10 - i * 2), INF if i == 0 else "", "Production", "Windows Server 2019",
            "1809", date(2020, 11, 16), date(2025, 11, 15))                                          # one without an owner (CR-03)
    dev("mad-mkt01", "Supermicro SYS-1029P-WTR", "Supermicro", *M, "R02", "30", TT, crit, "Red Hat Enterprise Linux", "9.4", date(2021, 9, 13), date(2026, 9, 12))
    for i in range(6):
        dev(f"mad-pdu-r0{i // 2 + 1}{'ab'[i % 2]}", "APC AP8941 Rack PDU", "APC", *M, f"R0{i // 2 + 1}", "" if i == 5 else "0", INF, "", "", "",
            date(2019, 9, 2), date(2022, 9, 1))
    dev("mad-ups01", "APC Smart-UPS SRT 10kVA", "APC", M[0], M[1], "", "", INF, crit, "", "", date(2023, 4, 17), date(2026, 4, 16))
    for i in range(8):
        dev(f"mad-pp-r0{i // 2 + 1}-{i % 2 + 1}", "Cat6A 24-port patch panel", "Panduit", *M, "" if i == 7 else f"R0{i // 2 + 1}",
            "" if i == 7 else str(44 - (i % 2)), NET, "", "", "", None, None, serial="")
    # Paris
    dev("par-core-sw01", "Cisco Catalyst 9300-48P", "Cisco", *P, "R01", "40", NET, crit, "IOS-XE", "", date(2022, 2, 21), date(2027, 2, 21))   # CR-04
    dev("par-acc-sw01", "Cisco Catalyst 9300-48P", "Cisco", *P, "R01", "38", NET, "Production", "IOS-XE", "17.12.4", date(2022, 2, 21), date(2027, 2, 21))
    dev("par-rtr01", "Cisco ISR 4331", "Cisco", *P, "R01", "42", NET, crit, "IOS-XE", "17.9.6a", date(2021, 6, 7), date(2027, 6, 6))
    dev("par-fw01", "FortiGate 100F", "Fortinet", *P, "R01", "36", NET, crit, "FortiOS", "7.4.8", date(2023, 5, 8), date(2028, 5, 8))
    dev("par-esx01", "PowerEdge R650", "Dell", *P, "R02", "20", INF, "Production", "VMware ESXi", "8.0.3", date(2022, 1, 17), None, vendor=DELL,
        cost=10800, years=5)
    dev("par-esx02", "PowerEdge R650", "Dell", *P, "R02", "18", INF, "Production", "VMware ESXi", "8.0.3", date(2022, 1, 17), None, vendor=DELL,
        cost=10800, years=5)
    for i in range(2):
        dev(f"par-pdu-r0{i + 1}", "APC AP8941 Rack PDU", "APC", *P, f"R0{i + 1}", "0", INF, "", "", "", date(2021, 6, 7), date(2024, 6, 6))
    dev("par-ups01", "APC Smart-UPS SRT 6kVA", "APC", P[0], P[1], "", "", INF, crit, "", "", date(2022, 3, 14), date(2025, 3, 13))
    for i in range(3):
        dev(f"par-pp-r01-{i + 1}", "Cat6A 24-port patch panel", "Panduit", *P, "R01", str(44 - i), NET, "", "", "", None, None, serial="")
    # the Paris servers' Dell warranty: one ends in 77 days
    for r in out["purchases"]:
        if r[3] == "PowerEdge R650" and r[8] == "Paris":
            r[6] = "2027-01-15"
            break

    # ---------------------------------------------------------------- HR and stock
    for p in sorted(people, key=lambda x: x["id"]):
        out["hr"].append([p["id"], p["name"], p["upn"], p["site"], p["dept"], p["status"], _d(p["start"]), _d(p["end"])])
    out["stock"] = [["Madrid", "Laptop", "Latitude 7450", 6, 5], ["Madrid", "Desktop", "Precision 3680 Tower", 2, 2], ["Madrid", "Monitor", "Dell P2725HE", 3, 10],
                    ["Madrid", "Dock", "Dell WD22TB4", 8, 6], ["Madrid", "Phone", "iPhone 16", 4, 3],
                    ["Paris", "Laptop", "Latitude 7450", 3, 3], ["Paris", "Monitor", "Dell P2725HE", 6, 4], ["Paris", "Dock", "Dell WD22TB4", 1, 2],
                    ["Paris", "Phone", "iPhone 16", 2, 2],
                    ["Amsterdam", "Laptop", "Latitude 7450", 2, 2], ["Amsterdam", "Monitor", "Dell P2725HE", 4, 2], ["Amsterdam", "Dock", "Dell WD22TB4", 2, 1],
                    ["Amsterdam", "Phone", "iPhone 16", 1, 1]]
    out["intune"].sort(key=lambda r: r[0])
    out["jamf"].sort(key=lambda r: r[0])
    out["purchases"].sort(key=lambda r: (r[5], r[0], r[2]))
    return out


def write(folder: Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rows = _rows()
    for name, (k, header) in FILES.items():
        with open(folder / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(header)
            w.writerows(rows[k])
    (folder / "settings.json").write_text(json.dumps(SETTINGS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return folder
