# Data format

Put the files in one folder and run `python -m assetplan review <folder>`. At least one inventory source is required: `device42-devices.csv`, `office-register.csv` or `purchases.csv`. Every other file adds its checks when present. Comma, semicolon or tab separated, UTF-8. Column names are matched loosely (case, accents and punctuation are ignored), and the common alternatives below, in English and Spanish, are accepted, including the names the Device42, Microsoft Graph and Jamf Pro APIs use.

## How the inventory is built

Every row of every source is joined by **serial number** (service tag), ignoring case, spaces and dashes. Placeholder serials (`To be filled by O.E.M.`, `Default string`, `0`, `System Serial Number`) are never matched: they are reported as COV-03. Items without a serial are kept by Device42 name or by asset tag.

| Field | Taken from, in this order |
|---|---|
| Category | Device42 type or model, register category, purchase category, then the MDM model and operating system |
| Site | Device42 building, register site, the HR site of the assigned user, then the purchase ship-to site |
| Owner | Device42 customer; the register's assigned user or room; for laptops, desktops, phones and tablets the MDM user (`userPrincipalName`, Jamf user and location) wins |
| State | The register state, Device42 `in_service` (no means in stock); otherwise deployed |
| Purchase date, warranty | Device42 (custom fields), register, purchases; with no purchase at all, the MDM enrolment date as an estimate |
| Replacement date | Purchase date plus `refresh_years` of the category; for comms room equipment the end-of-support date if it comes first |

## device42-devices.csv

The comms rooms as Device42 holds them: racks, network equipment, servers, PDUs, UPS and patch panels. `scripts/Export-AssetData.ps1` writes it from `GET /api/1.0/devices/all/`.

| Column | Also accepted | Notes |
|---|---|---|
| name | device name, hostname | |
| serial_no | serial number, service tag | Empty for patch panels is fine |
| asset_no | asset tag | |
| hw_model, manufacturer | hardware model, model | The category is guessed from the model when there is no type: Catalyst or Nexus → switch, ISR → router, FortiGate → firewall, PowerEdge or ProLiant → server, PDU, Smart-UPS → ups, patch panel |
| device_sub_type | object category, category, type | Optional: switch, router, firewall, server, storage, pdu, ups, patch panel |
| building, room, rack, start_at | site, sala, U position | `start_at` is the U position in the rack. `site_aliases` maps building names to sites |
| in_service | | `no` counts as a spare (in stock) |
| customer | owner, department | The owner of the device |
| service_level | criticality | Levels in `critical_service_levels` make a warranty ending within `warranty_critical_days` critical |
| os, osver | firmware, software version | Empty version on network equipment and servers is CR-04 |
| Purchase date, Warranty end, End of support | fin garantía, LDoS | Custom fields if you keep them in Device42. End of support can also come from `end_of_support` in settings.json, per model |

## intune-devices.csv

Microsoft Graph `GET /deviceManagement/managedDevices` (`Get-MgDeviceManagementManagedDevice -All`).

| Column | Notes |
|---|---|
| deviceName, serialNumber, model, manufacturer | |
| operatingSystem, osVersion | Windows, macOS, iOS, Android: used for the category when nothing else gives it |
| userPrincipalName | The user of the device: the owner of a laptop, desktop or phone |
| lastSyncDateTime | Not synced for `not_seen_days` is COV-02 |
| enrolledDateTime | Estimated purchase date when no purchase record exists |
| managedDeviceOwnerType | `personal` devices (BYOD) are left out of the inventory and counted |
| complianceState | Copied to the inventory |

## jamf-computers.csv

Jamf Pro API computers inventory, sections GENERAL, HARDWARE, USER_AND_LOCATION and OPERATING_SYSTEM.

| Column | Also accepted | Notes |
|---|---|---|
| general.name | computer name | |
| hardware.serialNumber | serial number | |
| hardware.model | model | |
| operatingSystem.version | os version | |
| userAndLocation.email | email, userAndLocation.username, username | The owner |
| general.lastContactTime | last check in, last contact | Compared with `not_seen_days` |
| general.lastEnrolledDate | last enrolled | Estimated purchase date when no purchase record exists |

