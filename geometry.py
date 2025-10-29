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