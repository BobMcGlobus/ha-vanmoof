# VanMoof S3/X3 — Home Assistant integration (skeleton)

A **standalone** HACS custom integration for the VanMoof S3/X3, talking to the
bike directly over BLE from Home Assistant — no Pi bridge, no MQTT layer.

It exposes:

- `sensor.*` — battery %, odometer (km, total_increasing), current speed (km/h)
- `lock.*` — the bike's digital lock (lock / unlock)

Under the hood it wraps [`pymoof`](https://github.com/quantsini/pymoof) and uses
Home Assistant's own Bluetooth stack (`bleak-retry-connector`), so the
connection is routed automatically through the **local adapter or any ESPHome
Bluetooth proxy** that can currently reach the bike.

> Status: v0.1.0 — first testable release. Auto-discovery is enabled, the
> `LockState` enum is verified against pymoof source, and `pymoof` is pinned.
> Still pending: a first run against a real bike (see *Not yet validated*).

---

## Install

**HACS (custom repository)**
1. HACS → ⋮ → *Custom repositories* → add `https://github.com/BobMcGlobus/ha-vanmoof`, category *Integration*.
2. Install *VanMoof S3/X3*, restart HA.

**Manual**
Copy `custom_components/vanmoof/` into `<config>/custom_components/`, restart HA.

Then: *Settings → Devices & Services → Add Integration → VanMoof*. Pick the bike
from the discovered-device list (or paste its MAC), then enter the encryption
key and user key id.

---

## Getting the encryption key + user key id

`pymoof` reads these from your VanMoof account. Two ways:

```bash
pip install pymoof
python -c "import asyncio; from pymoof.tools import retrieve_encryption_key as r; \
           asyncio.run(r.main())"   # follow the prompts (VanMoof login)
```

The tool returns, per bike, the `encryptionKey` (hex string → **Encryption key**)
and `userKeyId` (int → **User key id**).

**Caveat (post-bankruptcy):** VanMoof's servers changed hands (Lavoie). If the
account/API path is down when you try, extract the keys offline instead via
[`chwdt/vanmoof-tools`](https://github.com/chwdt/vanmoof-tools) (dumps the keys
stored on the bike over BLE). Once you have them, this integration never needs
the cloud again — it's fully local.

---

## Not yet validated

Everything below is code-complete but has **not been exercised against a real
bike** yet. Once you've run a bike through setup, confirm:

- **All reads return plausible values** — battery %, odometer, speed, lock
  state. The plan's `scratch_probe.py` (throwaway, not shipped) isolates this
  ahead of HA if you want.
- **Lock/unlock actually actuates** the bike. The `LockState` enum
  (`UNLOCKED=0x00`, `LOCKED=0x01`, `AWAITING_UNLOCK=0x02`) is verified against
  pymoof 0.0.6 source, but the round-trip through the bike isn't.
- **Auto-discovery fires.** HA should pop up "New device discovered" for the
  bike via the advertised BikeInfo service UUID
  `6acc5540-e631-4069-944d-b8ca7598ad50` (this is what pymoof's own
  `discover_bike` scans for). The manual *Add Integration → VanMoof* flow works
  regardless.

Known rough edge: a **wrong key** currently surfaces as a repeating
`ConfigEntryNotReady`/`UpdateFailed` retry loop rather than a clean auth error,
because `authenticate()` returns silently and only the first read raises. A
`ConfigEntryAuthFailed`-based reauth flow is the planned fix.

---

## Design notes / known trade-offs

- **Connect-per-poll.** Every 5 min: connect → `authenticate()` → read →
  disconnect. Politer to the bike than a persistent link (doesn't block the
  phone app, doesn't hold the radio), at the cost of a few seconds per cycle.
  If you want faster lock response or live speed, switch to a persistent
  connection + GATT notifications and drop the poll — the coordinator's
  `_with_client` is the single place to change.
- **`authenticate()` fails silently.** pymoof's `authenticate()` returns even
  on a bad key; the first read (`get_battery_level`) is what raises. A wrong key
  therefore currently surfaces as a repeating `UpdateFailed`/`ConfigEntryNotReady`
  retry loop rather than a clean auth error. If you want a reauth flow, raise
  `ConfigEntryAuthFailed` from `_with_client` on the first-read failure.
- **Availability is automatic.** When the bike is out of range, the poll fails
  and all entities go `unavailable` via `CoordinatorEntity`. No extra code.
- **Idempotent setup.** `unique_id` is the MAC. Consider `get_frame_number()`
  (no auth needed) as a stabler unique id, and to validate the connection
  inside the config flow before creating the entry.