## purchases.csv

The vendor's order or warranty report: one line per serial.

| Column | Also accepted | Notes |
|---|---|---|
| Order number | order, PO, pedido | |
| Vendor | supplier, reseller | |
| Serial | service tag, número de serie | Two lines with the same serial are COV-03 |
| Model, Category | product, tipo | |
| Purchase date, Warranty end | order date, ship date, fin garantía | |
| Unit cost | price, precio | `1.450,00 €` and `1,450.00` are both read |
| Ship to site | site, sede | Last fallback for the site |

## office-register.csv

The hardware no MDM sees (monitors, docks, meeting room kit, printers), and the state of anything that is not simply deployed: spares in stock, devices in repair or RMA, to be retired, retired.

| Column | Also accepted | Notes |
|---|---|---|
| Asset tag | etiqueta | |
| Serial | service tag | Two register lines with the same serial are COV-03 |
| Category, Model, Manufacturer | tipo, modelo, marca | laptop, desktop, phone, tablet, monitor (pantalla), dock (base), meeting room, printer (impresora) |
| Site, Room | sede, sala, puesto | |
| Assigned to | user, asignado a | A UPN for a person, or a room or desk name |
| State | estado | in stock (almacén, spare), deployed (en uso), in repair (RMA), to be retired, retired (baja) |
| Purchase date | fecha compra | For items with no purchase line |

## hr.csv

| Column | Also accepted | Notes |
|---|---|---|
| Employee ID, Name | numero empleado, nombre | |
| UPN | email, correo | Matched with the MDM user and the register |
| Site, Department | sede, departamento | |
| Status | estado | `leaver`, `terminated`, `baja`... or a leave date in the past |
| Start date, Leave date | fecha alta, fecha baja | Joiners count from their start date; leavers have `leaver_return_days` to return their devices |

## stock.csv

| Column | Also accepted | Notes |
|---|---|---|
| Site, Category, Model | sede, categoria | One line per site and item you keep spares of |
| On hand, Minimum | quantity, mínimo | Below the minimum is STK-01 |

## settings.json

| Key | Default | What |
|---|---|---|
| `organisation`, `as_of` | | Name for the reports; reference date (otherwise today) |
| `currency` | € | For the forecast |
| `not_seen_days` | 30 | A deployed laptop, desktop or phone not seen in MDM for longer is COV-02 |
| `warranty_warn_days`, `warranty_critical_days`, `critical_service_levels` | 90, 45, critical | Warranty ending soon; critical within the shorter window for those service levels |
| `eos_warn_days` | 365 | End of support coming (information) |
| `leaver_return_days` | 14 | Days a leaver has to return the devices |
| `refresh_years` | laptop 4, desktop 5, phone 3, tablet 4, monitor 6, dock 5, meeting room 5, printer 6, switch / router / firewall 7, server 5, storage 5, pdu 10, ups 4, patch panel none | Replacement age per category. For the UPS it is the battery |
| `unit_costs` | | Replacement cost per category for the forecast |
| `max_per_person` | laptop 1, desktop 1, phone 1, tablet 1, monitor 2, dock 1 | PPL-03 |
| `computer_required` | true | Active people need a laptop or desktop (PPL-04) |
| `end_of_support` | | Model → date, when Device42 does not carry it. Take the dates from the vendor's end-of-life notices |
| `rack_categories`, `stock_categories` | | What must have a rack and U position; what the stock check covers |
| `forecast_quarters`, `wave_share` | 4, 0.4 | Quarters in the forecast; one quarter with this share of the cost or more is FC-02 |
| `site_aliases` | | Building or office names → site |
| `owners` | | Owner per area: coverage, comms, lifecycle, people, stock, forecast |

The quarters are calendar quarters. The forecast shows the overdue backlog, the rest of the current quarter and the next `forecast_quarters` quarters; the stock check uses the replacements due by the end of next quarter.
