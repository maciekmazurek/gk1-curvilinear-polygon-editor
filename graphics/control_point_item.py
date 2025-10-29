from model import Vertex
from config import VERTEX_DIAMETER
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
)

class ControlPointItem(QGraphicsEllipseItem):
    def __init__(self, vertex: Vertex, parent=None, color=QColor(228, 168, 197)):
        super().__init__(-VERTEX_DIAMETER/2.4, -VERTEX_DIAMETER/2.4,
                         VERTEX_DIAMETER/1.2, VERTEX_DIAMETER/1.2, parent)
        self.vertex = vertex
        self.setBrush(QBrush(color))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True)
        # Setting Z value to be above vertices and edges
        self.setZValue(3.0)

    # Virtual method which intercepts changes of the item state
    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.parentItem():
            parent = self.parentItem()
            # We dont inform parent if the position change was caused by parent
            # itself (to avoid infinite loops) - we only inform parent when
            # user drags the control point directly 
            if not parent.updating_from_parent:
                control_new_scene_coords = parent.mapToScene(value)
                parent.on_control_moved(self.vertex, control_new_scene_coords)
        return super().itemChange(change, value)