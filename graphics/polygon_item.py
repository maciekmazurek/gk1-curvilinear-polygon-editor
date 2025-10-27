from model import *
from graphics.vertex_item import VertexItem
from graphics.line_edge_item import StandardLineEdgeItem, BresenhamLineEdgeItem
from graphics.bezier_edge_item import BezierEdgeItem
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtGui import (
    QColor,
    QPainterPath,
    QPen,
)
from PySide6.QtCore import QPointF, QRectF, Qt

class PolygonItem(QGraphicsItem):
    def __init__(self, polygon: Polygon):
        super().__init__()
        self.polygon = polygon
        # We disable QGraphics Framework's built-in moving mechanism
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        # Default line drawing mode
        self.line_drawing_mode = LineDrawingMode.QGRAPHICS

        # Flag indicating whether the position of vertices is being currently 
        # updated by the parent (this class)
        self.updating_from_parent = False

        # Properties used for implementing polygon dragging
        self._dragging = False
        self._drag_start_scene = None
        self._original_vertices_positions = None
        self._original_control_positions = None

        self.vertex_items = {}
        self.edge_items = []

        self._setup_childitems()

    def boundingRect(self):
        # Build union of:
        #  - vertex bounding box (scene coords -> local)
        #  - bounding rects of all child edge items (they are in local coords)
        rects = []

        if self.polygon.vertices:
            minx = min(v.x for v in self.polygon.vertices)
            miny = min(v.y for v in self.polygon.vertices)
            maxx = max(v.x for v in self.polygon.vertices)
            maxy = max(v.y for v in self.polygon.vertices)
            top_left = self.mapFromScene(QPointF(minx, miny))
            bottom_right = self.mapFromScene(QPointF(maxx, maxy))
            rects.append(QRectF(top_left, bottom_right).normalized())

        # include child edge items' bounding rects (already in local coords)
        for e_item in getattr(self, "edge_items", []):
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
        """
        Build path corresponding to actual edges. This is used only for hit-testing
        and selection. For LINE edges we add straight segments, for BEZIER we add a
        cubicTo (used only by shape() — actual drawing of bezier is pixelized in
        BezierEdgeItem).
        """
        path = QPainterPath()
        if not self.polygon.edges:
            return path

        # start from first edge's v1
        first_edge = self.polygon.edges[0]
        start = self.mapFromScene(QPointF(first_edge.v1.x, first_edge.v1.y))
        path.moveTo(start)

        for e in self.polygon.edges:
            if getattr(e, "type", None) == EdgeType.LINE:
                p2 = self.mapFromScene(QPointF(e.v2.x, e.v2.y))
                path.lineTo(p2)
            elif getattr(e, "type", None) == EdgeType.BEZIER:
                # add cubicTo for hit-testing (control points in scene coords -> map)
                c1 = self.mapFromScene(QPointF(e.c1.x, e.c1.y))
                c2 = self.mapFromScene(QPointF(e.c2.x, e.c2.y))
                p3 = self.mapFromScene(QPointF(e.v2.x, e.v2.y))
                path.cubicTo(c1, c2, p3)
            else:
                # fallback to straight line
                p2 = self.mapFromScene(QPointF(e.v2.x, e.v2.y))
                path.lineTo(p2)

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
        """Return the Edge instance connecting vertices a and b if present.

        The edges_dict stores keys as ordered pairs (v1, v2). This helper
        tries both orientations and returns None if no connecting edge is
        found. This prevents KeyError during drag propagation when order may
        differ.
        """
        ed = getattr(self.polygon, 'edges_dict', None)
        if not ed:
            return None
        return ed.get((a, b)) or ed.get((b, a))

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
            if self.line_drawing_mode == LineDrawingMode.QGRAPHICS:
                return StandardLineEdgeItem(edge, parent)
            elif self.line_drawing_mode == LineDrawingMode.BRESENHAM:
                return BresenhamLineEdgeItem(edge, parent)
        elif edge.type == EdgeType.BEZIER:
            return BezierEdgeItem(edge, parent)

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
                continue_propagation = self._relax_edge_constraint(v1, v2)
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
                continue_propagation = self._relax_edge_constraint(v1, v2)
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

        self.update()

    def _relax_edge_constraint(self, v1: Vertex, v2: Vertex) -> bool:
        current_edge = self._edge_between(v1, v2)
        # If we couldn't find an edge connecting v1 and v2, stop propagation
        if current_edge is None:
            return False
        # Jeżeli krawedz nie ma ograniczenia to przerywamy propagacje
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
            dx = v2.x - v1.x
            dy = v2.y - v1.y
            sx = 1 if dx >= 0 else -1
            sy = 1 if dy >= 0 else -1
            mag = max(abs(dx), abs(dy))
            v2.x = v1.x + sx * mag
            v2.y = v1.y + sy * mag
        else:
            return False

        return True

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
            dx = moving.x - other.x
            dy = moving.y - other.y
            sx = 1 if dx >= 0 else -1
            sy = 1 if dy >= 0 else -1
            mag = max(abs(dx), abs(dy))
            moving.x = other.x + sx * mag
            moving.y = other.y + sy * mag
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
        self.line_drawing_mode = mode

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