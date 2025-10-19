from model import Polygon
from PySide6.QtWidgets import QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem
from PySide6.QtGui import QBrush, QColor
from config import *

class PolygonRenderer:
    def __init__(self, scene: QGraphicsScene):
        self.scene = scene

    def render(self, polygon: Polygon) -> None:
        radius = VERTEX_DIAMETER / 2
        for v in polygon.vertices:
            ellipse = QGraphicsEllipseItem(-radius, -radius, VERTEX_DIAMETER, VERTEX_DIAMETER)
            ellipse.setPos(v.x, v.y)
            ellipse.setBrush(QBrush(QColor("black")))
            self.scene.addItem(ellipse)

        for e in polygon.edges:
            line = QGraphicsLineItem(e.v1.x, e.v1.y, e.v2.x, e.v2.y)
            self.scene.addItem(line)
