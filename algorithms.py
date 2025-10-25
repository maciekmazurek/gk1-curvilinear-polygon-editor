from PySide6.QtCore import QPointF

import math

def bresenham(x0: int, y0: int, x1: int, y1: int):
    pixels = []
    steep = abs(y1 - y0) > abs(x1 - x0)
    if steep:
        x0, y0 = y0, x0
        x1, y1 = y1, x1
    if x0 > x1:
        x0, x1 = x1, x0
        y0, y1 = y1, y0
    dx = x1 - x0
    dy = abs(y1 - y0)
    err = dx // 2
    ystep = 1 if y0 < y1 else -1
    y = y0
    for x in range(x0, x1 + 1):
        if steep:
            pixels.append((y, x))
        else:
            pixels.append((x, y))
        err -= dy
        if err < 0:
            y += ystep
            err += dx
    return pixels

def distance(p0: QPointF, p1: QPointF) -> float:
    return math.hypot(p1.x() - p0.x(), p1.y() - p0.y())

def bezier(p0: QPointF, p1: QPointF, p2: QPointF, p3: QPointF):
    # Estimate sampling density from control polygon length
    est_len = (distance(p0, p1) + distance(p1, p2) + distance(p2, p3))
    n = max(int(est_len * 1.5), 32)
    n = min(n, 2000)
    dt = 1.0 / n

    # Power basis coefficients (local coords)
    x0, y0 = p0.x(), p0.y()
    x1, y1 = p1.x(), p1.y()
    x2, y2 = p2.x(), p2.y()
    x3, y3 = p3.x(), p3.y()

    ax = -x0 + 3*x1 - 3*x2 + x3
    ay = -y0 + 3*y1 - 3*y2 + y3
    bx = 3*x0 - 6*x1 + 3*x2
    by = 3*y0 - 6*y1 + 3*y2
    cx = -3*x0 + 3*x1
    cy = -3*y0 + 3*y1
    dx = x0
    dy = y0

    dt2 = dt * dt
    dt3 = dt2 * dt

    sx = dx
    sy = dy

    s1x = cx * dt + bx * dt2 + ax * dt3
    s1y = cy * dt + by * dt2 + ay * dt3

    s2x = 2 * bx * dt2 + 6 * ax * dt3
    s2y = 2 * by * dt2 + 6 * ay * dt3

    s3x = 6 * ax * dt3
    s3y = 6 * ay * dt3

    # Collect integer pixel coordinates (absolute in parent local coords)
    pixels = []
    last_px = None
    for i in range(n + 1):
        px = int(round(sx))
        py = int(round(sy))
        if last_px != (px, py):
            pixels.append((px, py))
            last_px = (px, py)
        sx += s1x
        sy += s1y
        s1x += s2x
        s1y += s2y
        s2x += s3x
        s2y += s3y

    return pixels