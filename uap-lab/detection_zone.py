"""Detection-region coordinates are normalized to the original camera frame."""
import math

FULL_FRAME = [0, 0, 1, 1]


def valid(bounds):
    return (isinstance(bounds, list) and len(bounds) == 4
            and all(type(v) in (int, float) and math.isfinite(v) for v in bounds)
            and 0 <= bounds[0] < bounds[2] <= 1
            and 0 <= bounds[1] < bounds[3] <= 1)


def settings(document):
    bounds = document.get('zone_bounds')
    return dict(zone_enabled=document.get('zone_enabled') is True,
                zone_bounds=bounds if valid(bounds) else FULL_FRAME.copy())


def filter_boxes(boxes, shape, bounds):
    height, width = shape[:2]
    left, top, right, bottom = bounds
    return [box for box in boxes
            if left*width <= box[0]+box[2]/2 <= right*width
            and top*height <= box[1]+box[3]/2 <= bottom*height]
