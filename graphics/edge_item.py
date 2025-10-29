from model import Edge
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtGui import QPainterPath
from PySide6.QtCore import QRectF

# Base class for edge items (StandardLineEdgeItem, BresenhamLineEdgeItem, 
# BezierEdgeItem, ArcEdgeItem)
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