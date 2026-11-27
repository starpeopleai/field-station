"""Live worldwide launch context from Launch Library 2."""
import fcntl
import json
from pathlib import Path
from urllib.error import HTTPError
import math
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://ll.thespacedevs.com/2.3.0/launches/"
POST_LAUNCH_SECONDS = 2 * 60 * 60
_lock = threading.Lock()
_rows = None
_last_success = 0
_next_check = 0
_complete = False
_cache = Path.home() / "Library/Caches/field-station/launch-schedule.json"


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def distance_miles(center, pad):
    try:
        lat1, lon1, lat2, lon2 = (float(point[key]) for point in (center, pad)
                                  for key in ("latitude", "longitude"))
    except (KeyError, TypeError, ValueError):
        return None
    if not (abs(lat1) <= 90 and abs(lat2) <= 90 and abs(lon1) <= 180 and abs(lon2) <= 180):
        return None
    a, b = math.radians(lat1), math.radians(lat2)
    hav = math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(lon2-lon1)/2)**2
    return round(3958.7613 * 2 * math.asin(math.sqrt(max(0, min(1, hav)))))


def label(rows, now, center=None):
    if rows is None:
        return dict(state="unknown", text="Launch data unavailable")
    today = datetime.fromtimestamp(now).date()
    candidates = []
    for row in rows:
        net = timestamp(row.get("net"))
        precision = (row.get("net_precision") or {}).get("abbrev")
        if net is None or precision not in ("SEC", "MIN", "HR", "AM", "PM", "DAY"):
            continue
        status = (row.get("status") or {}).get("id")
        reported = status in (3, 4, 6, 7, 9)
        precise = precision in ("SEC", "MIN")
        if reported:
            if not precise or not net <= now < net + POST_LAUNCH_SECONDS:
                continue
            minutes = int((now - net) // 60)
            rank, text, state = 0, f"Launch -{minutes//60:02d}:{minutes%60:02d}", "active"
        elif datetime.fromtimestamp(net).date() != today:
            continue
        elif status in (1, 2, 8) and precise and net > now:
            minutes = math.ceil((net - now) / 60)
            rank, text, state = 1, f"Launch in {minutes//60:02d}:{minutes%60:02d}", "scheduled"
        elif status in (1, 2, 8):
            rank, text, state = 2, "Launch time pending", "pending"
        elif status == 5:
            rank, text, state = 3, "Launch on hold", "hold"
        else:
            continue
        pad = row.get("pad") or {}
        country = (pad.get("country") or {}).get("name") or ""
        site = pad.get("location") or {}
        locality = site.get("city") or site.get("locality") or ""
        if country == "New Zealand" and "mahia peninsula" in (site.get("name") or "").lower().replace("ā", "a"):
            locality = "Māhia"
        place = ", ".join(filter(None, (locality, country)))
        candidates.append((rank, net, text, state, country, place, pad))
    if not candidates:
        return dict(state="idle", text="No launch scheduled")
    _, net, text, state, country, place, pad = min(candidates, key=lambda item: (item[0], -item[1] if item[0] == 0 else item[1]))
    return dict(state=state, text=text, country=country, place=place, epoch=net, distance_miles=distance_miles(center, pad))


def _refresh(now):
    global _rows, _last_success
    utc = lambda epoch: datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")
    # Cover the station's whole local day and the next refresh across midnight.
    midnight = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
    params = dict(net__gte=utc(midnight.timestamp() - POST_LAUNCH_SECONDS), net__lte=utc(now + 26*3600),
                  limit=100, include_suborbital="true")
    request = Request(BASE + "?" + urlencode(params), headers={"User-Agent": "StarPeople-FieldStation/1.0"})
    global _complete
    try:
        _cache.parent.mkdir(parents=True, exist_ok=True)
        with _cache.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                cached = json.loads(_cache.read_text())
            except (ValueError, OSError):
                cached = {}
            if not isinstance(cached, dict):
                cached = {}
            if isinstance(cached.get("rows"), list):
                with _lock:
                    _rows = cached["rows"]
                    _last_success = cached.get("observed", 0)
                    _complete = cached.get("complete", False)
            if now < cached.get("retry", 0):
                return
            cached["retry"] = now + 600
            try:
                with urlopen(request, timeout=8) as response:
                    data = json.load(response)
                if isinstance(data.get("results"), list) and not data.get("next"):
                    cached.update(rows=data["results"], observed=now, complete=True)
                    with _lock:
                        _rows, _last_success, _complete = cached["rows"], now, True
            except HTTPError as error:
                delay = error.headers.get("Retry-After", "")
                if delay.isdigit():
                    cached["retry"] = max(cached["retry"], now + int(delay))
            except (OSError, ValueError):
                pass
            tmp = _cache.with_suffix(".tmp")
            tmp.write_text(json.dumps(cached))
            tmp.replace(_cache)
    except (OSError, ValueError, TypeError):
        return


def current(center=None):
    global _next_check
    now = time.time()
    with _lock:
        if now >= _next_check:
            _next_check = now + 60
            threading.Thread(target=_refresh, args=(now,), daemon=True).start()
        age = now - _last_success
        rows = _rows if age < 7200 else None
        complete = _complete
    result = label(rows, now, center)
    if result["state"] == "idle" and (not complete or age >= 1800):
        return label(None, now, center)
    return result
