from model.model import *
from config import *
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QMenu,
    QInputDialog,
    QMessageBox,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QImage,
    QPixmap,
    QPainter
)
from PySide6.QtCore import QPointF, QRectF, Qt

import algorithms

from graphics.vertex_item import VertexItem
from graphics.controlpoint_item import ControlPointItem
    
# Base class for edge items (StandardLine, BresenhamLine, Bezier, Arc)
class EdgeItem(QGraphicsItem):
    def __init__(self, edge: Edge, parent):
        super().__init__(parent)
        self.edge = edge
        # Setting Z value to be below vertices
        self.setZValue(1.0)

    # Subclasses must implement:
    def update_edge(self) -> None:
        raise NotImplementedError

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, 0, 0)

    def paint(self, painter, option, widget) -> None:
        raise NotImplementedError

    def shape(self) -> QPainterPath:
        return QPainterPath()

class LineEdgeItem(EdgeItem):
    def __init__(self, edge: Edge, parent):
        if edge.type != EdgeType.LINE:
            pass # Should implement raising an error
        super().__init__(edge, parent)
        self._cached_bounding = QRectF(0, 0, 0, 0)
        self._p1 = QPointF()
        self._p2 = QPointF()

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)

    def convert_coords_to_parent(self):
        p1 = self.parentItem().mapFromScene(QPointF(self.edge.v1.x, self.edge.v1.y))
        p2 = self.parentItem().mapFromScene(QPointF(self.edge.v2.x, self.edge.v2.y))
        return (p1, p2)
    
    def contextMenuEvent(self, event):
        menu = QMenu()
        add_vertex_action = menu.addAction("Add new vertex")
        set_vertical_action = menu.addAction("Set constraint: Vertical")
        set_45_action = menu.addAction("Set constraint: 45°")
        set_length_action = menu.addAction("Set constraint: Fixed length...")
        clear_constraint_action = menu.addAction("Clear constraint")

        # Converting screenPos from QPointF to QPoint so we can pass it to
        # menu.exec()
        sp = event.screenPos()
        try:
            qp = sp.toPoint()
        except Exception:
            qp = sp
        chosen_action = menu.exec(qp)

        parent = self.parentItem()
        if chosen_action == add_vertex_action:
            if parent:
                parent.add_vertex_on_edge(self.edge)
        elif chosen_action == set_vertical_action:
            if parent:
                ok = parent.apply_constraint_to_edge(self.edge, ConstraintType.VERTICAL)
                if not ok:
                    QMessageBox.warning(None, "Constraint", "Cannot set vertical constraint: adjacent edge is already vertical.")
        elif chosen_action == set_45_action:
            if parent:
                parent.apply_constraint_to_edge(self.edge, ConstraintType.DIAGONAL_45)
        elif chosen_action == set_length_action:
            if parent:
                # ask user for desired length
                current_len = ((self.edge.v1.x - self.edge.v2.x)**2 + (self.edge.v1.y - self.edge.v2.y)**2) ** 0.5
                val, ok = QInputDialog.getDouble(None, "Fixed length", "Length:", current_len, 0.0, 1e6, 2)
                if ok:
                    parent.apply_constraint_to_edge(self.edge, ConstraintType.FIXED_LENGTH, val)
        elif chosen_action == clear_constraint_action:
            if parent:
                parent.apply_constraint_to_edge(self.edge, ConstraintType.NONE, None)

        event.accept()

    def _draw_constraint_icon(self, painter):
        ct = getattr(self.edge, "constraint_type", ConstraintType.NONE)
        if ct == ConstraintType.NONE:
            return
        mid = QPointF((self._p1.x() + self._p2.x()) / 2.0, (self._p1.y() + self._p2.y()) / 2.0)
        painter.save()
        painter.setPen(QPen(QColor("black")))
        if ct == ConstraintType.VERTICAL:
            painter.setBrush(QBrush(QColor("red")))
            painter.drawEllipse(mid, 6, 6)
            painter.setPen(QPen(QColor("white")))
            painter.drawText(QRectF(mid.x()-6, mid.y()-6, 12, 12), Qt.AlignCenter, "V")
        elif ct == ConstraintType.DIAGONAL_45:
            painter.setBrush(QBrush(QColor("green")))
            painter.drawEllipse(mid, 6, 6)
            painter.setPen(QPen(QColor("white")))
            painter.drawText(QRectF(mid.x()-6, mid.y()-6, 12, 12), Qt.AlignCenter, "45")
        elif ct == ConstraintType.FIXED_LENGTH:
            painter.setBrush(QBrush(QColor("blue")))
            painter.drawEllipse(mid, 6, 6)
            painter.setPen(QPen(QColor("white")))
            val = self.edge.constraint_value
            if val is None:
                s = "?"
            else:
                s = f"{val:.0f}"
            painter.drawText(QRectF(mid.x()-8, mid.y()-8, 16, 16), Qt.AlignCenter, s)
        painter.restore()

    def shape(self):
        # Provide a stroked path so mouse events (clicks/right-clicks) hit the line
        path = QPainterPath()
        path.moveTo(self._p1)
        path.lineTo(self._p2)
        stroker = QPainterPathStroker()
        stroker.setWidth(6.0)  # clickable tolerance in parent-local coordinates
        return stroker.createStroke(path)

