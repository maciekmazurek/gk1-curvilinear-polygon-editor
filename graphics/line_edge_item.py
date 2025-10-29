from model import Edge, EdgeType, ConstraintType
from graphics.edge_item import EdgeItem
from PySide6.QtWidgets import (
    QMenu,
    QInputDialog,
    QMessageBox,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QImage,
    QPixmap,
    QPainter
)
from PySide6.QtCore import QPointF, QRectF, Qt

import algorithms

# Base class for line edge items (StandardLineEdgeItem, BresenhamLineEdgeItem)
class LineEdgeItem(EdgeItem):
    def __init__(self, edge: Edge, parent):
        super().__init__(edge, parent)
        self._cached_bounding = QRectF(0, 0, 0, 0)
        self._p1 = QPointF()
        self._p2 = QPointF()

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)

    def _convert_coords_to_parent(self):
        p1 = self.parentItem().mapFromScene(QPointF(self.edge.v1.x, self.edge.v1.y))
        p2 = self.parentItem().mapFromScene(QPointF(self.edge.v2.x, self.edge.v2.y))
        return (p1, p2)
    
    def contextMenuEvent(self, event):
        menu = QMenu()
        add_vertex_action = menu.addAction("Add new vertex")
        menu.addSeparator()
        set_vertical_action = menu.addAction("Set constraint: Vertical")
        set_45_action = menu.addAction("Set constraint: 45°")
        set_length_action = menu.addAction("Set constraint: Fixed length...")
        clear_constraint_action = menu.addAction("Clear constraint")
        menu.addSeparator()
        to_bezier_action = menu.addAction("Convert to Bezier")
        to_arc_action = menu.addAction("Convert to Arc")

        # Converting screenPos from QPointF to QPoint so we can pass it to
        # menu.exec()
        sp = event.screenPos()
        try:
            qp = sp.toPoint()
        except Exception:
            qp = sp
        chosen_action = menu.exec(qp)

        parent = self.parentItem()
        if parent:
            if chosen_action == add_vertex_action:
                parent.add_vertex_on_edge(self.edge)
            elif chosen_action == set_vertical_action:
                ok = parent.apply_constraint_to_edge(self.edge, ConstraintType.VERTICAL)
                if not ok:
                    QMessageBox.warning(None, "Constraint", "Cannot set vertical constraint: adjacent edge is already vertical.")
            elif chosen_action == set_45_action:
                parent.apply_constraint_to_edge(self.edge, ConstraintType.DIAGONAL_45)
            elif chosen_action == set_length_action:
                # Ask user for desired length
                current_len = ((self.edge.v1.x - self.edge.v2.x)**2 + (self.edge.v1.y - self.edge.v2.y)**2) ** 0.5
                val, ok = QInputDialog.getDouble(None, "Fixed length", "Length:", current_len, 0.0, 1e6, 2)
                if ok:
                    parent.apply_constraint_to_edge(self.edge, ConstraintType.FIXED_LENGTH, val)
            elif chosen_action == clear_constraint_action:
                parent.apply_constraint_to_edge(self.edge, ConstraintType.NONE, None)
            elif chosen_action == to_bezier_action:
                parent.convert_edge_to_bezier(self.edge)
            elif chosen_action == to_arc_action:
                parent.convert_edge_to_arc(self.edge)
        event.accept()

    def _draw_constraint_icon(self, painter):
        ct = getattr(self.edge, "constraint_type", ConstraintType.NONE)
        if ct == ConstraintType.NONE:
            return
        mid = QPointF((self._p1.x() + self._p2.x()) / 2.0, (self._p1.y() + self._p2.y()) / 2.0)
        painter.save()
        painter.setPen(QPen(QColor("black")))
        if ct == ConstraintType.VERTICAL:
            painter.setBrush(QBrush(QColor("red")))
            painter.drawEllipse(mid, 6, 6)
            painter.setPen(QPen(QColor("white")))
            painter.drawText(QRectF(mid.x()-6, mid.y()-6, 12, 12), Qt.AlignCenter, "V")
        elif ct == ConstraintType.DIAGONAL_45:
            painter.setBrush(QBrush(QColor("green")))
            painter.drawEllipse(mid, 6, 6)
            painter.setPen(QPen(QColor("white")))
            painter.drawText(QRectF(mid.x()-6, mid.y()-6, 12, 12), Qt.AlignCenter, "45")
        elif ct == ConstraintType.FIXED_LENGTH:
            painter.setBrush(QBrush(QColor("blue")))
            painter.drawEllipse(mid, 6, 6)
            painter.setPen(QPen(QColor("white")))
            val = self.edge.constraint_value
            if val is None:
                s = "?"
            else:
                s = f"{val:.0f}"
            painter.drawText(QRectF(mid.x()-8, mid.y()-8, 16, 16), Qt.AlignCenter, s)
        painter.restore()

    def shape(self):
        # Provide a stroked path so mouse events (clicks/right-clicks) hit the line
        path = QPainterPath()
        path.moveTo(self._p1)
        path.lineTo(self._p2)
        stroker = QPainterPathStroker()
        stroker.setWidth(6.0)  # clickable tolerance in parent-local coordinates
        return stroker.createStroke(path)

# Line drawn using standard QGraphics library algorithm
class StandardLineEdgeItem(LineEdgeItem):
    def __init__(self, edge: Edge, parent):
        super().__init__(edge, parent)

    def update_edge(self):
        self.prepareGeometryChange()
        p1, p2 = self._convert_coords_to_parent()
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
        # Draw line
        painter.drawLine(self._p1, self._p2)
        self._draw_constraint_icon(painter)

# Line drawn using Bresenham's algorithm
class BresenhamLineEdgeItem(LineEdgeItem):
    def __init__(self, edge: Edge, parent):
        super().__init__(edge, parent)
        self._pixels = []
        self._pixmap = None
        self._pixmap_offset = QPointF(0, 0)

    def boundingRect(self):
        return self._cached_bounding

    def update_edge(self):
        self.prepareGeometryChange()
        p1, p2 = self._convert_coords_to_parent()
        self._p1, self._p2 = p1, p2

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

        if width <= 0 or height <= 0:
            self._pixmap = None
            minx = min(p1.x(), p2.x()) - 1
            miny = min(p1.y(), p2.y()) - 1
            maxx = max(p1.x(), p2.x()) + 1
            maxy = max(p1.y(), p2.y()) + 1
            self._cached_bounding = QRectF(minx, miny, maxx - minx, maxy - miny)
            return

        # Calculate pixel coordinates relative to image (offset by minx/miny)
        rel_x0 = x0 - minx
        rel_y0 = y0 - miny
        rel_x1 = x1 - minx
        rel_y1 = y1 - miny

        self._pixels = algorithms.bresenham(rel_x0, rel_y0, rel_x1, rel_y1)

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
            # Draw line
            painter.drawPixmap(self._pixmap_offset, self._pixmap)
            # Uncomment the following line to show that functionality is working
            # print(f"[DEBUG] Painting Bresenham line with {len(self._pixels)} pixels")
            self._draw_constraint_icon(painter)