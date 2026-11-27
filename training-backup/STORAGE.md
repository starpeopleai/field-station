# Dedicated training storage

Training workers accept `storage_volume` and `storage_volume_id`. The configured root must resolve inside the mounted volume, and its `.training-volume` marker must match the configured identity. Missing or substituted disks fail closed before creating output directories.

For the HQ deployment, the intended data roots are:

- `/Volumes/UFO-Training/field`: all model lanes, immutable training snapshots, model runs, comparisons, and research.
- `/Volumes/UFO-Training/review-mirror`: checksum-verified field review snapshots.
- `/Volumes/UFO-Training/hq-review`: offline HQ review database and frame cache.
- `/Volumes/UFO-Thumb/field-station-backup`: separate backup copies of training/models, review snapshots, and anomalous packages.

The field station retains reviewed crops and labels for offline operation. HQ storage is not a live network filesystem dependency of review saves. Recordings and the camera buffer do not belong on the training volume.

Migration must pre-copy while services run, stop HQ writers for the final delta, verify source/destination contents, then update configurations and service wrappers. Historical absolute paths require compatibility symlinks. Retain original copies until service health and the independent backup are verified. Never fall back to an internal disk when an external volume is absent.

Recognition journals are a separate storage consumer. Rollover uses SQLite `VACUUM INTO` to preserve a compact snapshot instead of duplicating the active database's unused pages. The compact partition is synced and published before pruning its rows from the active journal; interrupted rollover recovery remains idempotent.

Large observation payloads use a versioned lossless compressed representation. Review and recovery readers accept both legacy JSON text and compressed payloads. Install compatible readers before enabling compressed writes; do not roll back readers to a version that only understands JSON text.

Interrupted review batches recover their manifest by replaying changed audit receipts against current sample records. Missing or invalid manifests still trigger a full rebuild. This avoids making a routine service restart block new saves behind a scan of every historical sample.