# Rysowany za pomocą interfejsu udostępnianego przez QGraphics
class StandardLineEdgeItem(LineEdgeItem):
    def __init__(self, edge: Edge, parent):
        super().__init__(edge, parent)

    def update_edge(self):
        self.prepareGeometryChange()
        p1, p2 = self.convert_coords_to_parent()
        self._p1, self._p2 = p1, p2
        # bounding rect slightly expanded to include pen
        pen_margin = 1.0
        minx = min(p1.x(), p2.x()) - pen_margin
        miny = min(p1.y(), p2.y()) - pen_margin
        maxx = max(p1.x(), p2.x()) + pen_margin
        maxy = max(p1.y(), p2.y()) + pen_margin
        self._cached_bounding = QRectF(minx, miny, maxx - minx, maxy - miny)

    def boundingRect(self):
        return self._cached_bounding
    
    def paint(self, painter, option, widget):
        painter.setPen(QPen(QColor("black")))
        painter.drawLine(self._p1, self._p2)
        self._draw_constraint_icon(painter)

# Rysowany za pomocą własnej implementacji algorytmu Bresenhama
class BresenhamLineEdgeItem(LineEdgeItem):
    def __init__(self, edge: Edge, parent):
        super().__init__(edge, parent)
        self._pixels = []
        self._pixmap = None
        self._pixmap_offset = QPointF(0, 0)

    def boundingRect(self):
        return self._cached_bounding

    def update_edge(self):
        self.prepareGeometryChange()
        p1, p2 = self.convert_coords_to_parent()
        self._p1, self._p2 = p1, p2

        x0 = int(round(p1.x()))
        y0 = int(round(p1.y()))
        x1 = int(round(p2.x()))
        y1 = int(round(p2.y()))

        # Integer bounding box in parent coordinates
        minx = min(x0, x1) - 1
        miny = min(y0, y1) - 1
        maxx = max(x0, x1) + 1
        maxy = max(y0, y1) + 1

        width = maxx - minx + 1
        height = maxy - miny + 1

        if width <= 0 or height <= 0:
            self._pixmap = None
            minx = min(p1.x(), p2.x()) - 1
            miny = min(p1.y(), p2.y()) - 1
            maxx = max(p1.x(), p2.x()) + 1
            maxy = max(p1.y(), p2.y()) + 1
            self._cached_bounding = QRectF(minx, miny, maxx - minx, maxy - miny)
            return

        # Calculate pixel coordinates relative to image (offset by minx/miny)
        rel_x0 = x0 - minx
        rel_y0 = y0 - miny
        rel_x1 = x1 - minx
        rel_y1 = y1 - miny

        self._pixels = algorithms.bresenham(rel_x0, rel_y0, rel_x1, rel_y1)

        img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)  # We make sure its transparent

        # Creating painter object on our image
        qp = QPainter(img)
        try:
            qp.setPen(Qt.NoPen)
            qp.setBrush(QBrush(QColor("black")))
            # Drawing pixels into image with boundaries checking
            for px, py in self._pixels:
                if 0 <= px < width and 0 <= py < height:
                    qp.drawRect(px, py, 1, 1)
        finally:
            qp.end()

        # Converting image to pixmap and updating bounding rectangle
        self._pixmap = QPixmap.fromImage(img)
        self._pixmap_offset = QPointF(minx, miny)
        self._cached_bounding = QRectF(minx, miny, width, height)

    def paint(self, painter, option, widget):
        if self._pixmap:
            # Draw pixmap at precomputed offset (in parent local coordinates)
            painter.drawPixmap(self._pixmap_offset, self._pixmap)
            # Uncomment the following line to show that functionality is working
            print(f"[DEBUG] Painting Bresenham line with {len(self._pixels)} pixels")
            self._draw_constraint_icon(painter)

