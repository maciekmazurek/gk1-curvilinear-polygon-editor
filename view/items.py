from model.model import Bezier, Vertex, Edge, Polygon
from config import *
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
)
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
from model.model import LineDrawingMode, EdgeType

import math

class VertexItem(QGraphicsEllipseItem):
    def __init__(self, vertex : Vertex, parent=None):
        # We call the constructor of the base class to create an ellipse item
        super().__init__(-vertex.radius, -vertex.radius, 
                         vertex.radius*2, vertex.radius*2, parent)
        self.vertex = vertex
        self.setBrush(QBrush(QColor("black")))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True)
        # Setting Z value to be on top of edges
        self.setZValue(2.0)

    # Virtual method which intercepts changes of the item state
    def itemChange(self, change : QGraphicsItem.GraphicsItemChange, value):
        # If position of the vertex has changed
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.parentItem():
            parent = self.parentItem()
            # We dont inform parent if the position change was caused by parent
            # itself (to avoid infinite loops) - we only inform parent when
            # the user drags the vertex directly 
            if not parent.updating_from_parent:
                vertex_new_scene_coords = parent.mapToScene(value)
                parent.on_vertex_moved(self.vertex, vertex_new_scene_coords)
        return super().itemChange(change, value)
    
class ControlPointItem(QGraphicsEllipseItem):
    def __init__(self, vertex: Vertex, parent=None, color="orange"):
        super().__init__(-vertex.radius/1.2, -vertex.radius/1.2,
                         vertex.radius*2/1.2, vertex.radius*2/1.2, parent)
        self.vertex = vertex
        self.setBrush(QBrush(QColor(color)))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True)
        # Setting Z value to be above vertices and edges
        self.setZValue(3.0)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.parentItem():
            parent = self.parentItem()
            if not parent.updating_from_parent:
                control_new_scene_coords = parent.mapToScene(value)
                parent.on_control_moved(self.vertex, control_new_scene_coords)
        return super().itemChange(change, value)
    
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

    def convert_coords_to_parent(self):
        p1 = self.parentItem().mapFromScene(QPointF(self.edge.v1.x, self.edge.v1.y))
        p2 = self.parentItem().mapFromScene(QPointF(self.edge.v2.x, self.edge.v2.y))
        return (p1, p2)

# Rysowany za pomocą interfejsu udostępnianego przez QGraphics
class StandardLineEdgeItem(LineEdgeItem):
    def __init__(self, edge: Edge, parent):
        super().__init__(edge, parent)

    def update_edge(self):
        p1, p2 = self.convert_coords_to_parent()
        self.prepareGeometryChange()
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

# Rysowany za pomocą własnej implementacji algorytmu Bresenhama
class BresenhamLineEdgeItem(LineEdgeItem):
    def __init__(self, edge: Edge, parent):
        super().__init__(edge, parent)
        self._pixels = []
        self._pixmap = None
        self._pixmap_offset = QPointF(0, 0)

    def _calculate_bresenham(self, x0: int, y0: int, x1: int, y1: int):
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

    def boundingRect(self):
        return self._cached_bounding

    def update_edge(self):
        self.prepareGeometryChange()

        p1, p2 = self.convert_coords_to_parent()
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

        # If degenerate, clear cache
        if width <= 0 or height <= 0:
            self._pixmap = None
            self._cached_bounding = QRectF(0, 0, 0, 0)
            return

        # Calculate pixel coordinates relative to image (offset by minx/miny)
        rel_x0 = x0 - minx
        rel_y0 = y0 - miny
        rel_x1 = x1 - minx
        rel_y1 = y1 - miny

        self._pixels = self._calculate_bresenham(rel_x0, rel_y0, rel_x1, rel_y1)

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
    
