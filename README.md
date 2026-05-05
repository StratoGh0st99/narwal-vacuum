# Narwal Vacuum — Home Assistant Integration

Local, cloud-independent integration for Narwal robot vacuums. Talks
to the robot directly over its WebSocket on TCP/9002 — no Narwal
account, no cloud round-trip, low latency.

This integration is a **community fork** of
[`sjmotew/NarwalIntegration`](https://github.com/sjmotew/NarwalIntegration).
The original work by [@sjmotew](https://github.com/sjmotew) and
[@clawtom](https://github.com/clawtom) — protocol reverse engineering,
map renderer, segment-area mapping, the bulk of the entity model — is
the foundation everything here builds on. This fork adds extra Flow 2
decoders, error / station / multi-map sensors, a finer map render,
and a tooling stack for further protocol work.

## Compatibility

Confirmed working over the local protocol on TCP/9002:

| Model | Status | Notes |
|-------|--------|-------|
| Narwal Flow (AX12) | Working | Inherited from upstream |
| **Narwal Flow 2 (QxMSPG6VSO)** | Working — primary focus | Live protocol RE done here |
| Freo Z10 Ultra (CX4) | Working | Community confirmed upstream |
| Freo X10 Pro (AX15) | Working | Community confirmed upstream |
| Freo X Ultra / X Plus / J-series / Freo Z Ultra | Not compatible | Cloud-only or Tuya-based |

If your model has port 9002 open (`nmap -p 9002 <robot-ip>`) it likely
works — open an issue with model + firmware so we can extend the
protocol mappings.

## What this fork adds on top of upstream

All upstream entities still work the same. Additions are guarded so
non-Flow-2 devices keep their original behaviour.

| Feature | Source field |
|---|---|
| Live cleaning **progress** % during a clean | `working_status.1` (float32) |
| Correct cleaning **area** in m² (no more 1.8 m² constant) | `working_status.2` (float32) |
| Per-room **completion** tracking | `working_status.5[i].4` |
| **Mop-drying timer** (% + remaining time) | `working_status.8 / 9` |
| **Active error** binary sensor with stable code → identifier mapping | `robot_base_status.48.1.*.2` and secondary channel `base.1` |
| **Station activity** sensor: idle / mop_washing / mop_drying / dust_emptying | `WorkingStatus` + `48.1` markers |
| **User-action prompt** sensor + countdown (carry me to dock, refill tank, …) | `base.3.16` + `working_status.22` |
| **Multi-map switch detection** — reloads the map when you change it in the app | `base.30 / base.44` |
| **Mop humidity select** entity (read + write) | `base.29` (read) + existing setter |
| **Live suction read** during cleaning | `base.26` |
| **Dust bag health** % | `base.41` |
| **Freo Mind** start via `vacuum.send_command` | reverse-engineered payload |
| Flow 2 `ROOM_TYPE` overrides (Master Bedroom, Toilet, Storage Room, …) | per-product-key delta |
| **Higher-resolution map** — 6–12× upscale with crisp room blocks + smoothly drawn dock / robot / labels | renderer rewrite |
| WorkingStatus enum: MOP_WASHING (3), MAPPING (7), MOP_DRYING (17), MOP_DRYING_ACTIVE (19) | live capture |

A capture / replay tool for further protocol RE lives in
[`tools/narwal_capture.py`](tools/narwal_capture.py) — see the
[capture guide](tools/CAPTURE_GUIDE.md) for usage.

## Installation

### HACS (custom repository)

1. **HACS** → ⋮ → **Custom repositories**
2. Add `https://github.com/StratoGh0st99/narwal-vacuum` — category
   **Integration**
3. Find **Narwal Vacuum** in HACS, click **Download**
4. **Restart Home Assistant**

### Manual

1. Copy `custom_components/narwal_vacuum/` to your HA
   `config/custom_components/` directory
2. Restart Home Assistant

### Configuration

1. **Settings → Devices & Services → Add Integration** → search
   **Narwal Vacuum**
2. Enter the robot's IP address and pick its model
3. Entities are created automatically

> If you used the upstream `narwal` integration before, this one runs
> alongside it under the new domain `narwal_vacuum`. You'll re-add the
> robot here once; the robot's stored maps / rooms are unaffected.

## Requirements

- Robot reachable on the local network with port 9002 open
- Home Assistant 2025.1.0+ / Python 3.12+
- Robot's mobile app **closed** when HA is connected — only one
  WebSocket session at a time

## Reporting issues

Please use the issue tracker on this repo. Include:

- Model and product key (visible as the device name in HA after setup)
- Firmware version (`sensor.<robot>_firmware_version`)
- Home Assistant version
- A capture from `tools/narwal_capture.py` if the issue is protocol-related

## Disclaimer

Unofficial, community-maintained. Not affiliated with or endorsed by
Narwal. Firmware updates from Narwal can break the local protocol at
any time.

## License

MIT — same as upstream.
