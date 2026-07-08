# VanMoof S3/X3 — Home Assistant integration

[![Validate](https://github.com/BobMcGlobus/ha-vanmoof/actions/workflows/validate.yml/badge.svg)](https://github.com/BobMcGlobus/ha-vanmoof/actions/workflows/validate.yml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![release](https://img.shields.io/github/v/release/BobMcGlobus/ha-vanmoof)](https://github.com/BobMcGlobus/ha-vanmoof/releases)

A **standalone** HACS custom integration for the VanMoof S3/X3, talking to the
bike directly over BLE from Home Assistant — no Pi bridge, no MQTT layer.

It exposes:

- `sensor.*` — battery %, odometer (km, total_increasing), current speed (km/h)
- `lock.*` — the bike's digital lock (lock / unlock; locking connects immediately)
- `binary_sensor.*` — **In range**: passive presence from BLE advertisements
  (any adapter/proxy), so it flips off shortly after the bike leaves range —
  handy for arrival and departure / theft automations, independent of polling.

The **poll interval** is adjustable per bike (integration → *Configure*). A wrong
encryption key triggers a **re-authentication** prompt instead of a silent retry
loop.

Under the hood it wraps a vendored slice of
[`pymoof`](https://github.com/quantsini/pymoof) and uses Home Assistant's own
Bluetooth stack (`bleak-retry-connector`), so the connection is routed
automatically through the **local adapter or any ESPHome Bluetooth proxy** that
can currently reach the bike. Setup can pull the encryption key straight from
your VanMoof account; after that it's fully local.

Translations: English, German, Dutch.

## Supported hardware

- ✅ **VanMoof S3 / X3** — supported and tested on real S3 hardware.
- ❔ **Other bikes:** the S3/X3 BLE protocol (via pymoof) is the only one
  implemented. SX1/SX2 and "Smart" S1/S2 are recognised over the air but *not*
  supported by pymoof; S5 / A5 use a different, unsupported protocol. Adding a
  model means adding a second BLE client — contributions welcome, but there's no
  untested "support" claimed here.

---

## Install

**HACS (custom repository)**
1. HACS → ⋮ → *Custom repositories* → add `https://github.com/BobMcGlobus/ha-vanmoof`, category *Integration*.
2. Install *VanMoof S3/X3*, restart HA.

**Manual**
Copy `custom_components/vanmoof/` into `<config>/custom_components/`, restart HA.

Then: *Settings → Devices & Services → Add Integration → VanMoof*, and pick one
of the two setup paths below.

---

## Setup: getting the encryption key + user key id

The config flow offers two ways. Either way, once set up the integration is
**fully local** — the cloud is only touched (optionally) during setup.

**1. Log in with your VanMoof account (recommended).** Choose *"Log in with my
VanMoof account"*, enter your VanMoof email + password, and pick the bike. The
`encryptionKey` and `userKeyId` are read from your account automatically; you
then pick the bike from the nearby-device list. Credentials are used once and
not stored.

> The bike must be **in Bluetooth range and awake** during setup: the MAC stored
> in your VanMoof account is *not* the address the bike advertises on, so the
> integration connects using the address it actually sees over the air. Easiest
> path for an in-range bike is to let **auto-discovery** find it and pick the
> account login for the key. A bike that's out of range (e.g. in the cellar)
> can't be set up until it's nearby.

**2. Enter the key manually.** Choose *"Enter the encryption key manually"*, pick
the bike from the nearby-device list (or paste its MAC), then enter the
`encryptionKey` (hex → **Encryption key**) and `userKeyId` (int → **User key
id**). Get these however you like — e.g. offline from the bike.

**Caveat (post-bankruptcy):** VanMoof's servers changed hands (Lavoie), so the
account login may be flaky or gone. If it fails, use manual entry with keys
extracted offline via [`chwdt/vanmoof-tools`](https://github.com/chwdt/vanmoof-tools)
(dumps the keys stored on the bike over BLE).

---

## Status & known rough edges

Verified on real S3 hardware: account login, auto-discovery, connect →
authenticate → read, and the battery / odometer / speed sensors + lock entity.

Known rough edges:

- **Wrong key** currently surfaces as a repeating `ConfigEntryNotReady` /
  `UpdateFailed` retry loop rather than a clean auth error, because
  `authenticate()` returns silently and only the first read raises. A
  `ConfigEntryAuthFailed`-based reauth flow is the planned fix.
- **The bike must be in range and awake during setup** — the MAC in your VanMoof
  account is *not* the BLE address it advertises on, so the integration uses the
  address it actually sees over the air.
- **No brand icon yet** — the logo/icon lives in `home-assistant/brands`; see
  [`brands/README.md`](brands/README.md) for the one-time submission.

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
- **`pymoof` is vendored, not a requirement.** The published `pymoof` pins
  `bleak<0.15` and `cryptography<37`, which conflict with Home Assistant's own
  (much newer) versions — installing it makes HA's requirement step fail (a
  *"config flow could not be loaded: 500"*). So the small runtime slice of
  pymoof (SX3 client, GATT profile, BLE helpers) lives under
  `pymoof_vendor/` (MIT, upstream quantsini/pymoof) and uses HA's own `bleak`
  and `cryptography`. Nothing is pip-installed. To refresh it, re-copy those
  files from upstream and re-point the two package-internal imports.
- **Availability is automatic.** When the bike is out of range, the poll fails
  and all entities go `unavailable` via `CoordinatorEntity`. No extra code.
- **Idempotent setup.** `unique_id` is the MAC. Consider `get_frame_number()`
  (no auth needed) as a stabler unique id, and to validate the connection
  inside the config flow before creating the entry.
