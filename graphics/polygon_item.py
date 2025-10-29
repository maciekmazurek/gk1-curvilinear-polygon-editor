from model import *
from graphics.vertex_item import VertexItem
from graphics.line_edge_item import StandardLineEdgeItem, BresenhamLineEdgeItem
from graphics.bezier_edge_item import BezierEdgeItem
from graphics.arc_edge_item import ArcEdgeItem
from PySide6.QtWidgets import QGraphicsItem, QMessageBox
from PySide6.QtGui import (
    QColor,
    QPainterPath,
    QPen,
)
from PySide6.QtCore import QPointF, QRectF, Qt
from geometry import *

import math

class PolygonItem(QGraphicsItem):
    def __init__(self, polygon: Polygon):
        super().__init__()
        self.polygon = polygon
        # last warning text to optionally surface to UI caller
        self.last_continuity_warning: str | None = None
        # We disable QGraphics Framework's built-in moving mechanism
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        # Default line drawing mode
        self._line_drawing_mode = LineDrawingMode.QGRAPHICS

        # Flag indicating whether the position of vertices is being currently 
        # updated by the parent (i.e. this class)
        self.updating_from_parent = False

        # Properties used for implementing polygon dragging
        self._dragging = False
        self._drag_start_scene = None
        self._original_vertices_positions = None
        self._original_control_positions = None

        self.vertex_items = {}
        self.edge_items = []

        self._setup_childitems()
        self._enforce_all_constraints_and_continuity()

    def boundingRect(self):
        # Build union of:
        #  - vertex bounding box
        #  - bounding rects of all child edge items
        rects = []

        if self.polygon.vertices:
            minx = min(v.x for v in self.polygon.vertices)
            miny = min(v.y for v in self.polygon.vertices)
            maxx = max(v.x for v in self.polygon.vertices)
            maxy = max(v.y for v in self.polygon.vertices)
            top_left = self.mapFromScene(QPointF(minx, miny))
            bottom_right = self.mapFromScene(QPointF(maxx, maxy))
            rects.append(QRectF(top_left, bottom_right).normalized())

        # include child edge items' bounding rects
        for e_item in self.edge_items:
            try:
                r = e_item.boundingRect()
            except Exception:
                r = QRectF(0, 0, 0, 0)
            if not r.isNull():
                rects.append(r)

        if not rects:
            return QRectF(0, 0, 0, 0)

        # union all rects
        united = rects[0]
        for r in rects[1:]:
            united = united.united(r)
        # add a small margin so handles/pen fit
        return united.adjusted(-4, -4, 4, 4)

    def shape(self):
        path = QPainterPath()
        edges = self.polygon.edges
        if not edges:
            return path

        # Small helper local to mapping into parent coordinates
        def to_parent(x: float, y: float) -> QPointF:
            return self.mapFromScene(QPointF(x, y))

        # Start path at first edge's v1
        start = to_parent(edges[0].v1.x, edges[0].v1.y)
        path.moveTo(start)

        for idx, e in enumerate(edges):
            etype = getattr(e, "type", None)

            if etype == EdgeType.LINE:
                path.lineTo(to_parent(e.v2.x, e.v2.y))
                continue

            if etype == EdgeType.BEZIER:
                # Use cubicTo for shape-based hit testing
                c1 = to_parent(e.c1.x, e.c1.y)
                c2 = to_parent(e.c2.x, e.c2.y)
                p3 = to_parent(e.v2.x, e.v2.y)
                path.cubicTo(c1, c2, p3)
                continue

            if etype == EdgeType.ARC:
                # Approximate arc with polyline consistent with ArcEdgeItem
                v1, v2 = e.v1, e.v2
                x1, y1 = v1.x, v1.y
                x2, y2 = v2.x, v2.y

                chord_u, chord_len = unit(x2 - x1, y2 - y1)
                if chord_u is None or chord_len < 1e-6:
                    # Degenerate: draw the chord
                    path.lineTo(to_parent(e.v2.x, e.v2.y))
                    continue

                # Continuity flags: only one end of a given arc may be G1
                g1_v1 = getattr(v1, 'continuity', None) and v1.continuity.name == 'G1'
                g1_v2 = getattr(v2, 'continuity', None) and v2.continuity.name == 'G1'
                if g1_v1 and g1_v2:
                    g1_v2 = False

                # Base circle via chord mid-point and normal
                Mx, My = (x1 + x2) * 0.5, (y1 + y2) * 0.5
                ncx, ncy = rot90_ccw(*chord_u)
                Cx, Cy = Mx, My
                R = chord_len * 0.5
                prefer_ccw = True

                # If G1 at one endpoint, adjust center to match desired tangent
                if g1_v1 or g1_v2:
                    if g1_v1:
                        t = neighbour_tangent(edges, idx, e, v1, True); Px, Py = x1, y1
                    else:
                        t = neighbour_tangent(edges, idx, e, v2, False); Px, Py = x2, y2
                    if t is not None:
                        ntx, nty = rot90_ccw(*t)
                        mx, my = Mx - Px, My - Py
                        det = ntx * (-ncy) - nty * (-ncx)
                        if abs(det) > 1e-8:
                            s = (mx * (-ncy) - my * (-ncx)) / det
                            Cx, Cy = Px + s * ntx, Py + s * nty
                            R = math.hypot(Px - Cx, Py - Cy)
                            # Choose orientation so arc tangent matches desired t at endpoint
                            rx, ry = Px - Cx, Py - Cy
                            r_u, _ = unit(rx, ry)
                            if r_u is not None:
                                tx_ccw_x, tx_ccw_y = rot90_ccw(*r_u)
                                tx_cw_x, tx_cw_y = (r_u[1], -r_u[0])
                                dot_ccw = tx_ccw_x * t[0] + tx_ccw_y * t[1]
                                dot_cw = tx_cw_x * t[0] + tx_cw_y * t[1]
                                prefer_ccw = dot_ccw >= dot_cw

                a1 = math.atan2(y1 - Cy, x1 - Cx)
                a2 = math.atan2(y2 - Cy, x2 - Cx)
                a1n, a2n = norm_angle(a1), norm_angle(a2)

                if prefer_ccw:
                    sweep = a2n - a1n
                    if sweep <= 0:
                        sweep += 2 * math.pi
                    sign = 1.0
                else:
                    sweep = a1n - a2n
                    if sweep <= 0:
                        sweep += 2 * math.pi
                    sweep = -sweep
                    sign = -1.0

                total_angle = abs(sweep)
                samples = max(int(R * total_angle * 1.5), 24)
                samples = min(samples, 1024)
                dt = total_angle / samples if samples > 0 else total_angle

                for i in range(1, samples + 1):
                    a = a1 + sign * dt * i
                    sx = Cx + R * math.cos(a)
                    sy = Cy + R * math.sin(a)
                    path.lineTo(to_parent(sx, sy))
                continue

            # Fallback for unknown type: draw straight line to v2
            path.lineTo(to_parent(e.v2.x, e.v2.y))

        return path
    
    def paint(self, painter, option, widget):
        # Do not draw polygon edges here — EdgeItem children are responsible
        # for drawing their own representation (line / bresenham / bezier).
        # Optionally draw selection outline when selected:
        if self.isSelected():
            painter.setPen(QPen(QColor("blue"), 1, Qt.DashLine))
            painter.drawPath(self.shape())

    def _setup_childitems(self):
        # Ensure the polygon.edges_dict matches the current edges list so
        # other code that relies on it (e.g. constraint propagation) can
        # look up edges by endpoint pairs.
        self._sync_edges_dict()

        self.updating_from_parent = True
        try:
            # Setting up VertexItems
            for v in self.polygon.vertices:
                v_item = VertexItem(v, parent=self)
                # We convert vertex position from scene coordinates to parent 
                # coordinates
                vertex_parent_coords = self.mapFromScene(QPointF(v.x, v.y))
                # "updating_from_parent" flag prevents from calling 
                # parent.on_vertex_moved by children vertices (which whould
                # cause the infinite loop) after the following setPos 
                # method call
                v_item.setPos(vertex_parent_coords)
                self.vertex_items[v] = v_item
        finally:
            self.updating_from_parent = False

        # Setting up EdgeItems
        for e in self.polygon.edges:
            e_item = self.EdgeItemFactory(e, parent=self)
            self.edge_items.append(e_item)
            e_item.update_edge()

    def _rebuild_childitems(self):
        # Remove all childitems
        for child in list(self.childItems()):
            child.setParentItem(None)
            sc = self.scene()
            if sc:
                sc.removeItem(child)
        self.vertex_items.clear()
        self.edge_items.clear()

        # Rebuild
        self._setup_childitems()
        self.update()

    # convert_edge helper method
    def _replace_edge_at_index(self, idx: int, new_edge: Edge):
        self.polygon.edges[idx] = new_edge
        # reset constraints on non-line edges
        if getattr(new_edge, 'type', None) != EdgeType.LINE:
            new_edge.constraint_type = ConstraintType.NONE
            new_edge.constraint_value = None
        # sync edge dict and rebuild items
        self._sync_edges_dict()
        self._rebuild_childitems()

    def convert_edge(self, edge: Edge, new_type: EdgeType):
        idx = self.polygon.edges.index(edge)
        v1, v2 = edge.v1, edge.v2
        if new_type == EdgeType.LINE:
            new_edge = Edge(v1, v2)
            self._replace_edge_at_index(idx, new_edge)
        elif new_type == EdgeType.BEZIER:
            # initialize control points along the chord at 1/3 and 2/3 positions
            dx = v2.x - v1.x
            dy = v2.y - v1.y
            c1 = Vertex(v1.x + dx / 3.0, v1.y + dy / 3.0)
            c2 = Vertex(v2.x - dx / 3.0, v2.y - dy / 3.0)
            new_edge = Bezier(v1, v2, c1, c2)
            self._replace_edge_at_index(idx, new_edge)
            # Try to enforce C1 at both endpoints; if disallowed due to Arc adjacency, fall back to G1
            for v in (v1, v2):
                if not self.apply_continuity_to_vertex(v, ContinuityType.C1):
                    self.apply_continuity_to_vertex(v, ContinuityType.G1)
        elif new_type == EdgeType.ARC:
            new_edge = Arc(v1, v2)
            self._replace_edge_at_index(idx, new_edge)
            # For arcs: enforce G0 at both endpoints
            v1.continuity = ContinuityType.G0
            v2.continuity = ContinuityType.G0
            # refresh visuals after continuity change
            self.edge_items[idx].update_edge()
            self.update()

    def _sync_edges_dict(self):
        # Recreate mapping from (v1, v2) -> Edge for current polygon.edges
        d = {}
        for e in self.polygon.edges:
            try:
                # store both orientations to make lookups robust regardless
                # of which vertex is passed first during propagation
                d[(e.v1, e.v2)] = e
                d[(e.v2, e.v1)] = e
            except Exception:
                # guard: skip malformed edges
                continue
        self.polygon.edges_dict = d

    def _edge_between(self, a: Vertex, b: Vertex) -> Edge | None:
        return self.polygon.edges_dict.get((a, b)) or self.polygon.edges_dict.get((b, a))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start_scene = event.scenePos()
            # We save original positions of vertices and control points
            self._original_vertices_positions = [(v, v.x, v.y) for v in self.polygon.vertices]
            self._original_control_positions = [(e, e.c1.x, e.c1.y, e.c2.x, e.c2.y) for e in self.polygon.edges if e.type == EdgeType.BEZIER]
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.scenePos() - self._drag_start_scene
            dx, dy = delta.x(), delta.y()

            # We update original positions of vertices and control points
            for v, ox, oy in self._original_vertices_positions:
                v.x = ox + dx
                v.y = oy + dy
            for e, c1x, c1y, c2x, c2y in self._original_control_positions:
                e.c1.x = c1x + dx
                e.c1.y = c1y + dy
                e.c2.x = c2x + dx
                e.c2.y = c2y + dy

            self.updating_from_parent = True
            try:
                for v, v_item in self.vertex_items.items():
                    # We convert new vertex position from scene coordinates to 
                    # parent coordinates
                    vertex_new_parent_coords = self.mapFromScene(QPointF(v.x, v.y))
                    # "updating_from_parent" flag prevents from calling 
                    # parent.on_vertex_moved by children vertices (which whould
                    # cause the infinite loop) after the following setPos 
                    # method call
                    v_item.setPos(vertex_new_parent_coords)
                for e_item in self.edge_items:
                    e_item.update_edge()
            finally:
                self.updating_from_parent = False

            self.update()
            event.accept()
        else:
            return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._drag_start_scene = None
            self._original_vertices_positions = None
            self._original_control_positions = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def EdgeItemFactory(self, edge: Edge, parent):
        if edge.type == EdgeType.LINE:
            if self._line_drawing_mode == LineDrawingMode.QGRAPHICS:
                return StandardLineEdgeItem(edge, parent)
            elif self._line_drawing_mode == LineDrawingMode.BRESENHAM:
                return BresenhamLineEdgeItem(edge, parent)
        elif edge.type == EdgeType.BEZIER:
            return BezierEdgeItem(edge, parent)
        elif edge.type == EdgeType.ARC:
            return ArcEdgeItem(edge, parent)

    # Method called by VertexItem when user directly drags a single vertex
    def on_vertex_moved(self, vertex: Vertex, vertex_new_scene_coords: QPointF):
        vertex.x = vertex_new_scene_coords.x()
        vertex.y = vertex_new_scene_coords.y()

        # Propagate constraints in both directions around the polygon (circular)
        n = len(self.polygon.vertices)
        if n > 1:
            # Rightwards propagation (increasing index, wrap-around)
            idx = self.polygon.vertices.index(vertex)
            i = idx
            while True:
                j = (i + 1) % n
                if j == idx:
                    break
                v1 = self.polygon.vertices[i]
                v2 = self.polygon.vertices[j]
                continue_propagation = self._enforce_edge_constraint(v1, v2)
                if not continue_propagation:
                    break
                i = j

            # Leftwards propagation (decreasing index, wrap-around)
            i = idx
            while True:
                j = (i - 1) % n
                if j == idx:
                    break
                v1 = self.polygon.vertices[i]
                v2 = self.polygon.vertices[j]
                continue_propagation = self._enforce_edge_constraint(v1, v2)
                if not continue_propagation:
                    break
                i = j
        
        # Updating the visuals
        self.updating_from_parent = True
        try:
            for v, v_item in self.vertex_items.items():
                vertex_parent_coords = self.mapFromScene(QPointF(v.x, v.y))
                v_item.setPos(vertex_parent_coords)
            for e_item in self.edge_items:
                e_item.update_edge()
        finally:
            self.updating_from_parent = False

        # Enforce continuity constraints for any vertices that requested it
        for v in self.polygon.vertices:
            if v.continuity is not None and v.continuity != ContinuityType.G0:
                self.enforce_vertex_continuity_from_vertex(v)

        self.update()

    def _enforce_edge_constraint(self, v1: Vertex, v2: Vertex) -> bool:
        current_edge = self._edge_between(v1, v2)
        # If we couldn't find an edge connecting v1 and v2, stop propagation
        if current_edge is None:
            return False
        # If edge has no constraint, stop propagation
        if current_edge.constraint_type == ConstraintType.NONE:
            return False
        elif current_edge.constraint_type == ConstraintType.VERTICAL:
            v2.x = v1.x
        elif current_edge.constraint_type == ConstraintType.FIXED_LENGTH:
            L = current_edge.constraint_value
            dx = v2.x - v1.x
            dy = v2.y - v1.y
            dist = (dx*dx + dy*dy) ** 0.5
            if dist == 0:
                v2.x = v1.x + L
                v2.y = v1.y
            else:
                scale = L / dist
                v2.x = v1.x + dx * scale
                v2.y = v1.y + dy * scale
        elif current_edge.constraint_type == ConstraintType.DIAGONAL_45:
            # Project direction to nearest 45° while preserving current Euclidean length
            dx = v2.x - v1.x
            dy = v2.y - v1.y
            dist = math.hypot(dx, dy)
            if dist < 1e-8:
                # If degenerate, keep a small step in the quadrant inferred by neighbors
                sx = 1 if dx >= 0 else -1
                sy = 1 if dy >= 0 else -1
                inv_sqrt2 = 1.0 / math.sqrt(2.0)
                ux = sx * inv_sqrt2
                uy = sy * inv_sqrt2
                step = 1.0
                v2.x = v1.x + ux * step
                v2.y = v1.y + uy * step
            else:
                sx = 1 if dx >= 0 else -1
                sy = 1 if dy >= 0 else -1
                inv_sqrt2 = 1.0 / math.sqrt(2.0)
                ux = sx * inv_sqrt2
                uy = sy * inv_sqrt2
                v2.x = v1.x + ux * dist
                v2.y = v1.y + uy * dist
        else:
            return False

        return True

    def adjacent_edges_of_vertex(self, vertex: Vertex):
        if vertex not in self.polygon.vertices:
            return (None, None, None, None)
        edges = self.polygon.edges
        n_edges = len(edges)
        if n_edges == 0:
            return (None, None, None, None)

        incident = [e for e in edges if getattr(e, 'v1', None) is vertex or getattr(e, 'v2', None) is vertex]
        prev_edge = next_edge = None
        prev_idx = next_idx = None

        if incident:
            for e in incident:
                if getattr(e, 'v2', None) is vertex and prev_edge is None:
                    prev_edge = e
                    try:
                        prev_idx = edges.index(e)
                    except ValueError:
                        prev_idx = None
                if getattr(e, 'v1', None) is vertex and next_edge is None:
                    next_edge = e
                    try:
                        next_idx = edges.index(e)
                    except ValueError:
                        next_idx = None

        # If one side is still missing (e.g., inconsistent orientation), try to infer
        if (prev_edge is None or next_edge is None) and vertex in self.polygon.vertices:
            n = len(self.polygon.vertices)
            idx = self.polygon.vertices.index(vertex)
            # Expected mapping: edges[i] = (vertices[i] -> vertices[(i+1)%n])
            infer_prev_idx = (idx - 1) % n
            infer_next_idx = idx % n
            if prev_edge is None and 0 <= infer_prev_idx < n_edges:
                prev_edge = edges[infer_prev_idx]
                prev_idx = infer_prev_idx
            if next_edge is None and 0 <= infer_next_idx < n_edges:
                next_edge = edges[infer_next_idx]
                next_idx = infer_next_idx

        return (prev_edge, prev_idx, next_edge, next_idx)

    def _project_direction_to_constraint(
        self,
        vertex: Vertex,
        other_vertex: Vertex,
        desired_dir: tuple[float, float] | None,
        constraint_type: ConstraintType,
        constraint_value,
    ) -> tuple[tuple[float, float], float]:
        vx = vertex.x
        vy = vertex.y
        dx = other_vertex.x - vx
        dy = other_vertex.y - vy
        _, current_len = normalize_vector((dx, dy))
        if current_len < 1e-8:
            if constraint_type == ConstraintType.FIXED_LENGTH and constraint_value:
                current_len = abs(constraint_value)
            else:
                current_len = 1.0

        if desired_dir is None:
            desired_dir = (dx, dy)

        dir_norm, _ = normalize_vector(desired_dir)
        if dir_norm is None:
            dir_norm, _ = normalize_vector((dx, dy))
        if dir_norm is None:
            dir_norm = (1.0, 0.0)

        ux, uy = dir_norm

        if constraint_type == ConstraintType.VERTICAL:
            sign = -1.0 if uy < 0 else 1.0 if uy > 0 else (-1.0 if dy < 0 else 1.0)
            ux = 0.0
            uy = sign
            base_len = current_len
        elif constraint_type == ConstraintType.DIAGONAL_45:
            sx = -1.0 if ux < 0 else 1.0 if ux > 0 else (-1.0 if dx < 0 else 1.0)
            sy = -1.0 if uy < 0 else 1.0 if uy > 0 else (-1.0 if dy < 0 else 1.0)
            factor = 1.0 / math.sqrt(2.0)
            ux = sx * factor
            uy = sy * factor
            base_len = current_len
        elif constraint_type == ConstraintType.FIXED_LENGTH:
            base_len = abs(constraint_value) if constraint_value is not None else current_len
            if base_len < 1e-8:
                base_len = current_len if current_len > 1e-8 else 1.0
        else:
            base_len = current_len

        return (ux, uy), base_len

    # --- Arc helpers for continuity with Bezier ---
    def _arc_tangent_at_vertex(self, arc_edge: Edge, at_v1: bool) -> tuple[float, float] | None:
        if getattr(arc_edge, 'type', None) != EdgeType.ARC:
            return None

        # locate index of this arc to access neighbours in polygon order
        try:
            idx = self.polygon.edges.index(arc_edge)
        except ValueError:
            return None
        n_edges = len(self.polygon.edges)

        v1 = arc_edge.v1
        v2 = arc_edge.v2
        x1, y1 = v1.x, v1.y
        x2, y2 = v2.x, v2.y
        chord_u, chord_len = unit(x2 - x1, y2 - y1)
        if chord_u is None or chord_len < 1e-8:
            return None

        # continuity flags (only one end may be G1)
        g1_v1 = getattr(v1, 'continuity', None) == ContinuityType.G1
        g1_v2 = getattr(v2, 'continuity', None) == ContinuityType.G1
        if g1_v1 and g1_v2:
            # honor only v1 per rule
            g1_v2 = False

        Mx = (x1 + x2) * 0.5
        My = (y1 + y2) * 0.5
        ncx, ncy = rot90_ccw(*chord_u)

        Cx, Cy = Mx, My
        R = chord_len * 0.5
        prefer_ccw = True

        # tangent from neighbour edge at the chosen endpoint if G1
        def neighbour_tangent_for_arc(at_v1_local: bool):
            # For v1 use edge before arc; for v2 use edge after arc
            if at_v1_local:
                ne = self.polygon.edges[(idx - 1) % n_edges]
                vertex = v1
                # direction along neighbour at vertex
                if ne.v2 is vertex:
                    vx = vertex.x - ne.v1.x; vy = vertex.y - ne.v1.y
                else:
                    vx = ne.v2.x - vertex.x; vy = ne.v2.y - vertex.y
                if getattr(ne, 'type', None) == EdgeType.BEZIER:
                    try:
                        vx = vertex.x - ne.c2.x; vy = vertex.y - ne.c2.y
                    except Exception:
                        pass
            else:
                ne = self.polygon.edges[(idx + 1) % n_edges]
                vertex = v2
                if ne.v1 is vertex:
                    vx = ne.v2.x - vertex.x; vy = ne.v2.y - vertex.y
                else:
                    vx = vertex.x - ne.v1.x; vy = vertex.y - ne.v1.y
                if getattr(ne, 'type', None) == EdgeType.BEZIER:
                    try:
                        vx = ne.c1.x - vertex.x; vy = ne.c1.y - vertex.y
                    except Exception:
                        pass
            u, _ = unit(vx, vy)
            return u

        if g1_v1 or g1_v2:
            if g1_v1:
                t = neighbour_tangent_for_arc(True); Px, Py = x1, y1
            else:
                t = neighbour_tangent_for_arc(False); Px, Py = x2, y2
            if t is not None:
                ntx, nty = rot90_ccw(*t)
                mx = Mx - Px; my = My - Py
                det = ntx * (-ncy) - nty * (-ncx)
                if abs(det) > 1e-8:
                    s = (mx * (-ncy) - my * (-ncx)) / det
                    Cx = Px + s * ntx; Cy = Py + s * nty
                    R = math.hypot(Px - Cx, Py - Cy)
                    rx = Px - Cx; ry = Py - Cy
                    r_u, _ = unit(rx, ry)
                    if r_u is not None:
                        t_ccw = rot90_ccw(*r_u)
                        t_cw = rot90_cw(*r_u)
                        dot_ccw = t_ccw[0] * t[0] + t_ccw[1] * t[1]
                        dot_cw = t_cw[0] * t[0] + t_cw[1] * t[1]
                        prefer_ccw = dot_ccw >= dot_cw

        # tangent at requested vertex along polygon direction
        if at_v1:
            rx = x1 - Cx; ry = y1 - Cy
        else:
            rx = x2 - Cx; ry = y2 - Cy
        r_u, _ = unit(rx, ry)
        if r_u is None:
            return None
        if prefer_ccw:
            return rot90_ccw(*r_u)
        else:
            return (-rot90_ccw(*r_u)[0], -rot90_ccw(*r_u)[1])  # rot90_cw

    def apply_continuity_to_vertex(self, vertex: Vertex, continuity: ContinuityType) -> bool:
        # Now applicable when at least one adjacent edge is Bezier or Arc
        prev_edge, prev_idx, next_edge, next_idx = self.adjacent_edges_of_vertex(vertex)
        if prev_edge is None or next_edge is None:
            return False

        t1 = prev_edge.type
        t2 = next_edge.type
        has_bez = (t1 == EdgeType.BEZIER) or (t2 == EdgeType.BEZIER)
        has_arc = (t1 == EdgeType.ARC) or (t2 == EdgeType.ARC)
        both_line = (t1 == EdgeType.LINE) and (t2 == EdgeType.LINE)

        if both_line:
            return False
        # For any configuration involving an Arc, C1 is not supported
        if has_arc and continuity == ContinuityType.C1:
            return False

        # For Arc edges: only one endpoint may be G1 on a given arc
        if continuity == ContinuityType.G1 and has_arc:
            # clear previous warning
            self.last_continuity_warning = None
            conflicts = []
            if t1 == EdgeType.ARC and prev_edge is not None:
                other = prev_edge.v2 if prev_edge.v1 is vertex else prev_edge.v1
                if getattr(other, 'continuity', None) == ContinuityType.G1:
                    conflicts.append(prev_edge)
            if t2 == EdgeType.ARC and next_edge is not None:
                other = next_edge.v2 if next_edge.v1 is vertex else next_edge.v1
                if getattr(other, 'continuity', None) == ContinuityType.G1:
                    conflicts.append(next_edge)
            if conflicts:
                # Warn and reject
                msg = (
                    "You cannot set G1 continuity at this vertex because the other vertex on the associated arc already has G1.\n"
                    "For a single arc, only one of its vertices can have the G1 continuity."
                )
                self.last_continuity_warning = msg
                return False

        # Set continuity on the vertex
        vertex.continuity = continuity

        # Enforce immediately for Bezier-related cases; for Arc-related
        # cases, enforcement is handled implicitly by ArcEdgeItem geometry,
        # but we still refresh visuals.
        if has_bez:
            self.enforce_vertex_continuity_from_vertex(vertex)

        # Update visuals for affected edges
        try:
            self.edge_items[prev_idx].update_edge()
            self.edge_items[next_idx].update_edge()
            self.update()
        except Exception:
            pass
        return True
    
    # Metoda wywoływana przez _on_vertex_moved oraz apply_continuity_to_vertex.
    # Modyfikuje punkt kontrolny krzywej beziera związanej z wierzchołkiem, tak,
    # aby zachować przypisaną ciągłość dla tego wierzchołka (modyfikujemy tylko
    # pozycję punktu kontrolnego)
    def enforce_vertex_continuity_from_vertex(self, vertex: Vertex) -> None:
        prev_edge, prev_idx, next_edge, next_idx = self.adjacent_edges_of_vertex(vertex)
        if prev_edge is None or next_edge is None:
            return

        cont = getattr(vertex, 'continuity', None)
        if cont is None or cont == ContinuityType.G0:
            return

        # Coordinates
        vx = vertex.x
        vy = vertex.y

        prev_is_bezier = getattr(prev_edge, 'type', None) == EdgeType.BEZIER
        next_is_bezier = getattr(next_edge, 'type', None) == EdgeType.BEZIER

        # Case A: both Bezier (existing behavior)
        if prev_is_bezier and next_is_bezier:
            prev_c2 = prev_edge.c2
            next_c1 = next_edge.c1

            pvx = vx - prev_c2.x
            pvy = vy - prev_c2.y
            prev_len = math.hypot(pvx, pvy)
            nvx = next_c1.x - vx
            nvy = next_c1.y - vy
            next_len = math.hypot(nvx, nvy)

            if cont == ContinuityType.G1:
                # align unit tangent vectors; preserve handle lengths
                if prev_len > 1e-8:
                    ux = pvx / prev_len
                    uy = pvy / prev_len
                    # set next.c1 to point in same direction with its original length
                    next_edge.c1.x = vx + ux * next_len
                    next_edge.c1.y = vy + uy * next_len
                    # ensure prev control is aligned too (snap to exact opposite direction preserving length)
                    prev_edge.c2.x = vx - ux * prev_len
                    prev_edge.c2.y = vy - uy * prev_len
                elif next_len > 1e-8:
                    ux = nvx / next_len
                    uy = nvy / next_len
                    prev_edge.c2.x = vx - ux * prev_len
                    prev_edge.c2.y = vy - uy * prev_len
            elif cont == ContinuityType.C1:
                # enforce equality of tangent vectors: (v - prev.c2) == (next.c1 - v)
                next_edge.c1.x = 2 * vx - prev_c2.x
                next_edge.c1.y = 2 * vy - prev_c2.y
                prev_edge.c2.x = 2 * vx - next_edge.c1.x
                prev_edge.c2.y = 2 * vy - next_edge.c1.y

        # Case B1: prev is Bezier, next is ARC — align Bezier handle to arc tangent
        elif prev_is_bezier and getattr(next_edge, 'type', None) == EdgeType.ARC:
            prev_c2 = prev_edge.c2
            pvx = vx - prev_c2.x
            pvy = vy - prev_c2.y
            prev_len = math.hypot(pvx, pvy)
            if cont == ContinuityType.G1 and prev_len > 1e-8:
                t = self._arc_tangent_at_vertex(next_edge, at_v1=True)
                if t is not None:
                    prev_edge.c2.x = vx - t[0] * prev_len
                    prev_edge.c2.y = vy - t[1] * prev_len

        # Case B2: prev is Bezier, next is LINE
        elif prev_is_bezier and not next_is_bezier:
            # line tangent at v is (next_edge.v2 - v)
            other = next_edge.v2
            lvx = other.x - vx
            lvy = other.y - vy
            l_len = math.hypot(lvx, lvy)
            prev_c2 = prev_edge.c2
            pvx = vx - prev_c2.x
            pvy = vy - prev_c2.y
            prev_len = math.hypot(pvx, pvy)

            if l_len < 1e-8:
                return

            if cont == ContinuityType.G1:
                ux = lvx / l_len
                uy = lvy / l_len
                # align prev handle direction with line direction, preserve prev handle length
                prev_edge.c2.x = vx - ux * prev_len
                prev_edge.c2.y = vy - uy * prev_len
            elif cont == ContinuityType.C1:
                # set prev.c2 so that (v - prev.c2) == (other - v)
                prev_edge.c2.x = vx - lvx
                prev_edge.c2.y = vy - lvy

        # Case C1: prev is ARC, next is Bezier — align Bezier handle to arc tangent
        elif getattr(prev_edge, 'type', None) == EdgeType.ARC and next_is_bezier:
            next_c1 = next_edge.c1
            nvx = next_c1.x - vx
            nvy = next_c1.y - vy
            next_len = math.hypot(nvx, nvy)
            if cont == ContinuityType.G1 and next_len > 1e-8:
                t = self._arc_tangent_at_vertex(prev_edge, at_v1=False)
                if t is not None:
                    next_edge.c1.x = vx + t[0] * next_len
                    next_edge.c1.y = vy + t[1] * next_len

        # Case C2: prev is LINE, next is Bezier
        elif not prev_is_bezier and next_is_bezier:
            # line tangent at v is (v - prev_edge.v1)
            other = prev_edge.v1
            lvx = vx - other.x
            lvy = vy - other.y
            l_len = math.hypot(lvx, lvy)
            next_c1 = next_edge.c1
            nvx = next_c1.x - vx
            nvy = next_c1.y - vy
            next_len = math.hypot(nvx, nvy)

            if l_len < 1e-8:
                return

            if cont == ContinuityType.G1:
                ux = lvx / l_len
                uy = lvy / l_len
                # align next handle direction with line direction, preserve next handle length
                next_edge.c1.x = vx + ux * next_len
                next_edge.c1.y = vy + uy * next_len
            elif cont == ContinuityType.C1:
                # set next.c1 so that (next.c1 - v) == (v - other)
                next_edge.c1.x = vx + lvx
                next_edge.c1.y = vy + lvy

        # else: both not Bezier (shouldn't happen due to apply check)

        # After modifications, update visuals of affected edge items
        try:
            self.edge_items[prev_idx].update_edge()
            self.edge_items[next_idx].update_edge()
            self.update()
        except Exception:
            pass
    
    # Metoda wywoływana przez on_control_moved w BezierEdgeItem. Modyfikuje 
    # wierzchołek sąsiadujący z wierzchołkiem vertex po przesunięciu punktu
    # kontrolnego krzywej beziera związanego z wierzchołkiem vertex, tak aby zachować ciągłość
    # do niego przypisaną (modyfikujemy tylko pozycję wierzchołka sąsiadującego
    # z wierzchołkiem vertex, z którym tworzy on zwykłą krawędź)
    def enforce_vertex_continuity_from_control(self, vertex: Vertex, moved_control: str | None = None):
        prev_edge, prev_idx, next_edge, next_idx = self.adjacent_edges_of_vertex(vertex)
        if prev_edge is None or next_edge is None:
            return

        cont = getattr(vertex, 'continuity', None)
        if cont is None or cont == ContinuityType.G0:
            return

        vx = vertex.x
        vy = vertex.y

        prev_is_bezier = prev_edge.type == EdgeType.BEZIER
        next_is_bezier = next_edge.type == EdgeType.BEZIER

        moved_vertices = []

        # Case A: both Bezier — follow the moved handle as the driver
        if prev_is_bezier and next_is_bezier:
            prev_c2 = prev_edge.c2
            next_c1 = next_edge.c1

            pvx = vx - prev_c2.x
            pvy = vy - prev_c2.y
            prev_len = math.hypot(pvx, pvy)
            nvx = next_c1.x - vx
            nvy = next_c1.y - vy
            next_len = math.hypot(nvx, nvy)

            if cont == ContinuityType.G1:
                # Keep the moved side direction and align the other side to it
                if moved_control == 'prev' and prev_len > 1e-8:
                    ux = pvx / prev_len
                    uy = pvy / prev_len
                    next_edge.c1.x = vx + ux * max(next_len, 1e-8)
                    next_edge.c1.y = vy + uy * max(next_len, 1e-8)
                elif moved_control == 'next' and next_len > 1e-8:
                    ux = nvx / next_len
                    uy = nvy / next_len
                    prev_edge.c2.x = vx - ux * max(prev_len, 1e-8)
                    prev_edge.c2.y = vy - uy * max(prev_len, 1e-8)
                else:
                    # Fallback to previous heuristic if moved_control unknown
                    if prev_len > 1e-8:
                        ux = pvx / prev_len
                        uy = pvy / prev_len
                        next_edge.c1.x = vx + ux * next_len
                        next_edge.c1.y = vy + uy * next_len
                        prev_edge.c2.x = vx - ux * prev_len
                        prev_edge.c2.y = vy - uy * prev_len
                    elif next_len > 1e-8:
                        ux = nvx / next_len
                        uy = nvy / next_len
                        prev_edge.c2.x = vx - ux * prev_len
                        prev_edge.c2.y = vy - uy * prev_len
            elif cont == ContinuityType.C1:
                # Reflect across vertex; preserve the moved handle as-is
                if moved_control == 'prev':
                    # user moved prev.c2 -> set next.c1 as reflection
                    next_edge.c1.x = 2 * vx - prev_c2.x
                    next_edge.c1.y = 2 * vy - prev_c2.y
                elif moved_control == 'next':
                    # user moved next.c1 -> set prev.c2 as reflection
                    prev_edge.c2.x = 2 * vx - next_edge.c1.x
                    prev_edge.c2.y = 2 * vy - next_edge.c1.y
                else:
                    # Unknown driver -> symmetric reflection (legacy)
                    next_edge.c1.x = 2 * vx - prev_c2.x
                    next_edge.c1.y = 2 * vy - prev_c2.y
                    prev_edge.c2.x = 2 * vx - next_edge.c1.x
                    prev_edge.c2.y = 2 * vy - next_edge.c1.y

        # Case B0: prev is Bezier, next is ARC — align Bezier handle to arc tangent
        elif prev_is_bezier and getattr(next_edge, 'type', None) == EdgeType.ARC:
            prev_c2 = prev_edge.c2
            pvx = vx - prev_c2.x
            pvy = vy - prev_c2.y
            prev_len = math.hypot(pvx, pvy)
            if cont == ContinuityType.G1 and prev_len > 1e-8:
                t = self._arc_tangent_at_vertex(next_edge, at_v1=True)
                if t is not None:
                    prev_edge.c2.x = vx - t[0] * prev_len
                    prev_edge.c2.y = vy - t[1] * prev_len

        # Case B: prev is Bezier, next is LINE — adjust straight-edge endpoint
        elif prev_is_bezier and not next_is_bezier:
            prev_c2 = prev_edge.c2
            pvx = vx - prev_c2.x
            pvy = vy - prev_c2.y
            prev_len = math.hypot(pvx, pvy)

            other = next_edge.v2
            line_constraint = getattr(next_edge, 'constraint_type', ConstraintType.NONE)
            constraint_val = getattr(next_edge, 'constraint_value', None)

            if line_constraint != ConstraintType.NONE:
                dir_unit, base_len = self._project_direction_to_constraint(
                    vertex,
                    other,
                    (pvx, pvy),
                    line_constraint,
                    constraint_val,
                )
            else:
                dir_unit, _ = normalize_vector((pvx, pvy))
                if dir_unit is None:
                    dir_unit, base_len = normalize_vector((other.x - vx, other.y - vy))
                else:
                    base_len = math.hypot(other.x - vx, other.y - vy)
                if dir_unit is None:
                    dir_unit = (1.0, 0.0)
                if base_len < 1e-8:
                    base_len = prev_len if prev_len > 1e-8 else 1.0

            line_len = base_len
            if cont == ContinuityType.G1:
                if prev_len > 1e-8:
                    prev_edge.c2.x = vx - dir_unit[0] * prev_len
                    prev_edge.c2.y = vy - dir_unit[1] * prev_len
            elif cont == ContinuityType.C1:
                line_len = base_len if line_constraint == ConstraintType.FIXED_LENGTH else (prev_len if prev_len > 1e-8 else base_len)
                prev_edge.c2.x = vx - dir_unit[0] * line_len
                prev_edge.c2.y = vy - dir_unit[1] * line_len
            else:
                return

            other.x = vx + dir_unit[0] * line_len
            other.y = vy + dir_unit[1] * line_len
            moved_vertices.append(other)

        # Case C0: prev is ARC, next is Bezier — align Bezier handle to arc tangent
        elif getattr(prev_edge, 'type', None) == EdgeType.ARC and next_is_bezier:
            next_c1 = next_edge.c1
            nvx = next_c1.x - vx
            nvy = next_c1.y - vy
            next_len = math.hypot(nvx, nvy)
            if cont == ContinuityType.G1 and next_len > 1e-8:
                t = self._arc_tangent_at_vertex(prev_edge, at_v1=False)
                if t is not None:
                    next_edge.c1.x = vx + t[0] * next_len
                    next_edge.c1.y = vy + t[1] * next_len

        # Case C: prev is LINE, next is Bezier — adjust previous-line vertex
        elif not prev_is_bezier and next_is_bezier:
            next_c1 = next_edge.c1
            nvx = next_c1.x - vx
            nvy = next_c1.y - vy
            next_len = math.hypot(nvx, nvy)

            other = prev_edge.v1
            line_constraint = getattr(prev_edge, 'constraint_type', ConstraintType.NONE)
            constraint_val = getattr(prev_edge, 'constraint_value', None)
            desired_dir = (-nvx, -nvy)

            if line_constraint != ConstraintType.NONE:
                dir_unit, base_len = self._project_direction_to_constraint(
                    vertex,
                    other,
                    desired_dir,
                    line_constraint,
                    constraint_val,
                )
            else:
                dir_unit, _ = normalize_vector(desired_dir)
                if dir_unit is None:
                    dir_unit, base_len = normalize_vector((other.x - vx, other.y - vy))
                else:
                    base_len = math.hypot(other.x - vx, other.y - vy)
                if dir_unit is None:
                    dir_unit = (-1.0, 0.0)
                if base_len < 1e-8:
                    base_len = next_len if next_len > 1e-8 else 1.0

            line_len = base_len
            if cont == ContinuityType.G1:
                if next_len > 1e-8:
                    next_edge.c1.x = vx - dir_unit[0] * next_len
                    next_edge.c1.y = vy - dir_unit[1] * next_len
            elif cont == ContinuityType.C1:
                line_len = base_len if line_constraint == ConstraintType.FIXED_LENGTH else (next_len if next_len > 1e-8 else base_len)
                next_edge.c1.x = vx - dir_unit[0] * line_len
                next_edge.c1.y = vy - dir_unit[1] * line_len
            else:
                return

            other.x = vx + dir_unit[0] * line_len
            other.y = vy + dir_unit[1] * line_len
            moved_vertices.append(other)

        # Update visuals: edges and vertex positions
        try:
            self.edge_items[prev_idx].update_edge()
            self.edge_items[next_idx].update_edge()
        except Exception:
            pass

        try:
            self.updating_from_parent = True
            for v, v_item in self.vertex_items.items():
                vertex_parent_coords = self.mapFromScene(QPointF(v.x, v.y))
                v_item.setPos(vertex_parent_coords)
        finally:
            self.updating_from_parent = False

        for moved in moved_vertices:
            self.on_vertex_moved(moved, QPointF(moved.x, moved.y))

        try:
            self.update()
        except Exception:
            pass

    # Method called by LineEdgeItem when user wants to create new vertex
    def add_vertex_on_edge(self, edge: Edge):
        v1 = edge.v1
        v2 = edge.v2
        new_vertex = Vertex((v1.x + v2.x) / 2, (v1.y + v2.y) / 2)
        old_edge_index = self.polygon.edges.index(edge)

        # Insert new vertex in polygon.vertices right after v1
        try:
            v1_idx = self.polygon.vertices.index(v1)
        except ValueError:
            v1_idx = len(self.polygon.vertices) - 1
        self.polygon.vertices.insert(v1_idx + 1, new_vertex)

        # Replace edges: edge -> [edge(v1,new_v), edge(new_v,v2)]
        new_edge1 = Edge(v1, new_vertex)
        new_edge2 = Edge(new_vertex, v2)
        # New edges inherit no constraints from the parent edge
        new_edge1.constraint_type = ConstraintType.NONE
        new_edge1.constraint_value = None
        new_edge2.constraint_type = ConstraintType.NONE
        new_edge2.constraint_value = None
        self.polygon.edges[old_edge_index] = new_edge1
        self.polygon.edges.insert(old_edge_index + 1, new_edge2)

        # Sync the model's edge dictionary now that edges changed, then
        # rebuild view based on the new model
        self._sync_edges_dict()
        self._rebuild_childitems()

    # Method called by VertexItem when user wants to delete it
    def delete_vertex(self, vertex: Vertex):
        n = len(self.polygon.vertices)

        # We require at least 3 to keep the polygon structure
        if n > 3:
            del_vertex_index = self.polygon.vertices.index(vertex)
            prev_vertex_index = (del_vertex_index - 1) % n
            next_vertex_index = (del_vertex_index + 1) % n

            prev_vertex = self.polygon.vertices[prev_vertex_index]
            next_vertex = self.polygon.vertices[next_vertex_index]

            # Remove the vertex from vertices list
            del self.polygon.vertices[del_vertex_index]

            # Find the two edges that reference this vertex and replace them by
            # a single edge connecting prev_v -> next_v
            edge_indices = [i for i, e in enumerate(self.polygon.edges) if e.v1 is vertex or e.v2 is vertex]

            # We sort them for easier referencing
            edge_indices.sort()
            # Replace the lower index with the new connecting edge
            replace_index = edge_indices[0]
            self.polygon.edges[replace_index] = Edge(prev_vertex, next_vertex)

            # Remove the other edge(s) that were connected with the deleted 
            # vertex. Iterate from highest to lowest to keep indices valid
            for del_edge_index in reversed(edge_indices[1:]):
                del self.polygon.edges[del_edge_index]

            # Sync edges dict and rebuild view based on the new model
            self._sync_edges_dict()
            self._rebuild_childitems()
        else:
            # Show a short info when trying to remove a vertex from a triangle
            try:
                QMessageBox.warning(
                    None,
                    "Removing Vertex",
                    "You cannot delete a vertex — a polygon must have at least 3 vertices.",
                )
            except Exception:
                # In non-GUI or testing contexts, just ignore the message box
                pass

    def apply_constraint_to_edge(self, edge: Edge, constraint_type: ConstraintType, value=None) -> bool:
        idx = self.polygon.edges.index(edge)

        # If clearing constraint
        if constraint_type == ConstraintType.NONE:
            edge.constraint_type = ConstraintType.NONE
            edge.constraint_value = None
            self._rebuild_childitems()
            return True

        # Check neighbor constraints for disallowed combinations
        n = len(self.polygon.edges)
        prev_edge = self.polygon.edges[(idx - 1) % n]
        next_edge = self.polygon.edges[(idx + 1) % n]
        if constraint_type == ConstraintType.VERTICAL:
            if getattr(prev_edge, 'constraint_type', ConstraintType.NONE) == ConstraintType.VERTICAL or getattr(next_edge, 'constraint_type', ConstraintType.NONE) == ConstraintType.VERTICAL:
                return False

        # Apply constraint to model
        edge.constraint_type = constraint_type
        edge.constraint_value = value

        # Enforce the constraint immediately by adjusting one endpoint (v2)
        other = edge.v1
        moving = edge.v2
        if constraint_type == ConstraintType.VERTICAL:
            moving.x = other.x
        elif constraint_type == ConstraintType.DIAGONAL_45:
            # Set direction to nearest 45° and preserve current Euclidean length
            dx = moving.x - other.x
            dy = moving.y - other.y
            dist = math.hypot(dx, dy)
            if dist < 1e-8:
                sx = 1 if dx >= 0 else -1
                sy = 1 if dy >= 0 else -1
                inv_sqrt2 = 1.0 / math.sqrt(2.0)
                ux = sx * inv_sqrt2
                uy = sy * inv_sqrt2
                step = 1.0
                moving.x = other.x + ux * step
                moving.y = other.y + uy * step
            else:
                sx = 1 if dx >= 0 else -1
                sy = 1 if dy >= 0 else -1
                inv_sqrt2 = 1.0 / math.sqrt(2.0)
                ux = sx * inv_sqrt2
                uy = sy * inv_sqrt2
                moving.x = other.x + ux * dist
                moving.y = other.y + uy * dist
        elif constraint_type == ConstraintType.FIXED_LENGTH:
            L = value
            if L is None:
                # nothing to enforce
                pass
            else:
                dx = moving.x - other.x
                dy = moving.y - other.y
                dist = (dx*dx + dy*dy) ** 0.5
                if dist == 0:
                    moving.x = other.x + L
                    moving.y = other.y
                else:
                    scale = L / dist
                    moving.x = other.x + dx * scale
                    moving.y = other.y + dy * scale

        # Rebuild view to show icon and updated positions
        self._rebuild_childitems()
        return True

    # Method called by MainWindow when line drawing mode is changed
    def redraw_with_new_mode(self, mode: LineDrawingMode):
        # Update line drawing mode
        self._line_drawing_mode = mode

        # Remove old edge items
        for e_item in self.edge_items:
            e_item.setParentItem(None)
            scene = self.scene()
            if scene:
                scene.removeItem(e_item)
        self.edge_items.clear()

        # Create new edge items according to new drawing mode
        for e in self.polygon.edges:
            e_item = self.EdgeItemFactory(e, parent=self)
            self.edge_items.append(e_item)
            # Redrawing
            e_item.update_edge()

        self.update()

    def _enforce_all_constraints_and_continuity(self):
        # Sync map for robustness
        self._sync_edges_dict()

        # 1) Enforce constraints edge-by-edge (no propagation needed here)
        for e in list(self.polygon.edges):
            if getattr(e, 'constraint_type', ConstraintType.NONE) != ConstraintType.NONE:
                try:
                    self._enforce_edge_constraint(e.v1, e.v2)
                except Exception:
                    continue

        # 2) Enforce continuity at vertices that request it
        for v in list(self.polygon.vertices):
            cont = getattr(v, 'continuity', None)
            if cont is not None and cont != ContinuityType.G0:
                try:
                    self.enforce_vertex_continuity_from_vertex(v)
                except Exception:
                    continue

        # 3) Refresh visuals: positions and edges
        self.updating_from_parent = True
        try:
            for v, v_item in self.vertex_items.items():
                vertex_parent_coords = self.mapFromScene(QPointF(v.x, v.y))
                v_item.setPos(vertex_parent_coords)
            for e_item in self.edge_items:
                e_item.update_edge()
        finally:
            self.updating_from_parent = False
        try:
            self.update()
        except Exception:
            pass