"""Causal image-plane extrapolation relative to lights still observed in the frame."""
from collections import deque
from math import hypot
from statistics import median

WINDOW = 4.5
HORIZON = 8.0


def predict(rows):
    histories = []
    result = []
    for t, points in rows:
        if not histories:
            histories = [deque() for _ in points]
        estimates = []
        for i, point in enumerate(points):
            history = histories[i]
            if point is not None:
                if history and t-history[-1][0] > .3:
                    history.clear()
                history.append((t, points))
                while t-history[0][0] > WINDOW:
                    history.popleft()
                estimates.append(None)
                continue
            estimates.append(extrapolate(history, t, points, i))
        result.append(estimates)
    return result


def extrapolate(history, now, points, target):
    if len(history) < 5 or now-history[-1][0] > HORIZON:
        return None
    candidates = []
    for j, reference in enumerate(points):
        if reference is None:
            continue
        samples = [(t, ps[target][0]-ps[j][0], ps[target][1]-ps[j][1])
                   for t, ps in history if ps[j] is not None]
        if len(samples) < 5:
            continue
        start, end = samples[0][0], samples[-1][0]
        if end-start < .7 or now-end > min(HORIZON, 2*(end-start)):
            continue
        mt, mx, my = [sum(values)/len(samples) for values in zip(*samples)]
        var = sum((t-mt)**2 for t,x,y in samples)
        vx = sum((t-mt)*(x-mx) for t,x,y in samples)/var
        vy = sum((t-mt)*(y-my) for t,x,y in samples)/var
        if median(hypot(x-mx-vx*(t-mt), y-my-vy*(t-mt)) for t,x,y in samples) > 3:
            continue
        candidates.append((reference[0]+mx+vx*(now-mt), reference[1]+my+vy*(now-mt)))
    if candidates:
        return [round(median(axis), 1) for axis in zip(*candidates)]
    return None
