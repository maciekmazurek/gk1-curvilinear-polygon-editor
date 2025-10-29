from model import Bezier, EdgeType, Vertex
from graphics.control_point_item import ControlPointItem
from graphics.edge_item import EdgeItem
from PySide6.QtWidgets import QMenu
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

import algorithms

class BezierEdgeItem(EdgeItem):
    def __init__(self, edge: Bezier, parent):
        super().__init__(edge, parent)
        self._pixels = []
        self._pixmap = None
        self._pixmap_offset = QPointF(0, 0)

        self.updating_from_parent = False

        # Path cache used for shape()
        self._path_cache = None

        self.control_handle_1 = ControlPointItem(edge.c1, parent=self)
        self.control_handle_2 = ControlPointItem(edge.c2, parent=self)
        
        # On init place handles to correct positions
        self._place_control_handles()
        self.update_edge()

    def contextMenuEvent(self, event):
        # Only conversion back to Line is offered for Bezier edges
        menu = QMenu()
        to_line_action = menu.addAction("Convert to Line")

        # Converting screenPos from QPointF to QPoint so we can pass it to
        # menu.exec()
        sp = event.screenPos()
        try:
            qp = sp.toPoint()
        except Exception:
            qp = sp
        chosen = menu.exec(qp)

        if chosen == to_line_action:
            parent = self.parentItem()
            if parent:
                parent.convert_edge_to_line(self.edge)
        event.accept()

    def _convert_coords_to_parent(self):
        p0 = self.mapFromScene(QPointF(self.edge.v1.x, self.edge.v1.y))
        p1 = self.mapFromScene(QPointF(self.edge.c1.x, self.edge.c1.y))
        p2 = self.mapFromScene(QPointF(self.edge.c2.x, self.edge.c2.y))
        p3 = self.mapFromScene(QPointF(self.edge.v2.x, self.edge.v2.y))
        return (p0, p1, p2, p3)
    
    def _place_control_handles(self):
        # Place control handles at the correct positions
        self.updating_from_parent = True
        try:
            _, p1, p2, _ = self._convert_coords_to_parent()
            self.control_handle_1.setPos(p1)
            self.control_handle_2.setPos(p2)
        finally:
            self.updating_from_parent = False

    def on_control_moved(self, control_point: Vertex, new_scene_pos: QPointF):
        # Update control point position
        control_point.x = new_scene_pos.x()
        control_point.y = new_scene_pos.y()

        # Update caches / redraw
        self.update_edge()
        self.update()

        parent = self.parentItem()
        if parent:
            # Inform parent which control point moved so the moved handle 
            # remains the driver
            if control_point is self.edge.c1:
                parent.enforce_vertex_continuity_from_control(self.edge.v1, moved_control='next')
            elif control_point is self.edge.c2:
                parent.enforce_vertex_continuity_from_control(self.edge.v2, moved_control='prev')
            for e_item in parent.edge_items:
                    e_item.update_edge()
            parent.update()
    
    def update_edge(self):
        # Convert scene coords to local parent coords
        p0, p1, p2, p3 = self._convert_coords_to_parent()

        # Build control-polygon path and its bounding rect
        control_path = QPainterPath()
        control_path.moveTo(p0)
        control_path.lineTo(p1)
        control_path.lineTo(p2)
        control_path.lineTo(p3)
        control_rect = control_path.boundingRect().adjusted(-2, -2, 2, 2)

        self._pixels = algorithms.bezier(p0, p1, p2, p3)

        # If no pixels, still need to update path cache and bounding (control polygon)
        if not self._pixels:
            new_bounding = control_rect
            self.prepareGeometryChange()
            self._pixmap = None
            self._pixmap_offset = QPointF(0, 0)
            self._cached_bounding = new_bounding
            self._path_cache = control_path
            self._place_control_handles()
            return

        # compute integer bounding box for pixels
        x_vals = [p[0] for p in self._pixels]
        y_vals = [p[1] for p in self._pixels]
        minx = min(x_vals) - 1
        miny = min(y_vals) - 1
        maxx = max(x_vals) + 1
        maxy = max(y_vals) + 1

        width = maxx - minx + 1
        height = maxy - miny + 1

        # Guard against excessive memory usage
        if width <= 0 or height <= 0 or width * height > 5_000_000:
            # don't rasterize, but still include control polygon in bounding
            new_bounding = control_rect.united(QRectF(minx, miny, max(0, width), max(0, height)))
            self.prepareGeometryChange()
            self._pixels = []
            self._pixmap = None
            self._cached_bounding = new_bounding
            self._path_cache = control_path
            self._place_control_handles()
            return

        # Compute final bounding as union of pixel bounding box and control 
        # polygon bounding box
        pix_rect = QRectF(minx, miny, width, height)
        new_bounding = control_rect.united(pix_rect)

        # Prepare for geometry change before updating cached geometry
        self.prepareGeometryChange()

        img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)

        qp = QPainter(img)
        try:
            qp.setPen(Qt.NoPen)
            qp.setBrush(QBrush(QColor("black")))
            for px, py in self._pixels:
                rx = px - minx
                ry = py - miny
                if 0 <= rx < width and 0 <= ry < height:
                    qp.drawRect(rx, ry, 1, 1)
        finally:
            qp.end()

        self._pixmap = QPixmap.fromImage(img)
        self._pixmap_offset = QPointF(minx, miny)
        self._cached_bounding = new_bounding
        self._path_cache = control_path

        # ensure control handles positioned correctly
        self._place_control_handles()

    def boundingRect(self):
        return self._cached_bounding
    
    def paint(self, painter, option, widget):
        # Draw control polygon (dashed)
        painter.setPen(QPen(QColor("gray"), 1, Qt.DashLine))
        p0, p1, p2, p3 = self._convert_coords_to_parent()
        painter.drawLine(p0, p1)
        painter.drawLine(p1, p2)
        painter.drawLine(p2, p3)

        # Draw bezier curve
        if self._pixmap:
            painter.drawPixmap(self._pixmap_offset, self._pixmap)

    def shape(self):
        p0, p1, p2, p3 = self._convert_coords_to_parent()
        path = QPainterPath()
        path.moveTo(p0)
        path.lineTo(p1)
        path.lineTo(p2)
        path.lineTo(p3)
        self._path_cache = path
        return path