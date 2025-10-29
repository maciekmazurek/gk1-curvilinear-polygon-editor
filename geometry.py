import math
from model import EdgeType

def unit(x: float, y: float):
    l = math.hypot(x, y)
    if l < 1e-8:
        return (None, 0.0)
    return ((x / l, y / l), l)

def rot90_ccw(vx: float, vy: float):
    return (-vy, vx)

def rot90_cw(vx, vy):
    return (vy, -vx)

def norm_angle(a: float) -> float:
    # Normalize into [0, 2π)
    while a < 0:
        a += 2 * math.pi
    while a >= 2 * math.pi:
        a -= 2 * math.pi
    return a

def neighbour_tangent(edges, idx: int, current_edge, vertex, at_v1: bool):
    """Compute unit tangent direction at `vertex` using the neighbouring edge.

    - edges: full polygon edge list
    - idx: index of the current arc edge within edges
    - current_edge: the current arc edge (used for chord direction in two-arc G1 case)
    - vertex: the shared endpoint vertex
    - at_v1: True if vertex is v1 of the current edge, False if v2

    Returns a unit vector (ux, uy) or None if not computable.
    """
    n_edges = len(edges)
    e = current_edge

    if at_v1:
        ne = edges[(idx - 1) % n_edges]
        # Special case: vertex adjacent to two arcs with G1 -> use bisector tangent
        if getattr(ne, 'type', None) == EdgeType.ARC and getattr(vertex, 'continuity', None) and getattr(vertex.continuity, 'name', None) == 'G1':
            if ne.v2 is vertex:
                inx, iny = vertex.x - ne.v1.x, vertex.y - ne.v1.y
            else:
                inx, iny = vertex.x - ne.v2.x, vertex.y - ne.v2.y
            outx, outy = e.v2.x - vertex.x, e.v2.y - vertex.y
            u_in, _ = unit(inx, iny)
            u_out, _ = unit(outx, outy)
            if u_in is not None and u_out is not None:
                bx, by = u_in[0] + u_out[0], u_in[1] + u_out[1]
                u_b, _ = unit(bx, by)
                return u_out if u_b is None else u_b
        # Default: direction along neighbour at the shared vertex
        if ne.v2 is vertex:
            vx_, vy_ = vertex.x - ne.v1.x, vertex.y - ne.v1.y
        else:
            vx_, vy_ = ne.v2.x - vertex.x, ne.v2.y - vertex.y
        if getattr(ne, 'type', None) == EdgeType.BEZIER:
            try:
                vx_, vy_ = vertex.x - ne.c2.x, vertex.y - ne.c2.y
            except Exception:
                pass
    else:
        ne = edges[(idx + 1) % n_edges]
        if getattr(ne, 'type', None) == EdgeType.ARC and getattr(vertex, 'continuity', None) and getattr(vertex.continuity, 'name', None) == 'G1':
            inx, iny = vertex.x - e.v1.x, vertex.y - e.v1.y
            if ne.v1 is vertex:
                outx, outy = ne.v2.x - vertex.x, ne.v2.y - vertex.y
            else:
                outx, outy = ne.v1.x - vertex.x, ne.v1.y - vertex.y
            u_in, _ = unit(inx, iny)
            u_out, _ = unit(outx, outy)
            if u_in is not None and u_out is not None:
                bx, by = u_in[0] + u_out[0], u_in[1] + u_out[1]
                u_b, _ = unit(bx, by)
                return u_out if u_b is None else u_b
        if ne.v1 is vertex:
            vx_, vy_ = ne.v2.x - vertex.x, ne.v2.y - vertex.y
        else:
            vx_, vy_ = vertex.x - ne.v1.x, vertex.y - ne.v1.y
        if getattr(ne, 'type', None) == EdgeType.BEZIER:
            try:
                vx_, vy_ = ne.c1.x - vertex.x, ne.c1.y - vertex.y
            except Exception:
                pass

    u_, _ = unit(vx_, vy_)
    return u_

