from model import Vertex, ContinuityType, EdgeType
from config import VERTEX_DIAMETER
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

# Represent vertex of a polygon as a movable ellipse item
class VertexItem(QGraphicsEllipseItem):
    def __init__(self, vertex : Vertex, parent=None):
        # We call the constructor of the base class to create an ellipse item
        super().__init__(-VERTEX_DIAMETER/2, -VERTEX_DIAMETER/2, 
                         VERTEX_DIAMETER, VERTEX_DIAMETER, parent)
        self.vertex = vertex
        self.setBrush(QBrush(QColor("black")))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges, True)
        # Setting Z value to be on top of edges
        self.setZValue(2.0)

    # Virtual method which intercepts changes of the item state
    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        # If position of the vertex has changed
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.parentItem():
            parent = self.parentItem() # PolygonItem
            # We dont inform parent if the position change was caused by parent
            # itself (to avoid infinite loops) - we only inform parent when
            # the user drags the vertex directly 
            if not parent.updating_from_parent:
                vertex_new_scene_coords = parent.mapToScene(value)
                parent.on_vertex_moved(self.vertex, vertex_new_scene_coords)
        return super().itemChange(change, value)

    # Method to handle right-click context menu on the vertex
    def contextMenuEvent(self, event):
        menu = QMenu()
        del_action = menu.addAction("Delete vertex")
        menu.addSeparator()

        # Determine allowed continuity options based on adjacent edge types
        parent = self.parentItem()
        allowed = {"G0": False, "G1": False, "C1": False}
        prev_edge, _, next_edge, _ = parent.adjacent_edges_of_vertex(self.vertex)
        if prev_edge is not None and next_edge is not None:
            prev_type = prev_edge.type
            next_type = next_edge.type
            has_bezier = (prev_type == EdgeType.BEZIER) or (next_type == EdgeType.BEZIER)
            has_arc = (prev_type == EdgeType.ARC) or (next_type == EdgeType.ARC)
            has_line_only = (prev_type == EdgeType.LINE) and (next_type == EdgeType.LINE)
            if not has_line_only:
                # G0 always allowed when at least one adjacent edge is Bezier or Arc
                allowed["G0"] = True
                if has_arc:
                    # Any arc involved: allow G1 only (no C1 for arcs)
                    allowed["G1"] = True
                elif has_bezier:
                    # Bezier-bezier or bezier-line: allow G1 and C1
                    allowed["G1"] = True
                    allowed["C1"] = True

        set_g0_action = set_g1_action = set_c1_action = None
        if allowed["G0"]:
            set_g0_action = menu.addAction("Set continuity: G0")
        if allowed["G1"]:
            set_g1_action = menu.addAction("Set continuity: G1")
        if allowed["C1"]:
            set_c1_action = menu.addAction("Set continuity: C1")

        # Map created actions to their continuity types for robust handling
        continuity_map = {}
        if set_g0_action is not None:
            continuity_map[set_g0_action] = ContinuityType.G0
        if set_g1_action is not None:
            continuity_map[set_g1_action] = ContinuityType.G1
        if set_c1_action is not None:
            continuity_map[set_c1_action] = ContinuityType.C1

        sp = event.screenPos()
        try:
            qp = sp.toPoint()
        except Exception:
            qp = sp
        chosen_action = menu.exec(qp)

        # If user dismissed the menu (clicked outside or pressed Esc), do nothing
        if chosen_action is None:
            event.accept()
            return

        parent = self.parentItem()
        if parent:
            if chosen_action == del_action:
                parent.delete_vertex(self.vertex)
            elif chosen_action in continuity_map:
                cont = continuity_map[chosen_action]
                ok = parent.apply_continuity_to_vertex(self.vertex, cont)
                if not ok:
                    # Prefer specific warning prepared by parent (e.g., Arc both-ends G1)
                    custom = getattr(parent, "last_continuity_warning", None)
                    if custom:
                        QMessageBox.warning(None, "Ciągłość", custom)
                        parent.last_continuity_warning = None
                    else:
                        QMessageBox.warning(
                            None,
                            "Ciągłość",
                            (
                                "Ciągłość można ustawić tylko dla wierzchołków sąsiadujących z krzywą Beziera lub łukiem.\n"
                                "Dla łuków dozwolone są tylko G0 i G1."
                            ),
                        )
        event.accept()