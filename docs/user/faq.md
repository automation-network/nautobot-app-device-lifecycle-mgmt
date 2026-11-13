# Frequently Asked Questions

## Can Device Lifecycle App integrate directly with Cisco End of Sale/Support `EoX` API?

Although not natively built in to the app at this time, this can be achieved by writing a Nautobot Job that interacts with the Cisco EoX API. 

## Does this app support integration with other vendor's hardware/software API's such as Juniper, Palo Alto, Aruba, Arista, etc...?

The **EOSL.ai - Import Hardware Notices** Job imports hardware lifecycle data from
[EOSL.ai's public API](https://eosl.ai/api/v1/families.json). It is a third-party data
source, rather than a direct vendor API integration.

### Create Hardware Notices for existing devices

1. Install the updated app and restart Nautobot and its Celery workers.
2. Find **EOSL.ai - Import Hardware Notices** under **Jobs** and enable the Job if required.
3. Choose **Source**: **EOSL.ai API** or **Bundled local JSON files**. Optionally
   select a manufacturer. Leave **Dry run** enabled for the first run.
4. Review the job logs, then run again with **Dry run** disabled to create the notices.
5. Run **Device Hardware Notice Report** to refresh report results. You can schedule
   the import job to discover notices for device types added later.

The job creates one Hardware Notice per device type used by at least one existing
device. Existing notices are preserved, including manually entered dates. It does
not create devices, device types, or inventory-part notices.

Matching requires the same manufacturer name (ignoring punctuation and case) and
an exact SKU in the family's detail response. The device type's part number takes
precedence; if absent, its model is used. Manufacturer aliases and fuzzy family
matches are deliberately not inferred. Unmatched models, conflicting lifecycle
records, computed EOSL dates, and records without sale/support dates are skipped
with a warning. Review unmatched manufacturer names and device type part numbers
before rerunning; broad series names alone may not identify an individual SKU.

EOSL.ai often supplies dates as `YYYY-MM`. Nautobot requires a day, so the job uses
the **last day of that month**. Original dates, vendor source links, and this
conversion rule are recorded in the notice comments. The documentation link points
to the EOSL.ai family. Review the vendor source before relying on dates for support
decisions. Missing dates are left blank; EOSL maps to End of Support, End of Sale
maps to End of Sale, security support maps to End of Security Patches, and software
maintenance maps to End of Software Releases.

In API mode, the worker needs outbound HTTPS access to `eosl.ai`; no API key is
required. In local mode, no HTTP session or API requests are made, and missing
files do not trigger an API fallback. An HTTP, missing-file, or malformed-response
error stops collection before new notices are written. Repeated runs preserve
existing notices rather than refreshing their dates.

### Bundle local EOSL files in the app

The app includes the `2026-11` snapshot downloaded on 2026-11-06: the index and
all 3,299 family detail files under `nautobot_device_lifecycle_mgmt/data/epsl/`.

Before building/installing the app, add JSON snapshots using this layout:

```text
nautobot_device_lifecycle_mgmt/
  data/
    epsl/
      families.json
      family/
        juniper-m160.json
        ...
```

Save the index response from `https://eosl.ai/api/v1/families.json` as
`families.json`. Save each required entry's `detail` response under `family/`
using the filename from that URL. Keep the original JSON structure and URLs;
the Job translates these URLs into local file paths. The index alone is
insufficient because exact SKU records and lifecycle dates live in detail files.

You may provide a subset index containing only the families you have downloaded.
Every indexed family for a manufacturer being imported needs its detail file,
even when that family ultimately has no matching device type.

These JSON files are explicitly included in wheels and source distributions.
Install the updated package on every Nautobot worker, then select **Bundled local
JSON files** in the Job. Files on your browser's computer are not read by the
worker. The bundled snapshot's generation date is recorded in the index. Local
mode uses that snapshot; select API mode for live data. Refresh the index and its
family detail files together when updating the bundled snapshot.

## Why do I now see `Software Version (DLM)` in Devices and Inventory Items list views?

Previously, Devices and Inventory Items list views displayed duplicate Software Version columns one from Nautobot core and one provided by the Device Lifecycle Management (DLM) app.

To avoid confusion, the DLM-managed column is now explicitly labeled `Software Version (DLM)`.
