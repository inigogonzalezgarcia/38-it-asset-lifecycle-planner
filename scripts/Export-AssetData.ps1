<#
.SYNOPSIS
    Read-only export of the Device42 devices (comms rooms), the Intune managed devices and the Jamf Pro computers, written as the CSV files
    that assetplan reads.

.DESCRIPTION
    Only GET requests to read data, plus the token requests Jamf Pro needs to authenticate. Nothing is created, changed or deleted in
    Device42, Intune or Jamf Pro. No credential is written to disk: they are asked for at run time and kept in memory.

    Device42 (REST API, basic authentication with Get-Credential; a read-only user is enough):
      - device42-devices.csv: GET /api/1.0/devices/all/ page by page with limit and offset until total_count is reached.
                              Columns: name, serial_no, asset_no, hw_model, manufacturer, building, room, rack, start_at (U position),
                              in_service, customer, service_level, os, osver, last_updated, and the custom fields named in -CustomFields
                              (by default 'Purchase date', 'Warranty end' and 'End of support', if your instance records them that way).
                              Purchases and warranty can also come from purchases.csv (by serial), and end-of-support dates per model from
                              settings.json. The default API GET limit of the appliance is 1,000 records per request.
                              The JSON keys can differ between Device42 versions: compare one record (-Verbose prints the first one) with
                              the columns above.

    Intune (Microsoft Graph PowerShell SDK, module Microsoft.Graph.DeviceManagement), delegated permission
    DeviceManagementManagedDevices.Read.All, consented once by an administrator:
      - intune-devices.csv:   Get-MgDeviceManagementManagedDevice -All (GET /deviceManagement/managedDevices), with deviceName,
                              serialNumber, model, manufacturer, operatingSystem, osVersion, userPrincipalName, lastSyncDateTime,
                              enrolledDateTime, managedDeviceOwnerType and complianceState.

    Jamf Pro (Jamf Pro API):
      - jamf-computers.csv:   an API client (client ID and secret, POST /api/oauth/token with grant_type=client_credentials) with the
                              "Read Computers" privilege, or a user account (POST /api/v1/auth/token with basic authentication); then
                              GET <JamfInventoryPath>?section=GENERAL&section=HARDWARE&section=USER_AND_LOCATION&section=OPERATING_SYSTEM
                              with page and page-size until totalCount is reached. The token is invalidated at the end.
                              Jamf Pro versions the inventory endpoint (v1, v2, v3...): check the API reference of your instance
                              (https://<your-instance>/api/doc) and pass -JamfInventoryPath if it is not /api/v1/computers-inventory.

    Not exported here, because they live elsewhere: purchases.csv (the vendor's order or warranty report), office-register.csv (your
    register), hr.csv (HR system report) and stock.csv (stock register). See docs/data-format.md for their columns.

.PARAMETER OutputFolder
    Where the CSV files are written (created if missing).

.PARAMETER Device42Url
    Base URL of the Device42 appliance, for example https://device42.corp.contoso.com. Leave empty to skip Device42.

.PARAMETER JamfUrl
    Base URL of Jamf Pro, for example https://contoso.jamfcloud.com. Leave empty to skip Jamf Pro.

.PARAMETER JamfClientId
    Client ID of a Jamf Pro API client; the secret is asked for at run time. Without it, a Jamf Pro user and password are asked for.

.EXAMPLE
    .\scripts\Export-AssetData.ps1 -OutputFolder .\data -Device42Url https://device42.corp.contoso.com -JamfUrl https://contoso.jamfcloud.com -JamfClientId 0f1e2d3c-aaaa-bbbb-cccc-123456789abc

.EXAMPLE
    # Intune only
    .\scripts\Export-AssetData.ps1 -OutputFolder .\data
#>
[CmdletBinding()]
param(
    [string] $OutputFolder = '.\data',
    [string] $Device42Url = '',
    [int] $Device42PageSize = 500,
    [string[]] $CustomFields = @('Purchase date', 'Warranty end', 'End of support'),
    [switch] $SkipIntune,
    [string] $TenantId = '',
    [string] $JamfUrl = '',
    [string] $JamfClientId = '',
    [string] $JamfInventoryPath = '/api/v1/computers-inventory',
    [int] $JamfPageSize = 200
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputFolder | Out-Null

function Write-Csv([object[]] $Rows, [string] $Name) {
    $path = Join-Path $OutputFolder $Name
    $Rows | Export-Csv -Path $path -NoTypeInformation -Encoding utf8
    Write-Host ("{0,6} rows -> {1}" -f @($Rows).Count, $path)
}

function Get-BasicHeader([pscredential] $Credential) {
    $pair = '{0}:{1}' -f $Credential.UserName, $Credential.GetNetworkCredential().Password
    @{ Authorization = 'Basic ' + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pair)); Accept = 'application/json' }
}

