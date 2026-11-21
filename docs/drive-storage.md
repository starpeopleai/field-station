# Drive storage metrics

The private Metrics page lists mounted external drives on Field and HQ, with capacity, used/free bytes, and a usage bar. Sizes use decimal GB/TB. Internal/system volumes are excluded. The Used and Capacity table headers show totals across Field and HQ. APFS volumes sharing a container count once toward totals, using container capacity and usage. Stale-machine values remain explicitly marked last known.

`drive_storage.py` collects filesystem capacity using a bounded `df -kP` call, never recursive scans. The field API uses a background refresh and a 30-second cache. The page polls every 15 seconds without discarding existing rows during loading/errors. `/api/drive-storage` requires the private station token; public read-only pages do not load this section.

HQ publishes `storage-status/hq.json` on the field working volume every minute. Reports older than three minutes are labeled stale; last-known values remain visible. Operational installation: HQ `~/storage-monitor/publish.py`, supervised by `ai.starpeople.storage-report` at login and every 60 seconds. Its output and logs live on UFO-Working-Files. Network failure does not block the Metrics API.

The HQ LaunchAgent must use `~/ufo-processing/recognition-venv/bin/python`, the existing background runtime with removable-volume access. Apple system Python cannot access the external report/log directory in this session. Launchd stdout/stderr use `/dev/null`; the running process opens bounded rotating logs on UFO-Working-Files. Failed transfers retry up to three times with delays of 5 and 10 seconds; the scheduled job retries every minute thereafter.
