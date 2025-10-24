from model.model import Vertex, Edge, Polygon
from config import *
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, 
    QGraphicsItem, 
    QGraphicsLineItem,
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
    
class EdgeItem(QGraphicsLineItem):
    # Default line drawing mode
    line_drawing_mode = LineDrawingMode.QGRAPHICS

    def __init__(self, edge: Edge, parent):
        super().__init__(parent)
        self.edge = edge
        # Setting Z value to be below vertices
        self.setZValue(1.0)

    def convert_coords_to_parent(self):
        p1 = self.parentItem().mapFromScene(QPointF(self.edge.v1.x, 
                                                    self.edge.v1.y))
        p2 = self.parentItem().mapFromScene(QPointF(self.edge.v2.x, 
                                                    self.edge.v2.y))
        return (p1, p2)

    def Factory(edge: Edge, parent):
        if edge.type == EdgeType.LINE:
            if EdgeItem.line_drawing_mode == LineDrawingMode.QGRAPHICS:
                return StandardLineEdgeItem(edge, parent)
            elif EdgeItem.line_drawing_mode == LineDrawingMode.BRESENHAM:
                return BresenhamLineEdgeItem(edge, parent)
        # Other edge types (BEZIER, ARC) will be handled here in the future

# Rysowany za pomocą interfejsu udostępnianego przez QGraphics
class StandardLineEdgeItem(EdgeItem):
    def __init__(self, edge: Edge, parent):
        super().__init__(edge, parent)

    def update_edge(self):
        p1, p2 = self.convert_coords_to_parent()
        self.setLine(p1.x(), p1.y(), p2.x(), p2.y())

# Rysowany za pomocą własnej implementacji algorytmu Bresenhama
class BresenhamLineEdgeItem(EdgeItem):
    def __init__(self, edge: Edge, parent):
        super().__init__(edge, parent)
        self._line_pixels = []
        self._pixmap = None
        self._pixmap_offset = QPointF(0, 0)
        self._cached_bounding_rect = QRectF(0, 0, 0, 0)

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
        return self._cached_bounding_rect

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
            self._cached_bounding_rect = QRectF(0, 0, 0, 0)
            return

        # Calculate pixel coordinates relative to image (offset by minx/miny)
        rel_x0 = x0 - minx
        rel_y0 = y0 - miny
        rel_x1 = x1 - minx
        rel_y1 = y1 - miny

        self._line_pixels = self._calculate_bresenham(rel_x0, rel_y0, rel_x1, rel_y1)

        img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)  # We make sure its transparent

        # Creating painter object on our image
        qp = QPainter(img)
        try:
            qp.setPen(Qt.NoPen)
            qp.setBrush(QBrush(QColor("black")))
            # Drawing pixels into image with boundaries checking
            for px, py in self._line_pixels:
                if 0 <= px < width and 0 <= py < height:
                    qp.drawRect(px, py, 1, 1)
        finally:
            qp.end()

        # Converting image to pixmap and updating bounding rectangle
        self._pixmap = QPixmap.fromImage(img)
        self._pixmap_offset = QPointF(minx, miny)
        self._cached_bounding_rect = QRectF(minx, miny, width, height)

    def paint(self, painter, option, widget):
        if self._pixmap:
            # Draw pixmap at precomputed offset (in parent local coordinates)
            painter.drawPixmap(self._pixmap_offset, self._pixmap)
            # Uncomment the following line to show that functionality is working
            print(f"[DEBUG] Painting Bresenham line with {len(self._line_pixels)} pixels")
    
class PolygonItem(QGraphicsItem):
    def __init__(self, polygon: Polygon):
        super().__init__()
        self.polygon = polygon
        # We disable QGraphics Framework's built-in moving mechanism
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

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

    # Abstract method from QGraphicsItem that must be implemented
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
            e_item = EdgeItem.Factory(e, parent=self)
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

    # Method called by VertexItem when user directly drags a single vertex
    def on_vertex_moved(self, vertex: Vertex, vertex_new_scene_coords: QPointF):
        vertex.x = vertex_new_scene_coords.x()
        vertex.y = vertex_new_scene_coords.y()

        for e_item in self.edge_items:
            if e_item.edge.v1 is vertex or e_item.edge.v2 is vertex:
                e_item.update_edge()

        self.update()
    
    # Method called by MainWindow when line drawing mode is changed
    def redraw_with_new_mode(self, mode: LineDrawingMode):
        # Update line drawing mode
        EdgeItem.line_drawing_mode = mode

        # Remove old edge items
        for e_item in self.edge_items:
            e_item.setParentItem(None)
            scene = self.scene()
            if scene:
                scene.removeItem(e_item)
        self.edge_items.clear()

        # Create new edge items according to new drawing mode
        for e in self.polygon.edges:
            e_item = EdgeItem.Factory(e, parent=self)
            self.edge_items.append(e_item)
            # Redrawing
            e_item.update_edge()

        self.update()