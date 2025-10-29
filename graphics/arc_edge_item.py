from model import Arc, EdgeType
from graphics.edge_item import EdgeItem
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainterPath,
    QImage,
    QPixmap,
    QPainter
)
from PySide6.QtCore import QPointF, QRectF, Qt

import math
from geometry import compute_arc_geometry_for_edge

class ArcEdgeItem(EdgeItem):
    def __init__(self, edge: Arc, parent):
        if edge.type != EdgeType.ARC:
            pass  # could raise
        super().__init__(edge, parent)
        self._pixels = []
        self._pixmap = None
        self._pixmap_offset = QPointF(0, 0)
        self._cached_bounding = QRectF(0, 0, 0, 0)

        # path cache used for hit-testing/selection
        self._path_cache = None

        self.update_edge()

    def contextMenuEvent(self, event):
        # Only conversion back to Line is offered for Arc edges
        menu = QMenu()
        to_line_action = menu.addAction("Convert to Line")
        sp = event.screenPos()
        try:
            qp = sp.toPoint()
        except Exception:
            qp = sp
        chosen = menu.exec(qp)
        if chosen == to_line_action:
            parent = self.parentItem()
            if parent:
                parent.convert_edge(self.edge, EdgeType.LINE)
        event.accept()

    def convert_coords_to_parent(self):
        p0 = self.mapFromScene(QPointF(self.edge.v1.x, self.edge.v1.y))
        p3 = self.mapFromScene(QPointF(self.edge.v2.x, self.edge.v2.y))
        return (p0, p3)
        
    def update_edge(self):
        # scene geometry via shared helper
        parent = self.parentItem()
        edges = getattr(getattr(parent, 'polygon', None), 'edges', None)
        if not edges:
            # fallback: nothing to draw; keep tiny bbox around chord
            p0, p3 = self.convert_coords_to_parent()
            path = QPainterPath()
            path.moveTo(p0)
            path.lineTo(p3)
            control_rect = path.boundingRect().adjusted(-2, -2, 2, 2)
            self.prepareGeometryChange()
            self._pixels = []
            self._pixmap = None
            self._pixmap_offset = QPointF(0, 0)
            self._cached_bounding = control_rect
            self._path_cache = path
            return
        try:
            idx = edges.index(self.edge)
        except ValueError:
            # If edge not found, use chord-only fallback
            p0, p3 = self.convert_coords_to_parent()
            path = QPainterPath()
            path.moveTo(p0)
            path.lineTo(p3)
            control_rect = path.boundingRect().adjusted(-2, -2, 2, 2)
            self.prepareGeometryChange()
            self._pixels = []
            self._pixmap = None
            self._pixmap_offset = QPointF(0, 0)
            self._cached_bounding = control_rect
            self._path_cache = path
            return

        Cx, Cy, R, a_start, a_end, prefer_ccw = compute_arc_geometry_for_edge(edges, idx, self.edge)

    # convert to parent-local for rasterization
        # sample points
        total_angle = abs(a_end - a_start)
        if total_angle < 1e-6 or R < 1e-6:
            # nothing to draw; keep tiny bbox around chord
            p0, p3 = self.convert_coords_to_parent()
            path = QPainterPath()
            path.moveTo(p0)
            path.lineTo(p3)
            control_rect = path.boundingRect().adjusted(-2, -2, 2, 2)
            self.prepareGeometryChange()
            self._pixels = []
            self._pixmap = None
            self._pixmap_offset = QPointF(0, 0)
            self._cached_bounding = control_rect
            self._path_cache = path
            return

        # choose sampling density
        n = max(int(R * total_angle * 1.5), 32)
        n = min(n, 2000)
        dt = total_angle / n
        sign = 1.0 if (a_end - a_start) >= 0 else -1.0

        # generate points in parent-local coords
        points = []
        minx = miny = 1e18
        maxx = maxy = -1e18
        for i in range(n + 1):
            a = a_start + sign * dt * i
            sx = Cx + R * math.cos(a)
            sy = Cy + R * math.sin(a)
            p = self.mapFromScene(QPointF(sx, sy))
            px = int(round(p.x()))
            py = int(round(p.y()))
            points.append((px, py))
            if px < minx: minx = px
            if py < miny: miny = py
            if px > maxx: maxx = px
            if py > maxy: maxy = py

        width = max(0, maxx - minx + 1)
        height = max(0, maxy - miny + 1)
        control_path = QPainterPath()
        p0, p3 = self.convert_coords_to_parent()
        control_path.moveTo(p0)
        control_path.lineTo(p3)
        control_rect = control_path.boundingRect().adjusted(-2, -2, 2, 2)

        if width == 0 or height == 0 or width * height > 5_000_000:
            new_bounding = control_rect
            self.prepareGeometryChange()
            self._pixels = []
            self._pixmap = None
            self._pixmap_offset = QPointF(0, 0)
            self._cached_bounding = new_bounding
            self._path_cache = control_path
            return

        new_bounding = control_rect.united(QRectF(minx, miny, width, height))
        self.prepareGeometryChange()

        img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)
        qp = QPainter(img)
        try:
            qp.setPen(Qt.NoPen)
            qp.setBrush(QBrush(QColor("black")))
            for (px, py) in points:
                rx = px - minx
                ry = py - miny
                if 0 <= rx < width and 0 <= ry < height:
                    qp.drawRect(rx, ry, 1, 1)
        finally:
            qp.end()

        self._pixmap = QPixmap.fromImage(img)
        self._pixmap_offset = QPointF(minx, miny)
        self._cached_bounding = new_bounding
        # path used for selection/hit-testing: approximate polyline
        path = QPainterPath()
        if points:
            path.moveTo(points[0][0], points[0][1])
            for (px, py) in points[1:]:
                path.lineTo(px, py)
        self._path_cache = path

    def boundingRect(self):
        return self._cached_bounding

    def paint(self, painter, option, widget):
        # draw arc
        if self._pixmap:
            painter.drawPixmap(self._pixmap_offset, self._pixmap)

    def shape(self):
        # return cached path if available
        if getattr(self, "_path_cache", None) is not None:
            return self._path_cache
        # fallback: chord
        p0, p3 = self.convert_coords_to_parent()
        path = QPainterPath()
        path.moveTo(p0)
        path.lineTo(p3)
        return path