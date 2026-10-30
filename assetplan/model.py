"""Loading: the Device42 export of the comms rooms, the Intune managed devices and Jamf Pro computers, the vendor purchases with warranty,
the office register of the hardware no MDM sees, the HR roster, the stock register and settings.json, with forgiving column names
(Device42 API, Microsoft Graph and Jamf Pro API names included, and common Spanish ones), into plain dataclasses."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

D42_ALIASES = {
    "name": ["name", "device name", "hostname", "device", "nombre"],
    "serial": ["serial_no", "serial no", "serial number", "serial", "service tag", "numero de serie"],
    "asset_tag": ["asset_no", "asset no", "asset number", "asset tag", "etiqueta"],
    "category": ["device_sub_type", "device sub type", "object_category", "object category", "category", "device type", "type", "tipo"],
    "model": ["hw_model", "hw model", "hardware", "hardware model", "model", "modelo"],
    "manufacturer": ["manufacturer", "vendor", "make", "fabricante"],
    "building": ["building", "site", "location", "edificio", "sede"],
    "room": ["room", "sala"],
    "rack": ["rack"],
    "position": ["start_at", "start at", "u position", "rack u", "position", "posicion"],
    "in_service": ["in_service", "in service", "en servicio"],
    "owner": ["customer", "owner", "department", "responsable", "cliente"],
    "service_level": ["service_level", "service level", "criticality", "nivel de servicio"],
    "os": ["os", "operating system", "firmware name", "sistema operativo"],
    "os_version": ["osver", "os version", "firmware", "firmware version", "software version", "version"],
    "purchase_date": ["purchase date", "purchased", "fecha compra"],
    "warranty_end": ["warranty end", "warranty end date", "warranty expiry", "support end", "fin garantia"],
    "eos": ["end of support", "end_of_support", "eos", "ldos", "last date of support", "fin de soporte"],
}
INTUNE_ALIASES = {
    "name": ["devicename", "device name", "name"],
    "serial": ["serialnumber", "serial number", "serial"],
    "model": ["model"],
    "manufacturer": ["manufacturer"],
    "os": ["operatingsystem", "operating system", "os"],
    "os_version": ["osversion", "os version"],
    "user": ["userprincipalname", "user principal name", "primary user upn", "upn", "emailaddress", "email address"],
    "last_seen": ["lastsyncdatetime", "last sync date time", "last check in", "last sync"],
    "enrolled": ["enrolleddatetime", "enrolled date time", "enrollment date", "enrolled"],
    "owner_type": ["manageddeviceownertype", "managed device owner type", "ownership", "owner type"],
    "compliance": ["compliancestate", "compliance state", "compliance"],
}
JAMF_ALIASES = {
    "name": ["general name", "general.name", "computer name", "name"],
    "serial": ["hardware serialnumber", "hardware.serialnumber", "serial number", "serialnumber", "serial"],
    "model": ["hardware model", "hardware.model", "model"],
    "manufacturer": ["hardware make", "hardware.make", "make", "manufacturer"],
    "os_version": ["operatingsystem version", "operatingsystem.version", "os version", "operating system version"],
    "user": ["userandlocation email", "userandlocation.email", "email", "email address", "userandlocation username", "userandlocation.username",
             "username", "user"],
    "last_seen": ["general lastcontacttime", "general.lastcontacttime", "last check in", "last contact", "lastcontacttime", "last contact time",
                  "general lastcontact", "general.lastcontact"],
    "enrolled": ["general lastenrolleddate", "general.lastenrolleddate", "last enrolled", "enrolled", "lastenrolleddate"],
}
PURCHASE_ALIASES = {
    "order": ["order number", "order", "order no", "po", "purchase order", "pedido"],
    "serial": ["serial", "serial number", "service tag", "serial no", "numero de serie"],
    "model": ["model", "product", "description", "item", "modelo"],
    "category": ["category", "type", "product type", "categoria", "tipo"],
    "purchase_date": ["purchase date", "order date", "ship date", "invoice date", "fecha compra"],
    "warranty_end": ["warranty end", "warranty end date", "warranty expiry", "support end", "fin garantia"],
    "cost": ["unit cost", "unit price", "price", "cost", "coste", "precio"],
    "vendor": ["vendor", "supplier", "reseller", "proveedor"],
    "site": ["ship to site", "ship to", "site", "delivery site", "sede"],
}
REGISTER_ALIASES = {
    "asset_tag": ["asset tag", "asset", "tag", "asset no", "etiqueta"],
    "serial": ["serial", "serial number", "service tag", "numero de serie"],
    "category": ["category", "type", "kind", "categoria", "tipo"],
    "model": ["model", "description", "modelo"],
    "manufacturer": ["manufacturer", "make", "brand", "fabricante", "marca"],
    "site": ["site", "office", "location", "sede", "oficina"],
    "room": ["room", "area", "desk", "sala", "puesto"],
    "assigned": ["assigned to", "assigned user", "user", "upn", "owner", "assigned", "asignado a", "usuario"],
    "state": ["state", "status", "lifecycle state", "estado"],
    "purchase_date": ["purchase date", "purchased", "fecha compra"],
}
HR_ALIASES = {
    "employee_id": ["employee id", "employeeid", "employee number", "id", "numero empleado"],
    "name": ["name", "full name", "display name", "nombre"],
    "upn": ["upn", "userprincipalname", "email", "work email", "correo"],
    "site": ["site", "office", "location", "sede", "oficina"],
    "status": ["status", "employment status", "estado"],
    "start": ["start date", "hire date", "start", "fecha alta"],
    "end": ["leave date", "end date", "termination date", "last day", "fecha baja"],
    "department": ["department", "dept", "departamento"],
}
STOCK_ALIASES = {
    "site": ["site", "office", "location", "sede"],
    "category": ["category", "item", "type", "categoria"],
    "model": ["model", "description", "modelo"],
    "on_hand": ["on hand", "quantity", "qty", "stock", "available", "cantidad", "disponible"],
    "minimum": ["minimum", "min", "minimum level", "reorder level", "minimo"],
}

CATEGORIES = ("laptop", "desktop", "phone", "tablet", "monitor", "dock", "meeting room", "printer", "switch", "router", "firewall", "server",
              "storage", "pdu", "ups", "patch panel", "other")
MDM_CATEGORIES = ("laptop", "desktop", "phone", "tablet")
COMMS_CATEGORIES = ("switch", "router", "firewall", "server", "storage", "pdu", "ups", "patch panel")
NETWORK_CATEGORIES = ("switch", "router", "firewall")
STATES = ("in stock", "deployed", "in repair", "to be retired", "retired")
CATEGORY_WORDS = [  # checked in order: the first match wins
    ("patch panel", ("patch panel", "patch", "panel de parcheo", "parcheo")),
    ("pdu", ("pdu",)),
    ("ups", ("ups", "smart ups", "sai")),
    ("firewall", ("firewall", "fortigate", "palo alto", "asa", "cortafuegos")),
    ("router", ("router", "isr", "asr", "enrutador")),
    ("switch", ("switch", "catalyst", "nexus", "aruba cx", "conmutador")),
    ("storage", ("storage", "powerstore", "powervault", "netapp", "nas", "san", "almacenamiento")),
    ("server", ("server", "poweredge", "proliant", "supermicro", "thinksystem", "servidor")),
    ("dock", ("dock", "docking", "wd19", "wd22", "base", "dockstation")),
    ("monitor", ("monitor", "display", "screen", "pantalla")),
    ("printer", ("printer", "mfp", "laserjet", "imagerunner", "impresora")),
    ("meeting room", ("meeting room", "teams room", "teams rooms", "rally", "room kit", "videobar", "sala de reuniones")),
    ("phone", ("phone", "iphone", "android", "galaxy", "pixel", "movil", "telefono")),
    ("tablet", ("tablet", "ipad", "tableta")),
    ("desktop", ("desktop", "tower", "optiplex", "imac", "mac mini", "mac studio", "sobremesa", "sff", "nuc", "mini pc")),
    ("laptop", ("laptop", "notebook", "latitude", "precision", "xps", "macbook", "thinkpad", "elitebook", "surface laptop", "portatil")),
]
STATE_WORDS = [
    ("retired", ("retired", "disposed", "scrapped", "recycled", "written off", "baja", "retirado", "desechado")),
    ("to be retired", ("to be retired", "to retire", "pending disposal", "end of life", "eol", "para retirar", "pendiente de baja")),
    ("in repair", ("repair", "rma", "broken", "faulty", "reparacion", "averiado")),
    ("in stock", ("stock", "spare", "storage", "available", "unassigned", "almacen", "disponible", "repuesto")),
    ("deployed", ("deployed", "in use", "assigned", "active", "in service", "production", "asignado", "en uso", "desplegado")),
]
PLACEHOLDER_SERIALS = {"", "0", "none", "null", "na", "n a", "default string", "to be filled by o e m", "system serial number", "123456789",
                       "0123456789", "not specified", "unknown"}
YES = {"yes", "y", "true", "1", "si", "x", "in service", "on"}
LEAVER_WORDS = {"leaver", "left", "terminated", "termination", "withdrawn", "inactive", "baja", "former", "exited"}
DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M", "%d/%m/%Y", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M", "%d %b %Y", "%d-%b-%Y", "%b %d, %Y")

DEFAULT_REFRESH = {"laptop": 4, "desktop": 5, "phone": 3, "tablet": 4, "monitor": 6, "dock": 5, "meeting room": 5, "printer": 6, "switch": 7,
                   "router": 7, "firewall": 7, "server": 5, "storage": 5, "pdu": 10, "ups": 4, "patch panel": None, "other": None}
DEFAULT_COSTS = {"laptop": 1450, "desktop": 1650, "phone": 750, "tablet": 650, "monitor": 260, "dock": 230, "meeting room": 3800, "printer": 1400,
                 "switch": 6500, "router": 4800, "firewall": 9000, "server": 11000, "storage": 25000, "pdu": 900, "ups": 1600, "patch panel": 0,
                 "other": 0}
DEFAULT_OWNERS = {"coverage": "Site IT lead", "comms": "Network & infrastructure lead", "lifecycle": "Site IT lead", "people": "Service desk lead",
                  "stock": "Site IT lead", "forecast": "IT budget owner"}


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(ch for ch in s if not unicodedata.combining(ch))).strip()


def key(v) -> str:
    return str(v or "").strip().lower()


def serial_key(v) -> str:
    """Matching key for serial numbers and service tags: case, spaces and dashes ignored; placeholders give ''."""
    s = re.sub(r"[\s\-_.]+", "", str(v or "")).upper()
    return "" if _norm(v) in PLACEHOLDER_SERIALS or len(s) < 4 or len(set(s)) == 1 else s


def is_placeholder(v) -> bool:
    return bool(str(v or "").strip()) and not serial_key(v)


def parse_dt(v) -> datetime | None:
    s = str(v or "").strip()
    if not s or _norm(s) in {"never", "n a", "na", "none", "null", "0"} or s.startswith("0001-01-01"):
        return None
    s = re.sub(r"(\.\d+)?(Z|[+-]\d{2}:?\d{2})$", "", s)      # ISO with offset: kept as written (Graph and Jamf return UTC)
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def parse_date(v) -> date | None:
    d = parse_dt(v)
    return d.date() if d else None


def yes(v) -> bool:
    return _norm(v) in YES


def num(v) -> float | None:
    s = re.sub(r"[^\d,.\-]", "", str(v or ""))
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if len(s.split(",")[-1]) != 3 else s.replace(",", "")
    elif s.count(".") > 1 or ("." in s and len(s.split(".")[-1]) == 3):
        s = s.replace(".", "")          # 1.450 or 1.450.000: thousands separators
    try:
        return float(s)
    except ValueError:
        return None


def _words(text: str) -> str:
    return f" {_norm(text)} "


def category_of(*texts: str) -> str:
    """Category from an explicit value or from the model and the name: 'Latitude 7450' -> laptop, 'Catalyst 9300-48P' -> switch."""
    for t in texts:
        w = _words(t)
        if not w.strip():
            continue
        if w.strip() in CATEGORIES:
            return w.strip()
        for cat, words in CATEGORY_WORDS:
            if any(f" {x} " in w for x in words):
                return cat
    return "other"


def mdm_category(model: str, os_name: str, name: str = "") -> str:
    o = _norm(os_name)
    m = _words(model)
    if "ios" in o.split() or "iphone" in m:
        return "tablet" if " ipad " in m else "phone"
    if "ipados" in o or " ipad " in m:
        return "tablet"
    if "android" in o:
        return "tablet" if " tab " in m or "tablet" in m else "phone"
    c = category_of(model, name)
    if c in ("laptop", "desktop"):
        return c
    return "laptop" if ("mac" in o or "windows" in o) else c


def state_of(v) -> str:
    w = _words(v)
    for st, words in STATE_WORDS:
        if any(f" {x} " in w for x in words):
            return st
    return ""


def _read(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        header = fh.readline()
        fh.seek(0)
        delim = max(",;\t", key=header.count)
        reader = csv.DictReader(fh, delimiter=delim)
        return list(reader.fieldnames or []), list(reader)


def _rows(path: Path, aliases: dict[str, list[str]]) -> list[dict]:
    fields, raw = _read(path)
    heads = {_norm(h): h for h in fields}
    cols = {}
    for k, names in aliases.items():
        for n in [k.replace("_", " ")] + names:
            if _norm(n) in heads and heads[_norm(n)] not in cols.values():
                cols[k] = heads[_norm(n)]
                break
    return [{k: (r.get(c) or "").strip() for k, c in cols.items()} for r in raw]


# ---------------------------------------------------------------- records

@dataclass
class CommsDevice:          # one Device42 device
    name: str
    serial: str = ""
    asset_tag: str = ""
    category: str = "other"
    model: str = ""
    manufacturer: str = ""
    building: str = ""
    room: str = ""
    rack: str = ""
    position: str = ""
    in_service: bool = True
    owner: str = ""
    service_level: str = ""
    os: str = ""
    os_version: str = ""
    purchase_date: date | None = None
    warranty_end: date | None = None
    eos: date | None = None


@dataclass
class MdmDevice:            # one Intune managed device or Jamf Pro computer
    source: str             # "Intune" or "Jamf"
    name: str
    serial: str = ""
    model: str = ""
    manufacturer: str = ""
    os: str = ""
    os_version: str = ""
    user: str = ""
    last_seen: datetime | None = None
    enrolled: datetime | None = None
    owner_type: str = "company"
    compliance: str = ""

    @property
    def personal(self) -> bool:
        return _norm(self.owner_type) == "personal"


@dataclass
class Purchase:
    serial: str
    model: str = ""
    category: str = "other"
    order: str = ""
    purchase_date: date | None = None
    warranty_end: date | None = None
    cost: float | None = None
    vendor: str = ""
    site: str = ""


@dataclass
class RegisterItem:
    asset_tag: str
    serial: str = ""
    category: str = "other"
    model: str = ""
    manufacturer: str = ""
    site: str = ""
    room: str = ""
    assigned: str = ""
    state: str = ""
    purchase_date: date | None = None


@dataclass
class Person:
    employee_id: str
    name: str = ""
    upn: str = ""
    site: str = ""
    status: str = "active"
    start: date | None = None
    end: date | None = None
    department: str = ""

    def left(self, today: date) -> bool:
        return (self.end is not None and self.end <= today) or any(w in _norm(self.status).split() for w in LEAVER_WORDS)

    def active(self, today: date) -> bool:
        return not self.left(today) and (self.start is None or self.start <= today)


@dataclass
class StockLine:
    site: str
    category: str
    model: str = ""
    on_hand: int = 0
    minimum: int = 0


@dataclass
class Settings:
    organisation: str = "IT asset review"
    as_of: datetime | None = None
    currency: str = "€"
    not_seen_days: int = 30
    warranty_warn_days: int = 90
    warranty_critical_days: int = 45
    eos_warn_days: int = 365
    critical_service_levels: list[str] = field(default_factory=lambda: ["critical", "production critical", "tier 1"])
    leaver_return_days: int = 14
    refresh_years: dict = field(default_factory=lambda: dict(DEFAULT_REFRESH))
    unit_costs: dict = field(default_factory=lambda: dict(DEFAULT_COSTS))
    max_per_person: dict = field(default_factory=lambda: {"laptop": 1, "desktop": 1, "phone": 1, "tablet": 1, "monitor": 2, "dock": 1})
    computer_required: bool = True
    end_of_support: dict = field(default_factory=dict)          # model -> date, when the export does not carry it
    rack_categories: list[str] = field(default_factory=lambda: ["switch", "router", "firewall", "server", "storage", "pdu", "patch panel"])
    stock_categories: list[str] = field(default_factory=lambda: ["laptop", "desktop", "phone", "monitor", "dock"])
    forecast_quarters: int = 4
    wave_share: float = 0.4
    site_aliases: dict = field(default_factory=dict)            # building or office name -> site
    owners: dict = field(default_factory=lambda: dict(DEFAULT_OWNERS))

    def owner(self, area: str) -> str:
        return self.owners.get(area) or DEFAULT_OWNERS.get(area, "IT")

    def years(self, category: str) -> float | None:
        v = num(self.refresh_years.get(category))
        return v if v else None

    def cost(self, category: str) -> float:
        return float(num(self.unit_costs.get(category)) or 0)

    def site(self, v: str) -> str:
        if not v:
            return ""
        for alias, site in self.site_aliases.items():
            if _norm(alias) == _norm(v):
                return site
        return v.strip()


def settings_from_dict(raw: dict) -> Settings:
    s = Settings()
    for k, v in raw.items():
        if not hasattr(s, k) or v is None:
            continue
        cur = getattr(s, k)
        if k == "as_of":
            s.as_of = parse_dt(v)
        elif k in ("refresh_years", "unit_costs", "max_per_person"):
            cur.update({category_of(c) if category_of(c) != "other" else _norm(c): x for c, x in v.items()})
        elif k == "end_of_support":
            s.end_of_support = {_norm(m): parse_date(x) for m, x in v.items() if parse_date(x)}
        elif k in ("rack_categories", "stock_categories"):
            setattr(s, k, [category_of(x) for x in v])
        elif k == "critical_service_levels":
            s.critical_service_levels = [_norm(x) for x in v]
        elif k == "owners":
            cur.update(v)
        elif isinstance(cur, bool):
            s.computer_required = bool(v) if k == "computer_required" else cur
        elif isinstance(cur, int) and not isinstance(cur, bool):
            setattr(s, k, int(num(v) or 0))
        elif isinstance(cur, float):
            setattr(s, k, float(num(v) or 0))
        else:
            setattr(s, k, v)
    return s


@dataclass
class Data:
    settings: Settings
    as_of: datetime
    comms: list[CommsDevice] = field(default_factory=list)
    mdm: list[MdmDevice] = field(default_factory=list)
    purchases: list[Purchase] = field(default_factory=list)
    register: list[RegisterItem] = field(default_factory=list)
    people: list[Person] = field(default_factory=list)
    stock: list[StockLine] = field(default_factory=list)
    sources: dict = field(default_factory=dict)

    @property
    def today(self) -> date:
        return self.as_of.date()

    def person(self, upn: str) -> Person | None:
        if not hasattr(self, "_people"):
            self._people = {key(p.upn): p for p in self.people if p.upn}
        return self._people.get(key(upn))


# ---------------------------------------------------------------- loaders

def load_device42(path: Path, s: Settings | None = None) -> list[CommsDevice]:
    s = s or Settings()
    out = []
    for r in _rows(path, D42_ALIASES):
        if not (r.get("name") or r.get("serial")):
            continue
        model = r.get("model", "")
        cat = category_of(r.get("category", ""), model, r.get("name", ""))
        if cat in ("laptop", "desktop", "phone", "tablet", "other") and category_of(model, r.get("name", "")) in COMMS_CATEGORIES:
            cat = category_of(model, r.get("name", ""))
        eos = parse_date(r.get("eos")) or s.end_of_support.get(_norm(model))
        out.append(CommsDevice(r.get("name") or r.get("serial"), r.get("serial", ""), r.get("asset_tag", ""), cat, model, r.get("manufacturer", ""),
                               s.site(r.get("building", "")), r.get("room", ""), r.get("rack", ""), r.get("position", ""),
                               yes(r["in_service"]) if r.get("in_service") else True, r.get("owner", ""), r.get("service_level", ""),
                               r.get("os", ""), r.get("os_version", ""), parse_date(r.get("purchase_date")), parse_date(r.get("warranty_end")), eos))
    return out


def load_mdm(path: Path, source: str) -> list[MdmDevice]:
    aliases = INTUNE_ALIASES if source == "Intune" else JAMF_ALIASES
    out = []
    for r in _rows(path, aliases):
        if not (r.get("name") or r.get("serial")):
            continue
        os_name = r.get("os") or ("macOS" if source == "Jamf" else "")
        out.append(MdmDevice(source, r.get("name") or r.get("serial"), r.get("serial", ""), r.get("model", ""),
                             r.get("manufacturer") or ("Apple" if source == "Jamf" else ""), os_name, r.get("os_version", ""), r.get("user", ""),
                             parse_dt(r.get("last_seen")), parse_dt(r.get("enrolled")), r.get("owner_type") or "company", r.get("compliance", "")))
    return out


def load_purchases(path: Path, s: Settings | None = None) -> list[Purchase]:
    s = s or Settings()
    out = []
    for r in _rows(path, PURCHASE_ALIASES):
        if not r.get("serial"):
            continue
        out.append(Purchase(r["serial"], r.get("model", ""), category_of(r.get("category", ""), r.get("model", "")), r.get("order", ""),
                            parse_date(r.get("purchase_date")), parse_date(r.get("warranty_end")), num(r.get("cost")), r.get("vendor", ""),
                            s.site(r.get("site", ""))))
    return out


def load_register(path: Path, s: Settings | None = None) -> list[RegisterItem]:
    s = s or Settings()
    out = []
    for r in _rows(path, REGISTER_ALIASES):
        if not (r.get("asset_tag") or r.get("serial")):
            continue
        out.append(RegisterItem(r.get("asset_tag") or r.get("serial"), r.get("serial", ""), category_of(r.get("category", ""), r.get("model", "")),
                                r.get("model", ""), r.get("manufacturer", ""), s.site(r.get("site", "")), r.get("room", ""), r.get("assigned", ""),
                                state_of(r.get("state", "")), parse_date(r.get("purchase_date"))))
    return out


def load_hr(path: Path, s: Settings | None = None) -> list[Person]:
    s = s or Settings()
    return [Person(r.get("employee_id") or r.get("upn", ""), r.get("name", ""), r.get("upn", ""), s.site(r.get("site", "")), r.get("status") or "active",
                   parse_date(r.get("start")), parse_date(r.get("end")), r.get("department", ""))
            for r in _rows(path, HR_ALIASES) if r.get("employee_id") or r.get("upn")]


def load_stock(path: Path, s: Settings | None = None) -> list[StockLine]:
    s = s or Settings()
    return [StockLine(s.site(r.get("site", "")), category_of(r.get("category", ""), r.get("model", "")), r.get("model", ""),
                      int(num(r.get("on_hand")) or 0), int(num(r.get("minimum")) or 0))
            for r in _rows(path, STOCK_ALIASES) if r.get("site") and r.get("category")]


FILES = {  # file name: (loader key, description)
    "device42-devices.csv": "Device42 devices (comms rooms)",
    "intune-devices.csv": "Intune managed devices (Graph managedDevices)",
    "jamf-computers.csv": "Jamf Pro computers inventory",
    "purchases.csv": "Vendor purchases and warranty",
    "office-register.csv": "Office register (non-MDM hardware, spares, repairs)",
    "hr.csv": "HR roster",
    "stock.csv": "Stock register per site",
}


def _find(folder: Path, name: str) -> Path | None:
    p = folder / name
    if p.exists():
        return p
    stem = name.rsplit(".", 1)[0]
    alts = sorted(folder.glob(f"{stem}*.csv"))
    return alts[0] if alts else None


def load(folder: Path, as_of: datetime | None = None) -> Data:
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"no folder {folder}")
    sp = folder / "settings.json"
    s = settings_from_dict(json.loads(sp.read_text(encoding="utf-8"))) if sp.exists() else Settings()
    when = as_of or s.as_of or datetime.now().replace(second=0, microsecond=0)
    paths = {n: _find(folder, n) for n in FILES}
    if not any(paths[n] for n in ("device42-devices.csv", "office-register.csv", "purchases.csv")):
        raise FileNotFoundError(f"{folder}: need at least one inventory source: device42-devices.csv, office-register.csv or purchases.csv")
    d = Data(s, when)
    if paths["device42-devices.csv"]:
        d.comms = load_device42(paths["device42-devices.csv"], s)
    for n, src in (("intune-devices.csv", "Intune"), ("jamf-computers.csv", "Jamf")):
        if paths[n]:
            d.mdm += load_mdm(paths[n], src)
    if paths["purchases.csv"]:
        d.purchases = load_purchases(paths["purchases.csv"], s)
    if paths["office-register.csv"]:
        d.register = load_register(paths["office-register.csv"], s)
    if paths["hr.csv"]:
        d.people = load_hr(paths["hr.csv"], s)
    if paths["stock.csv"]:
        d.stock = load_stock(paths["stock.csv"], s)
    counts = {"device42-devices.csv": len(d.comms), "intune-devices.csv": sum(m.source == "Intune" for m in d.mdm),
              "jamf-computers.csv": sum(m.source == "Jamf" for m in d.mdm), "purchases.csv": len(d.purchases), "office-register.csv": len(d.register),
              "hr.csv": len(d.people), "stock.csv": len(d.stock)}
    d.sources = {n: counts[n] for n in FILES if paths[n]}
    return d


def add_years(d: date, years: float) -> date:
    whole = int(years)
    months = round((years - whole) * 12)
    y, m = d.year + whole + (d.month - 1 + months) // 12, (d.month - 1 + months) % 12 + 1
    try:
        return date(y, m, d.day)
    except ValueError:
        return date(y, m, 28)


def days(a: date, b: date) -> int:
    return (b - a).days


def quarter(d: date) -> str:
    return f"Q{(d.month - 1) // 3 + 1}-{d.year}"


def quarter_end(d: date, ahead: int = 0) -> date:
    q = (d.month - 1) // 3 + ahead
    y, q = d.year + q // 4, q % 4
    return date(y + (q == 3), 1, 1) - timedelta(days=1) if q == 3 else date(y, q * 3 + 4, 1) - timedelta(days=1)
