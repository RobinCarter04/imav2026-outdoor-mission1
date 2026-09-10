# Rulebook

Current: **V4 (1 Sep 2026)** — `Rulebook_IMAV2026_V4-1.pdf` (39 pages) with a plain-text extract
`Rulebook_IMAV2026_V4-1.txt` for grepping (`grep -n "5.4.1" Rulebook_IMAV2026_V4-1.txt`).
Source page (check for newer versions before every planning session):
https://2026.imavs.org/competitions-rulebook-imav-2026/

| Version | Date | File | Notes |
|---|---|---|---|
| V4 | 2026-09-01 | `Rulebook_IMAV2026_V4-1.pdf` | **current** — https://2026.imavs.org/wp-content/uploads/2026/09/Rulebook_IMAV2026_V4-1.pdf |
| V3 | 2026-07-22 | — | https://2026.imavs.org/wp-content/uploads/2026/07/Rulebook_IMAV2026_V3.pdf |

Where things are in V4:
| Topic | Section | Page |
|---|---|---|
| General rules (MTOW 5 kg, kill switch, 80 m, autonomy factor, zone breach → land) | §2 | 6–7 |
| Frequency / power limits | §2.1, Tab. 1 | 7 |
| Format: green card, 30-min slot, 10 min prep, mission validated on return | §2.2 | 7 |
| Outdoor site Haguenau, coordinates, site geofence corners, zones on the day | §5.2 | 26–27 |
| Precision landing sizes, ArUco 5x5 80 cm | §5.2.1 | 27–28 |
| Outdoor scoring components | §5.3 | 29 |
| **Mission 1 — Mapping and vehicle identification** | §5.4.1 | 30–33 |
| **Mission 1 scoring formula** | §5.4.2, Tab. 7 | 34 |

**Fig. 19 georeferenced (2026-09-10):** the p. 27 zone map was georeferenced from the four §5.2 geofence
corners (1.45 m/px, north-up, 1 m fit residual) and every zone digitised into `sim/areas/haguenau_fig19.kml`
and `haguenau_fig19_zones.json` (≈ ±10 m). Check image: `fig19_georeferenced_check.jpg` (red = rulebook
fence back-projected, magenta = detected zones, cyan = flight zone, green = Tab. 6 sample vehicles).

When a new version appears: download it, diff §2, §5.2, §5.4.1–5.4.2 against V4, and record any change
in `../WORKING_NOTES.md` and `../REQUIREMENTS.md`. Commit the PDFs (small; the history matters).
