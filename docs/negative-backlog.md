# Bounded machine-negative review sample

The optional sampler retains at most 1,000 unreviewed machine-negative detections
within a 25 GiB event-media budget. The count is independent of the number of
anomalies. These limits apply to this sample, not the whole station disk.

One quarter of slots prioritize uncertainty (capture probability closest to 0.5).
The remaining slots rotate through coarse crop appearance and capture-hour buckets.
No model is trained and no labels are changed by this process. Fresh arrivals have
a 15-minute grace period; active inspection, manual capture, bookmarks, pending
human saves, reviewed events, and archive evidence take priority over the limits.
Protected or fresh items can therefore temporarily exceed the budget.

The worker checks once a minute, processes at most 250 deletions or 60 seconds per
pass, and yields when review writes or media maintenance hold the relevant locks.
Successful passes with excess items remaining resume after five seconds. Current
queue candidates are checked first; an incomplete arrivals index triggers only
100 historical probes per pass, with a persistent cursor covering older records.
The worker uses normal disk scheduling and reduced CPU priority. Retention scans
use a separate lock; actual media mutations retain the shared safety lock.
Protection metadata errors preserve the affected data. An interruption leaves a
durable retry record. Each deletion is audited before media is unlinked.

Only event-owned images and inspection media are removed. Training crops, labels,
manual recordings, archived packages, and shared native segments are not deleted.
Existing reference-aware retention handles shared segments separately.

Install on the field account after deploying the code:

```sh
python3 scripts/install_negative_backlog.py --app /Users/ufo-field/ufo-field --data /Volumes/UFO-Field/uap-lab --enable
```

The LaunchAgent starts after account login, restarts on failure, and refuses to
run without the external field volume. The persistent policy, status, feature
cache, pending deletion records, and audit history live on the external volume
under `uap-lab/negative-backlog-*`. Only startup error logging uses the standard
macOS user log directory; routine service output is discarded. Run `negative_backlog.py --data PATH` without
`--apply` for a non-deleting preview. Set `enabled` to false in the policy to stop
automatic deletion. Existing daytime expiration remains a separate opt-in policy.
