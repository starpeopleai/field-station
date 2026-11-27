# Air traffic context

The private camera feed shows a north-up ADS-B aircraft plot. Arrows indicate reported **ground track**, not the aircraft's nose orientation. Missing track data renders as a dot. Hover or tap for callsign, aircraft type, pressure altitude in feet, speed in knots, and track.

Settings → Radar center address defaults to the Stanford Dish (37.4083, -122.179). This is an operator-selected radar reference, not the automatic county-only station location. Address resolution uses OpenStreetMap Nominatim only on explicit Save; no autocomplete. The entered address and resolved point stay in the private station settings. The geocoder receives the entered address; the traffic provider receives the configured query point. Settings also exposes a radar radius from 1–100 statute miles, defaulting to 15. The radar queries a 15 statute-mile radius by default (13.03 nautical miles); provider requests round up to 14 nautical miles and reports are filtered to the exact configured radius.

The collector polls https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{distance} every 15 seconds, with exponential error backoff, Retry-After handling, and an hour pause for rejected configuration/authentication. See https://github.com/adsbfi/opendata for provider terms and limits. Data is attributed to adsb.fi and is for private, non-commercial analysis. This private feed is not added to Internet Archive or public snapshots. Nominatim policy: https://operations.osmfoundation.org/policies/nominatim/.

Aircraft positions older than 30 seconds and known ground traffic are excluded. Feed timestamps are validated. Stale/unavailable data is explicitly shown and does not leave stale arrows on screen. Zero reports is not evidence that the airspace is empty: coverage depends on transponders and receiving stations. No automatic classification or training-label changes are made.

On detection creation, a bounded local database read records the latest preceding traffic sample within 30 seconds in `air-traffic.private.json`, next to that detection's event file. Review video → Air traffic at detection time shows that retained context. Historical detections without contemporaneous samples remain unavailable; current traffic is never substituted. This is regional context, not a geometrical match to the camera's field of view.

Storage is `<field-working-volume>/air-traffic`: private settings, current status, and compressed SQLite history, limited to 72 hours and 64 MiB of compressed payload (SQLite has additional overhead and reuses pages). Retained per-detection context is independent of the rolling history. Collection never participates in capture/video locks, and network calls never occur inside detection creation or review reads.

Install persistently with the station Python:

```
python scripts/install_air_traffic.py --root /Volumes/UFO-Field-Working-Files
```

Changes to `recognition_alerts.py` require reloading the recognition worker; the camera/recording worker need not restart. All new API routes require the private station token; public snapshot UI does not load the module.

## Public Archive evidence

A separate ADSB.lol collector requests openly licensed aircraft reports every 180 seconds (480 requests/day, below its anonymous 500/day allowance). Requests are budgeted across restarts and back off on errors. See https://www.adsb.lol/docs/open-data/api. Both history databases have independent 72-hour/64-MiB payload limits.

Automatic and manual Internet Archive bundles include `air-traffic.json`, with ODbL 1.0 attribution and license, timestamped aircraft reports, the recording time window, and gaps in available context. Public samples are retained at detection creation in `air-traffic-public.json`; a preceding sample must be within 210 seconds. Reports are not extrapolated or presented as a visual-object identification. The public file excludes the configured radar address and center; aircraft coordinates remain part of the evidence. Private adsb.fi reports are never exported.

The Archive planner includes this file in its checksummed inventory and rebuilds that inventory when aircraft evidence changes. Previously collected public samples survive rolling-history expiry. Historical recordings without contemporaneous aircraft data explicitly report unavailable; today's aircraft are never substituted. Manual recordings reviewed after history expiry can lack context if no bundle was prepared while history was retained.

Reload the capture/publisher and recognition services after installing the integration. The collector starts at login and restarts automatically.