# ---------------------------------------------------------------- Device42
if ($Device42Url) {
    $cred = Get-Credential -Message "Device42 user (read-only) for $Device42Url"
    $headers = Get-BasicHeader $cred
    $base = $Device42Url.TrimEnd('/')
    $devices = [System.Collections.Generic.List[object]]::new()
    $offset = 0
    do {
        $page = Invoke-RestMethod -Method Get -Headers $headers -Uri "$base/api/1.0/devices/all/?limit=$Device42PageSize&offset=$offset"
        $batch = @($page.Devices)
        if ($offset -eq 0 -and $batch.Count) { Write-Verbose ($batch[0] | ConvertTo-Json -Depth 4) }
        foreach ($d in $batch) { $devices.Add($d) }
        $offset += $batch.Count
        Write-Verbose "Device42: $offset of $($page.total_count)"
    } while ($batch.Count -gt 0 -and $offset -lt [int] $page.total_count)

    $rows = foreach ($d in $devices) {
        $row = [ordered] @{
            name = $d.name; serial_no = $d.serial_no; asset_no = $d.asset_no; hw_model = $d.hw_model; manufacturer = $d.manufacturer
            building = $d.building; room = $d.room; rack = $d.rack; start_at = $d.start_at; in_service = $d.in_service
            customer = $d.customer; service_level = $d.service_level; os = $d.os; osver = $d.osver; last_updated = $d.last_updated
        }
        foreach ($f in $CustomFields) {
            $cf = @($d.custom_fields) | Where-Object { $_.key -eq $f } | Select-Object -First 1
            $row[$f] = if ($cf) { $cf.value } else { '' }
        }
        [pscustomobject] $row
    }
    Write-Csv $rows 'device42-devices.csv'
}

# ---------------------------------------------------------------- Intune
if (-not $SkipIntune) {
    Import-Module Microsoft.Graph.DeviceManagement
    $connect = @{ Scopes = 'DeviceManagementManagedDevices.Read.All'; NoWelcome = $true }
    if ($TenantId) { $connect.TenantId = $TenantId }
    Connect-MgGraph @connect
    $props = 'deviceName', 'serialNumber', 'model', 'manufacturer', 'operatingSystem', 'osVersion', 'userPrincipalName', 'lastSyncDateTime',
             'enrolledDateTime', 'managedDeviceOwnerType', 'complianceState'
    $md = Get-MgDeviceManagementManagedDevice -All -Property $props
    $rows = foreach ($m in $md) {
        [pscustomobject] @{
            deviceName = $m.DeviceName; serialNumber = $m.SerialNumber; model = $m.Model; manufacturer = $m.Manufacturer
            operatingSystem = $m.OperatingSystem; osVersion = $m.OsVersion; userPrincipalName = $m.UserPrincipalName
            lastSyncDateTime = if ($m.LastSyncDateTime) { $m.LastSyncDateTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') } else { '' }
            enrolledDateTime = if ($m.EnrolledDateTime) { $m.EnrolledDateTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') } else { '' }
            managedDeviceOwnerType = "$($m.ManagedDeviceOwnerType)"; complianceState = "$($m.ComplianceState)"
        }
    }
    Write-Csv $rows 'intune-devices.csv'
    Disconnect-MgGraph | Out-Null
}

# ---------------------------------------------------------------- Jamf Pro
if ($JamfUrl) {
    $base = $JamfUrl.TrimEnd('/')
    if ($JamfClientId) {
        $secret = Read-Host -AsSecureString "Client secret for Jamf Pro API client $JamfClientId"
        $plain = [System.Net.NetworkCredential]::new('', $secret).Password
        $tok = Invoke-RestMethod -Method Post -Uri "$base/api/oauth/token" -ContentType 'application/x-www-form-urlencoded' `
               -Body @{ grant_type = 'client_credentials'; client_id = $JamfClientId; client_secret = $plain }
        $token = $tok.access_token
        $plain = $null
    } else {
        $cred = Get-Credential -Message "Jamf Pro user (read computers) for $base"
        $tok = Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/token" -Headers (Get-BasicHeader $cred)
        $token = $tok.token
    }
    $h = @{ Authorization = "Bearer $token"; Accept = 'application/json' }
    $sections = 'section=GENERAL&section=HARDWARE&section=USER_AND_LOCATION&section=OPERATING_SYSTEM'
    $all = [System.Collections.Generic.List[object]]::new()
    $page = 0
    try {
        do {
            $r = Invoke-RestMethod -Method Get -Headers $h -Uri "$base$($JamfInventoryPath)?$sections&page=$page&page-size=$JamfPageSize&sort=id%3Aasc"
            foreach ($c in @($r.results)) { $all.Add($c) }
            $page++
            Write-Verbose "Jamf Pro: $($all.Count) of $($r.totalCount)"
        } while (@($r.results).Count -gt 0 -and $all.Count -lt [int] $r.totalCount)
    } finally {
        try { Invoke-RestMethod -Method Post -Uri "$base/api/v1/auth/invalidate-token" -Headers $h | Out-Null } catch { Write-Verbose 'token already expired' }
    }
    $rows = foreach ($c in $all) {
        [pscustomobject] @{
            'general.name'              = $c.general.name
            'hardware.serialNumber'     = $c.hardware.serialNumber
            'hardware.model'            = $c.hardware.model
            'operatingSystem.version'   = $c.operatingSystem.version
            'userAndLocation.email'     = if ($c.userAndLocation.email) { $c.userAndLocation.email } else { $c.userAndLocation.username }
            'general.lastContactTime'   = $c.general.lastContactTime
            'general.lastEnrolledDate'  = $c.general.lastEnrolledDate
        }
    }
    Write-Csv $rows 'jamf-computers.csv'
}

Write-Host "Done. Add purchases.csv, office-register.csv, hr.csv and stock.csv, check settings.json, then run: python -m assetplan review $OutputFolder"
