from model import Arc, EdgeType, Vertex
from graphics.edge_item import EdgeItem
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainterPath,
    QPen,
    QImage,
    QPixmap,
    QPainter
)
from PySide6.QtCore import QPointF, QRectF, Qt

import math

class ArcEdgeItem(EdgeItem):
    """
    Renders an arc edge defined by endpoints v1, v2.
    Geometry rules:
    - If both endpoints have G0: center = midpoint(v1,v2), radius = |v2-v1|/2 (semicircle).
      We draw the CCW semicircle by default.
    - If exactly one endpoint has G1: we compute a circle center C as the
      intersection of:
        a) the line through the G1 endpoint along the normal to the desired tangent, and
        b) the perpendicular bisector of the chord v1-v2.
      Orientation (CW/CCW) is picked so that the tangent at the G1 endpoint
      matches the desired unit tangent direction.
    - If both endpoints claim G1, we honor only v1's G1 (v2 treated as G0).
    """

    def __init__(self, edge: Arc, parent):
        if edge.type != EdgeType.ARC:
            pass  # could raise
        super().__init__(edge, parent)
        self._pixels = []
        self._pixmap = None
        self._pixmap_offset = QPointF(0, 0)
        self._cached_bounding = QRectF(0, 0, 0, 0)

        # path cache used for hit-testing/selection
        self._path_cache = None

        self.update_edge()

    def contextMenuEvent(self, event):
        # Only conversion back to Line is offered for Arc edges
        menu = QMenu()
        to_line_action = menu.addAction("Convert to Line")
        sp = event.screenPos()
        try:
            qp = sp.toPoint()
        except Exception:
            qp = sp
        chosen = menu.exec(qp)
        if chosen == to_line_action:
            parent = self.parentItem()
            if parent:
                parent.convert_edge_to_line(self.edge)
        event.accept()

    def convert_coords_to_parent(self):
        p0 = self.mapFromScene(QPointF(self.edge.v1.x, self.edge.v1.y))
        p3 = self.mapFromScene(QPointF(self.edge.v2.x, self.edge.v2.y))
        return (p0, p3)

    # --- geometry helpers (scene-coords) ---
    def _unit(self, x, y):
        l = math.hypot(x, y)
        if l < 1e-8:
            return (None, 0.0)
        return ((x / l, y / l), l)

    def _rotate90_ccw(self, vx, vy):
        return (-vy, vx)

    def _rotate90_cw(self, vx, vy):
        return (vy, -vx)

    def _neighbour_edges(self):
        parent = self.parentItem()
        if not parent or not hasattr(parent, 'polygon'):
            return (None, None, None, None)
        edges = parent.polygon.edges
        try:
            idx = edges.index(self.edge)
        except ValueError:
            return (None, None, None, None)
        n = len(edges)
        prev_edge = edges[(idx - 1) % n]
        # For the arc's v2, the neighbour is the edge AFTER this arc,
        # not the arc itself. Use idx+1 as the 'next' neighbour.
        next_edge = edges[(idx + 1) % n]
        return (prev_edge, (idx - 1) % n, next_edge, (idx + 1) % n)

    def _tangent_at_vertex_from_neighbour(self, vertex: Vertex, at_v1: bool):
        prev_edge, _, next_edge, _ = self._neighbour_edges()
        if prev_edge is None or next_edge is None:
            return None
        # For v1, neighbour is prev_edge (ending at v1). For v2, neighbour is next_edge (starting at v2)
        if at_v1:
            e = prev_edge
            # Special case: vertex is adjacent to two arcs and asks for G1 -> use bisector tangent
            if getattr(e, 'type', None) == EdgeType.ARC and getattr(self.edge.v1, 'continuity', None) and self.edge.v1.continuity.name == 'G1':
                # incoming along prev arc chord into vertex
                if e.v2 is vertex:
                    inx = vertex.x - e.v1.x; iny = vertex.y - e.v1.y
                else:
                    inx = vertex.x - e.v2.x; iny = vertex.y - e.v2.y
                # outgoing along this arc chord from vertex to v2
                outx = self.edge.v2.x - vertex.x; outy = self.edge.v2.y - vertex.y
                u_in, _ = self._unit(inx, iny)
                u_out, _ = self._unit(outx, outy)
                if u_in is not None and u_out is not None:
                    bx = u_in[0] + u_out[0]; by = u_in[1] + u_out[1]
                    u_b, _ = self._unit(bx, by)
                    if u_b is None:
                        return u_out
                    return u_b
            if e.v1 is vertex and e.v2 is vertex:
                return None
            if e.v2 is vertex:
                # direction entering the vertex along polygon
                vx = vertex.x - e.v1.x
                vy = vertex.y - e.v1.y
            else:
                # e.v1 is vertex -> direction leaving vertex
                vx = e.v2.x - vertex.x
                vy = e.v2.y - vertex.y
            if getattr(e, 'type', None) == EdgeType.BEZIER:
                # if bezier and ends at v1, tangent is v1 - c2
                try:
                    vx = vertex.x - e.c2.x
                    vy = vertex.y - e.c2.y
                except Exception:
                    pass
        else:
            e = next_edge
            # Special case: vertex is adjacent to two arcs and asks for G1 -> use bisector tangent
            if getattr(e, 'type', None) == EdgeType.ARC and getattr(self.edge.v2, 'continuity', None) and self.edge.v2.continuity.name == 'G1':
                # incoming along this arc chord into vertex (from v1)
                inx = vertex.x - self.edge.v1.x; iny = vertex.y - self.edge.v1.y
                # outgoing along next arc chord from vertex
                if e.v1 is vertex:
                    outx = e.v2.x - vertex.x; outy = e.v2.y - vertex.y
                else:
                    outx = e.v1.x - vertex.x; outy = e.v1.y - vertex.y
                u_in, _ = self._unit(inx, iny)
                u_out, _ = self._unit(outx, outy)
                if u_in is not None and u_out is not None:
                    bx = u_in[0] + u_out[0]; by = u_in[1] + u_out[1]
                    u_b, _ = self._unit(bx, by)
                    if u_b is None:
                        return u_out
                    return u_b
            if e.v1 is vertex:
                vx = e.v2.x - vertex.x
                vy = e.v2.y - vertex.y
            else:
                vx = vertex.x - e.v1.x
                vy = vertex.y - e.v1.y
            if getattr(e, 'type', None) == EdgeType.BEZIER:
                try:
                    vx = e.c1.x - vertex.x
                    vy = e.c1.y - vertex.y
                except Exception:
                    pass
        u, _ = self._unit(vx, vy)
        return u

    def _compute_arc_geometry_scene(self):
        v1 = self.edge.v1
        v2 = self.edge.v2
        x1, y1 = v1.x, v1.y
        x2, y2 = v2.x, v2.y
        chord_u, chord_len = self._unit(x2 - x1, y2 - y1)
        if chord_u is None or chord_len < 1e-6:
            # degenerate
            Cx = (x1 + x2) * 0.5
            Cy = (y1 + y2) * 0.5
            R = chord_len * 0.5
            return (Cx, Cy, R, 0.0, 0.0, True)

        # continuity flags
        g1_v1 = getattr(v1, 'continuity', None) and v1.continuity.name == 'G1'
        g1_v2 = getattr(v2, 'continuity', None) and v2.continuity.name == 'G1'
        # only one end may be G1
        if g1_v1 and g1_v2:
            g1_v2 = False

        Mx = (x1 + x2) * 0.5
        My = (y1 + y2) * 0.5
        ncx, ncy = self._rotate90_ccw(*chord_u)  # perpendicular to chord

        # Default: semicircle with center at midpoint
        Cx, Cy = Mx, My
        R = chord_len * 0.5
        prefer_ccw = True

        if g1_v1 or g1_v2:
            # pick the endpoint with G1 and get its desired tangent
            if g1_v1:
                t = self._tangent_at_vertex_from_neighbour(v1, at_v1=True)
                P = (x1, y1)
                at_v1 = True
            else:
                t = self._tangent_at_vertex_from_neighbour(v2, at_v1=False)
                P = (x2, y2)
                at_v1 = False
            if t is not None:
                ntx, nty = self._rotate90_ccw(*t)  # normal to tangent, through P
                # Solve intersection of lines: P + s*n_t  and  M + u*n_c
                # [ntx, -ncx][s] = M-P
                # [nty, -ncy][u]
                mx = Mx - P[0]
                my = My - P[1]
                det = ntx * (-ncy) - nty * (-ncx)  # = -(nt cross nc)
                if abs(det) > 1e-8:
                    s = (mx * (-ncy) - my * (-ncx)) / det
                    Cx = P[0] + s * ntx
                    Cy = P[1] + s * nty
                    R = math.hypot(P[0] - Cx, P[1] - Cy)
                    # orientation: match tangent at the G1 end
                    rx = P[0] - Cx
                    ry = P[1] - Cy
                    r_u, _ = self._unit(rx, ry)
                    if r_u is not None:
                        t_ccw = self._rotate90_ccw(*r_u)
                        t_cw = self._rotate90_cw(*r_u)
                        dot_ccw = t_ccw[0] * t[0] + t_ccw[1] * t[1]
                        dot_cw = t_cw[0] * t[0] + t_cw[1] * t[1]
                        prefer_ccw = dot_ccw >= dot_cw
                # else keep default midpoint semicircle

        # angles for v1->v2
        a1 = math.atan2(y1 - Cy, x1 - Cx)
        a2 = math.atan2(y2 - Cy, x2 - Cx)
        # choose sweep according to prefer_ccw; normalize to [0, 2pi)
        def norm(a):
            while a < 0:
                a += 2 * math.pi
            while a >= 2 * math.pi:
                a -= 2 * math.pi
            return a
        a1n = norm(a1)
        a2n = norm(a2)
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

    def update_edge(self):
        # scene geometry
        Cx, Cy, R, a_start, a_end, prefer_ccw = self._compute_arc_geometry_scene()

        # convert to parent-local for rasterization
        C_local = self.mapFromScene(QPointF(Cx, Cy))
        # sample points
        total_angle = abs(a_end - a_start)
        if total_angle < 1e-6 or R < 1e-6:
            # nothing to draw; keep tiny bbox around chord
            p0, p3 = self.convert_coords_to_parent()
            path = QPainterPath()
            path.moveTo(p0)
            path.lineTo(p3)
            control_rect = path.boundingRect().adjusted(-2, -2, 2, 2)
            self.prepareGeometryChange()
            self._pixels = []
            self._pixmap = None
            self._pixmap_offset = QPointF(0, 0)
            self._cached_bounding = control_rect
            self._path_cache = path
            return

        # choose sampling density
        n = max(int(R * total_angle * 1.5), 32)
        n = min(n, 2000)
        dt = total_angle / n
        sign = 1.0 if (a_end - a_start) >= 0 else -1.0

        # generate points in parent-local coords
        points = []
        minx = miny = 1e18
        maxx = maxy = -1e18
        for i in range(n + 1):
            a = a_start + sign * dt * i
            sx = Cx + R * math.cos(a)
            sy = Cy + R * math.sin(a)
            p = self.mapFromScene(QPointF(sx, sy))
            px = int(round(p.x()))
            py = int(round(p.y()))
            points.append((px, py))
            if px < minx: minx = px
            if py < miny: miny = py
            if px > maxx: maxx = px
            if py > maxy: maxy = py

        width = max(0, maxx - minx + 1)
        height = max(0, maxy - miny + 1)
        control_path = QPainterPath()
        p0, p3 = self.convert_coords_to_parent()
        control_path.moveTo(p0)
        control_path.lineTo(p3)
        control_rect = control_path.boundingRect().adjusted(-2, -2, 2, 2)

        if width == 0 or height == 0 or width * height > 5_000_000:
            new_bounding = control_rect
            self.prepareGeometryChange()
            self._pixels = []
            self._pixmap = None
            self._pixmap_offset = QPointF(0, 0)
            self._cached_bounding = new_bounding
            self._path_cache = control_path
            return

        new_bounding = control_rect.united(QRectF(minx, miny, width, height))
        self.prepareGeometryChange()

        img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        qp = QPainter(img)
        try:
            qp.setPen(Qt.NoPen)
            qp.setBrush(QBrush(QColor("black")))
            for (px, py) in points:
                rx = px - minx
                ry = py - miny
                if 0 <= rx < width and 0 <= ry < height:
                    qp.drawRect(rx, ry, 1, 1)
        finally:
            qp.end()

        self._pixmap = QPixmap.fromImage(img)
        self._pixmap_offset = QPointF(minx, miny)
        self._cached_bounding = new_bounding
        # path used for selection/hit-testing: approximate polyline
        path = QPainterPath()
        if points:
            path.moveTo(points[0][0], points[0][1])
            for (px, py) in points[1:]:
                path.lineTo(px, py)
        self._path_cache = path

    def boundingRect(self):
        return self._cached_bounding

    def paint(self, painter, option, widget):
        # optional: draw chord (dashed) for helping
        painter.setPen(QPen(QColor("gray"), 1, Qt.DashLine))
        p0, p3 = self.convert_coords_to_parent()
        painter.drawLine(p0, p3)
        # draw arc
        if self._pixmap:
            painter.drawPixmap(self._pixmap_offset, self._pixmap)

    def shape(self):
        # return cached path if available
        if getattr(self, "_path_cache", None) is not None:
            return self._path_cache
        # fallback: chord
        p0, p3 = self.convert_coords_to_parent()
        path = QPainterPath()
        path.moveTo(p0)
        path.lineTo(p3)
        return path