class BezierEdgeItem(EdgeItem):
    def __init__(self, edge: Bezier, parent):
        if edge.type != EdgeType.BEZIER:
            pass # Should implement raising an error
        super().__init__(edge, parent)
        self._pixmap = None      # optional pixel cache for pixel mode
        self._pixmap_offset = QPointF(0, 0)

        # path cache used only for shape() / hit-testing (kept up-to-date)
        self._path_cache = None

        self.control_handle_1 = ControlPointItem(edge.c1, parent=self)
        self.control_handle_2 = ControlPointItem(edge.c2, parent=self)
        
        # On init place handles to correct positions
        self._place_control_handles()
        self.update_edge()

    def _place_control_handles(self):
        # map model (scene coords) to local parent coords and set pos without triggering callbacks
        self.updating_from_parent = True
        try:
            p1 = self.mapFromScene(QPointF(self.edge.c1.x, self.edge.c1.y))
            p2 = self.mapFromScene(QPointF(self.edge.c2.x, self.edge.c2.y))
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

    def _distance(self, p1: QPointF, p2: QPointF) -> float:
        return math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
    
    def update_edge(self):
        # Convert control points to local (parent) coordinates for rasterization
        p0 = self.mapFromScene(QPointF(self.edge.v1.x, self.edge.v1.y))
        p1 = self.mapFromScene(QPointF(self.edge.c1.x, self.edge.c1.y))
        p2 = self.mapFromScene(QPointF(self.edge.c2.x, self.edge.c2.y))
        p3 = self.mapFromScene(QPointF(self.edge.v2.x, self.edge.v2.y))

        # Build control-polygon path and its bounding rect (local coords)
        control_path = QPainterPath()
        control_path.moveTo(p0)
        control_path.lineTo(p1)
        control_path.lineTo(p2)
        control_path.lineTo(p3)
        control_rect = control_path.boundingRect().adjusted(-2, -2, 2, 2)

        # Estimate sampling density from control polygon length
        est_len = (self._distance(p0, p1) + self._distance(p1, p2) + self._distance(p2, p3))
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

        # If no pixels, still need to update path cache and bounding (control polygon)
        if not pixels:
            new_bounding = control_rect
            self.prepareGeometryChange()
            self._pixmap = None
            self._pixmap_offset = QPointF(0, 0)
            self._cached_bounding = new_bounding
            self._path_cache = control_path
            self._place_control_handles()
            return

        # compute integer bounding box for pixels
        xs = [p[0] for p in pixels]
        ys = [p[1] for p in pixels]
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
            self._pixmap = None
            self._cached_bounding = new_bounding
            self._path_cache = control_path
            self._place_control_handles()
            return

        # Compute final bounding as union of pixel bbox and control polygon bbox
        pix_rect = QRectF(minx, miny, width, height)
        new_bounding = control_rect.united(pix_rect)

        # prepare for geometry change BEFORE updating cached geometry
        self.prepareGeometryChange()

        # create image and rasterize pixels relative to minx/miny
        img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)

        qp = QPainter(img)
        try:
            qp.setPen(Qt.NoPen)
            qp.setBrush(QBrush(QColor("black")))
            for px, py in pixels:
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
        p0 = self.mapFromScene(QPointF(self.edge.v1.x, self.edge.v1.y))
        p1 = self.mapFromScene(QPointF(self.edge.c1.x, self.edge.c1.y))
        p2 = self.mapFromScene(QPointF(self.edge.c2.x, self.edge.c2.y))
        p3 = self.mapFromScene(QPointF(self.edge.v2.x, self.edge.v2.y))
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
        p0 = self.mapFromScene(QPointF(self.edge.v1.x, self.edge.v1.y))
        p1 = self.mapFromScene(QPointF(self.edge.c1.x, self.edge.c1.y))
        p2 = self.mapFromScene(QPointF(self.edge.c2.x, self.edge.c2.y))
        p3 = self.mapFromScene(QPointF(self.edge.v2.x, self.edge.v2.y))
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

        self.vertex_items = {}
        self.edge_items = []

        self._setup_children()

    def boundingRect(self):
        if not self.polygon.vertices:
            return QRectF(0, 0, 0, 0)
        minx = min(v.x for v in self.polygon.vertices)
        miny = min(v.y for v in self.polygon.vertices)
        maxx = max(v.x for v in self.polygon.vertices)
        maxy = max(v.y for v in self.polygon.vertices)

        top_left = self.mapFromScene(QPointF(minx, miny))
        bottom_right = self.mapFromScene(QPointF(maxx, maxy))

        return QRectF(top_left, bottom_right).normalized()

    def shape(self):
        path = QPainterPath()
        if not self.polygon.vertices:
            return path
        pts = [self.mapFromScene(QPointF(v.x, v.y)) for v in self.polygon.vertices]
        path.moveTo(pts[0])
        for p in pts[1:]:
            path.lineTo(p)
        path.closeSubpath()
        return path
    
    def paint(self, painter, option, widget):
        path = self.shape()
        if path.isEmpty():
            return
        painter.setPen(QPen(QColor("black")))
        painter.drawPath(path)

    def _setup_children(self):
        self.updating_from_parent = True
        try:
            # Setting up vertices
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

        # Setting up edges
        for e in self.polygon.edges:
            e_item = self.Factory(e, parent=self)
            self.edge_items.append(e_item)
            e_item.update_edge()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start_scene = event.scenePos()
            self._original_vertices_positions = [(v, v.x, v.y) for v in self.polygon.vertices]
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.scenePos() - self._drag_start_scene
            dx, dy = delta.x(), delta.y()

            for v, ox, oy in self._original_vertices_positions:
                v.x = ox + dx
                v.y = oy + dy

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
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def Factory(self, edge: Edge, parent):
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

        # PRZEIMPLEMENTOWAĆ W TAKI SPOSÓB, ŻEBY ODPOWIEDNIO MODYFIKOWAĆ
        # KRAWĘDZIE GDY PRZESUWANE SĄ DANE WIERZCHOŁKI
        for e_item in self.edge_items:
            if e_item.edge.v1 is vertex or e_item.edge.v2 is vertex:
                e_item.update_edge()

        self.update()
    
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
            e_item = self.Factory(e, parent=self)
            self.edge_items.append(e_item)
            # Redrawing
            e_item.update_edge()

        self.update()