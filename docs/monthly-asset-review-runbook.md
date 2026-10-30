# Monthly asset review runbook

One morning at the end of each month: export, run, fix what cannot wait, and take the pack to the monthly review with the site IT team and, once a quarter, to the budget owner. The tool only reads exports; records are corrected in Device42, Intune, Jamf Pro and the register themselves.

## Before the review (45 minutes)

1. Device42, Intune and Jamf Pro (read-only):
   ```powershell
   .\scripts\Export-AssetData.ps1 -OutputFolder .\data -Device42Url https://device42.corp.contoso.com -JamfUrl https://contoso.jamfcloud.com -JamfClientId <client id>
   ```
   The first run asks an administrator to consent to DeviceManagementManagedDevices.Read.All. The Device42 user and the Jamf Pro API client only need read rights.
2. Purchases: the vendor's order or warranty report for the last five years, by serial, as `purchases.csv`. Add the orders bought outside the vendor portal.
3. The office register (`office-register.csv`) with this month's moves, repairs and disposals, the stock counts per site (`stock.csv`) and the HR roster with leavers of the last three months (`hr.csv`).
4. Check `settings.json`: `as_of`, the refresh policy, unit costs and the end-of-support dates of the comms room models.
5. Build the outputs:
   ```bash
   python -m assetplan review data/ --title "IT asset review · October 2026"
   ```

## The same day

| Order | What | Output | Who |
|---|---|---|---|
| 1 | Leavers with devices past the return date: manager and HR, then lock or wipe | `people.csv`, PPL-02 | Service desk |
| 2 | Comms room devices past end of support or a critical warranty ending: renewal or replacement in the change calendar | `comms-rooms.csv`, CR-01, CR-02 | Network & infrastructure |
| 3 | Devices in MDM that the inventory does not know: find the order, tag them, register them | `coverage.csv`, COV-01 | Site IT |
| 4 | Laptops not seen for 30+ days: ask the user; recover, enrol or record as lost | `coverage.csv`, COV-02 | Site IT |
| 5 | Stock below the minimum and the orders for next quarter | `stock-plan.csv` | Site IT |

## The monthly review (30 minutes)

| Minutes | Topic | From the pack (`asset-review.md`) |
|---|---|---|
| 5 | Overall status and status per area | Summary |
| 10 | Coverage and people: what is missing, what is not seen, what leavers still hold | Headlines, Findings |
| 5 | Comms rooms: end of support, warranties, records to fix in Device42 | Findings |
| 5 | Stock orders and next quarter's replacements | Stock orders |
| 5 | Forecast and backlog, actions and owners | Forecast for the budget, Actions |

Once a quarter, take the forecast to the budget owner: the next four quarters by category and site, and the overdue backlog apart, because it is not in any budget yet. A quarter with half of the year's cost (FC-02) is a refresh wave: start part of it earlier or agree the capacity to deploy it.

Keep each month's output folder (pack, CSVs and exports) to compare month by month.

## How to read it

- **The serial number is the key.** If two systems disagree on the model for one serial, one of them has the wrong serial; check the label.
- **Not seen is not fine.** A laptop that has not synced for six weeks is in a drawer, broken, lost or with someone who left.
- **What MDM sees and nobody bought is still yours.** Laptops bought on a card or through another reseller have no warranty record and no replacement date until someone registers them.
- **A device returned is a device unassigned.** As long as the MDM user or the register says a leaver has it, it counts as not returned.
- **End of support beats age for the comms rooms.** A switch bought five years ago is still due now if the vendor stopped supporting it.
- **Device42 is only as good as its last walk-through.** Rack and U position, owner and firmware are what you need at 3 a.m.; fix them in Device42 when the report lists them.
