from model import *
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
)

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