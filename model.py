from enum import Enum
from config import *
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, 
    QGraphicsItem, 
    QGraphicsLineItem,
)
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtCore import QPointF, QRectF, Qt

class EdgeType(Enum):
    LINE = 1
    BEZIER = 2
    ARC = 3

class Vertex:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
        self.radius = VERTEX_DIAMETER / 2

class Edge:
    def __init__(self, v1: Vertex, v2: Vertex, type: EdgeType):
        self.v1 = v1
        self.v2 = v2
        self.type = type

class Polygon:
    def __init__(self):
        self.vertices = [Vertex(1, 4), Vertex(50, -10), Vertex(200, 40)]
        self.edges = []
        for i in range(len(self.vertices)):
            self.edges.append(Edge(self.vertices[i % 3], 
                                   self.vertices[(i + 1) % 3], 
                                   EdgeType.LINE))
            
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
    def __init__(self, edge: Edge, parent):
        super().__init__(parent)
        self.edge = edge
        # Setting Z value to be below vertices
        self.setZValue(1.0)

    def update_edge(self):
        # We convert vertex positions from scene coordinates to parent 
        # (PolygonItem) coordinates
        p1 = self.parentItem().mapFromScene(QPointF(self.edge.v1.x, 
                                                    self.edge.v1.y))
        p2 = self.parentItem().mapFromScene(QPointF(self.edge.v2.x, 
                                                    self.edge.v2.y))
        # Updating the edge position relative to the parent coordinates
        self.setLine(p1.x(), p1.y(), p2.x(), p2.y())

class PolygonItem(QGraphicsItem):
    def __init__(self, polygon: Polygon):
        super().__init__()
        self.polygon = polygon
        # We disable QGraphics Framework's built-in moving mechanism
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        # Flag indicating whether the position of vertices is updated by the 
        # parent object
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
            e_item = EdgeItem(e, parent=self)
            e_item.update_edge()
            self.edge_items.append(e_item)

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