class BezierEdgeItem(EdgeItem):
    def __init__(self, edge: Bezier, parent):
        if edge.type != EdgeType.BEZIER:
            pass # Should implement raising an error
        super().__init__(edge, parent)
        self._pixels = []
        self._pixmap = None
        self._pixmap_offset = QPointF(0, 0)

        # path cache used only for shape() / hit-testing (kept up-to-date)
        self._path_cache = None

        self.control_handle_1 = ControlPointItem(edge.c1, parent=self)
        self.control_handle_2 = ControlPointItem(edge.c2, parent=self)
        
        # On init place handles to correct positions
        self._place_control_handles()
        self.update_edge()

    def convert_coords_to_parent(self):
        p0 = self.mapFromScene(QPointF(self.edge.v1.x, self.edge.v1.y))
        p1 = self.mapFromScene(QPointF(self.edge.c1.x, self.edge.c1.y))
        p2 = self.mapFromScene(QPointF(self.edge.c2.x, self.edge.c2.y))
        p3 = self.mapFromScene(QPointF(self.edge.v2.x, self.edge.v2.y))
        return (p0, p1, p2, p3)
    
    def _place_control_handles(self):
        # Convert scene coords to local parent coords and set position without
        # triggering callbacks
        self.updating_from_parent = True
        try:
            _, p1, p2, _ = self.convert_coords_to_parent()
            self.control_handle_1.setPos(p1)
            self.control_handle_2.setPos(p2)
        finally:
            self.updating_from_parent = False

    def on_control_moved(self, control_vertex: Vertex, new_scene_pos: QPointF):
        # update model control point (scene coords)
        control_vertex.x = new_scene_pos.x()
        control_vertex.y = new_scene_pos.y()
        # update caches / redraw
        self.update_edge()
        self.update()
    
    def update_edge(self):
        # Convert scene coords to local parent coords
        p0, p1, p2, p3 = self.convert_coords_to_parent()

        # Build control-polygon path and its bounding rect (local coords)
        control_path = QPainterPath()
        control_path.moveTo(p0)
        control_path.lineTo(p1)
        control_path.lineTo(p2)
        control_path.lineTo(p3)
        control_rect = control_path.boundingRect().adjusted(-2, -2, 2, 2)

        self._pixels = algorithms.bezier(p0, p1, p2, p3)

        # If no pixels, still need to update path cache and bounding (control polygon)
        if not self._pixels:
            new_bounding = control_rect
            self.prepareGeometryChange()
            self._pixmap = None
            self._pixmap_offset = QPointF(0, 0)
            self._cached_bounding = new_bounding
            self._path_cache = control_path
            self._place_control_handles()
            return

        # compute integer bounding box for pixels
        xs = [p[0] for p in self._pixels]
        ys = [p[1] for p in self._pixels]
        minx = min(xs) - 1
        miny = min(ys) - 1
        maxx = max(xs) + 1
        maxy = max(ys) + 1

        width = maxx - minx + 1
        height = maxy - miny + 1

        # Guard against excessive memory usage
        if width <= 0 or height <= 0 or width * height > 5_000_000:
            # don't rasterize, but still include control polygon in bounding
            new_bounding = control_rect.united(QRectF(minx, miny, max(0, width), max(0, height)))
            self.prepareGeometryChange()
            self._pixels = []
            self._pixmap = None
            self._cached_bounding = new_bounding
            self._path_cache = control_path
            self._place_control_handles()
            return

        # Compute final bounding as union of pixel bbox and control polygon bbox
        pix_rect = QRectF(minx, miny, width, height)
        new_bounding = control_rect.united(pix_rect)

        # Prepare for geometry change before updating cached geometry
        self.prepareGeometryChange()

        img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)

        qp = QPainter(img)
        try:
            qp.setPen(Qt.NoPen)
            qp.setBrush(QBrush(QColor("black")))
            for px, py in self._pixels:
                rx = px - minx
                ry = py - miny
                if 0 <= rx < width and 0 <= ry < height:
                    qp.drawRect(rx, ry, 1, 1)
        finally:
            qp.end()

        self._pixmap = QPixmap.fromImage(img)
        self._pixmap_offset = QPointF(minx, miny)
        self._cached_bounding = new_bounding
        self._path_cache = control_path

        # ensure control handles positioned correctly
        self._place_control_handles()

    def boundingRect(self):
        return self._cached_bounding
    
    def paint(self, painter, option, widget):
        # Draw control polygon (dashed)
        painter.setPen(QPen(QColor("gray"), 1, Qt.DashLine))
        p0, p1, p2, p3 = self.convert_coords_to_parent()
        painter.drawLine(p0, p1)
        painter.drawLine(p1, p2)
        painter.drawLine(p2, p3)

        # Draw bezier curve
        if self._pixmap:
            painter.drawPixmap(self._pixmap_offset, self._pixmap)

    def shape(self):
        """
        Provide a path used for hit-testing/selection. We return the control-polygon
        path (mapped to local coordinates) expanded slightly by the pixmap bounding rect.
        """
        # Ensure we always have a path cache
        # if getattr(self, "_path_cache", None) is not None:
        #     return self._path_cache
        # fallback: build transient path from current control points
        p0, p1, p2, p3 = self.convert_coords_to_parent()
        path = QPainterPath()
        path.moveTo(p0)
        path.lineTo(p1)
        path.lineTo(p2)
        path.lineTo(p3)
        self._path_cache = path
        return path

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