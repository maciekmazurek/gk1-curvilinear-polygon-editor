from model import Vertex, ContinuityType
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QMenu,
    QMessageBox,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
)

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

    def contextMenuEvent(self, event):
        menu = QMenu()
        del_action = menu.addAction("Delete vertex")
        set_g0_action = menu.addAction("Set continuity: G0")
        set_g1_action = menu.addAction("Set continuity: G1")
        set_c1_action = menu.addAction("Set continuity: C1")
        sp = event.screenPos()
        try:
            qp = sp.toPoint()
        except Exception:
            qp = sp
        chosen_action = menu.exec(qp)
        if chosen_action == del_action:
            parent = self.parentItem()
            if parent:
                parent.delete_vertex(self.vertex)
        elif chosen_action in (set_g0_action, set_g1_action, set_c1_action):
            parent = self.parentItem()
            if parent:
                if chosen_action is set_g0_action:
                    ok = parent.apply_continuity_to_vertex(self.vertex, ContinuityType.G0)
                elif chosen_action is set_g1_action:
                    ok = parent.apply_continuity_to_vertex(self.vertex, ContinuityType.G1)
                else:
                    ok = parent.apply_continuity_to_vertex(self.vertex, ContinuityType.C1)
                if not ok:
                    QMessageBox.warning(None, "Continuity", "Continuity can only be set if at least one adjacent edge is Bezier.")
        event.accept()