def normalize_vector(vec: tuple[float, float]):
    length = math.hypot(vec[0], vec[1])
    if length < 1e-8:
        return (None, length)
    return ((vec[0] / length, vec[1] / length), length)

def compute_arc_geometry_for_edge(edges, idx: int, arc_edge):
    """Compute arc circle geometry (scene coords) for the given arc edge.

    Returns a tuple: (Cx, Cy, R, a_start, a_end, prefer_ccw)

    - If both endpoints have G0: center = chord midpoint, R = |chord|/2 (semicircle).
    - If exactly one endpoint has G1: compute center as intersection of:
        a) line through G1 endpoint along the normal to the desired tangent,
        b) the perpendicular bisector of the chord v1-v2.
      Orientation (CW/CCW) is chosen to match the tangent at the G1 endpoint.
    - If both endpoints claim G1, only v1's G1 is honored (v2 treated as G0).
    """
    v1 = arc_edge.v1
    v2 = arc_edge.v2
    x1, y1 = v1.x, v1.y
    x2, y2 = v2.x, v2.y

    chord_u, chord_len = unit(x2 - x1, y2 - y1)
    if chord_u is None or chord_len < 1e-6:
        # Degenerate chord: return midpoint circle and zero sweep
        Cx = (x1 + x2) * 0.5
        Cy = (y1 + y2) * 0.5
        R = chord_len * 0.5
        return (Cx, Cy, R, 0.0, 0.0, True)

    # continuity flags (only one end may be G1)
    g1_v1 = getattr(v1, 'continuity', None) and getattr(v1.continuity, 'name', None) == 'G1'
    g1_v2 = getattr(v2, 'continuity', None) and getattr(v2.continuity, 'name', None) == 'G1'
    if g1_v1 and g1_v2:
        g1_v2 = False

    # Base center at chord midpoint and radius as semicircle
    Mx = (x1 + x2) * 0.5
    My = (y1 + y2) * 0.5
    ncx, ncy = rot90_ccw(*chord_u)  # perpendicular to chord
    Cx, Cy = Mx, My
    R = chord_len * 0.5
    prefer_ccw = True

    # If one endpoint requests G1, adjust center to match desired tangent
    if g1_v1 or g1_v2:
        if g1_v1:
            t = neighbour_tangent(edges, idx, arc_edge, v1, True)
            Px, Py = x1, y1
        else:
            t = neighbour_tangent(edges, idx, arc_edge, v2, False)
            Px, Py = x2, y2
        if t is not None:
            ntx, nty = rot90_ccw(*t)  # normal to tangent at P
            mx, my = Mx - Px, My - Py
            det = ntx * (-ncy) - nty * (-ncx)
            if abs(det) > 1e-8:
                s = (mx * (-ncy) - my * (-ncx)) / det
                Cx, Cy = Px + s * ntx, Py + s * nty
                R = math.hypot(Px - Cx, Py - Cy)
                # Orientation: match tangent at the G1 endpoint
                rx, ry = Px - Cx, Py - Cy
                r_u, _ = unit(rx, ry)
                if r_u is not None:
                    t_ccw = rot90_ccw(*r_u)
                    t_cw = rot90_cw(*r_u)
                    dot_ccw = t_ccw[0] * t[0] + t_ccw[1] * t[1]
                    dot_cw = t_cw[0] * t[0] + t_cw[1] * t[1]
                    prefer_ccw = dot_ccw >= dot_cw

    # Angles for v1 -> v2
    a1 = math.atan2(y1 - Cy, x1 - Cx)
    a2 = math.atan2(y2 - Cy, x2 - Cx)
    a1n, a2n = norm_angle(a1), norm_angle(a2)
    if prefer_ccw:
        sweep = a2n - a1n
        if sweep <= 0:
            sweep += 2 * math.pi
    else:
        sweep = a1n - a2n
        if sweep <= 0:
            sweep += 2 * math.pi
        sweep = -sweep
    return (Cx, Cy, R, a1, a1 + sweep, prefer_ccw)