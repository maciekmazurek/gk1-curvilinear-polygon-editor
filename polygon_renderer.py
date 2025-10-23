from model import Polygon, PolygonItem
from PySide6.QtWidgets import QGraphicsScene

class PolygonRenderer:
    def __init__(self, scene: QGraphicsScene):
        self.scene = scene

    def render(self) -> None:
        self.scene.clear()
        polygon = Polygon()
        polygon_item = PolygonItem(polygon)
        # We set position of the polygon (parent) to (0, 0) in scene coordinates
        # because vertices (children) are initialized with coordinates
        # relative to the scene
        polygon_item.setPos(0, 0)
        self.scene.addItem(polygon_item)
