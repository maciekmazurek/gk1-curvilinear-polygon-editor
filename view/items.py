from model.model import Bezier, Vertex, Edge, Polygon
from config import *
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QMenu,
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
from model.model import LineDrawingMode, EdgeType

import algorithms

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
    
# Base class for edge items (StandardLine, BresenhamLine, Bezier, Arc)
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

class LineEdgeItem(EdgeItem):
    def __init__(self, edge: Edge, parent):
        if edge.type != EdgeType.LINE:
            pass # Should implement raising an error
        super().__init__(edge, parent)
        self._cached_bounding = QRectF(0, 0, 0, 0)
        self._p1 = QPointF()
        self._p2 = QPointF()
        # make this item accept context menu events and right-clicks
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)

    def convert_coords_to_parent(self):
        p1 = self.parentItem().mapFromScene(QPointF(self.edge.v1.x, self.edge.v1.y))
        p2 = self.parentItem().mapFromScene(QPointF(self.edge.v2.x, self.edge.v2.y))
        return (p1, p2)
    
    def contextMenuEvent(self, event):
        menu = QMenu()
        add_vertex_action = menu.addAction("Add new vertex")
        # We have to convert screenPos from QPointF to QPoint so we can
        # pass it to menu.exec()
        sp = event.screenPos()
        try:
            qp = sp.toPoint()
        except Exception:
            qp = sp
        chosen_action = menu.exec(qp)
        if chosen_action == add_vertex_action:
            parent = self.parentItem()
            if parent:
                # Pass the scene position of the edge midpoint to be explicit
                # but the polygon's method can compute midpoint itself if desired
                parent.add_vertex_on_edge(self.edge)
        event.accept()

    def shape(self):
        # Provide a stroked path so mouse events (clicks/right-clicks) hit the line
        path = QPainterPath()
        path.moveTo(self._p1)
        path.lineTo(self._p2)
        stroker = QPainterPathStroker()
        stroker.setWidth(6.0)  # clickable tolerance in parent-local coordinates
        return stroker.createStroke(path)

# Rysowany za pomocą interfejsu udostępnianego przez QGraphics
class StandardLineEdgeItem(LineEdgeItem):
    def __init__(self, edge: Edge, parent):
        super().__init__(edge, parent)

    def update_edge(self):
        self.prepareGeometryChange()
        p1, p2 = self.convert_coords_to_parent()
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
        painter.drawLine(self._p1, self._p2)

# Rysowany za pomocą własnej implementacji algorytmu Bresenhama
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
        p1, p2 = self.convert_coords_to_parent()
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
            # Draw pixmap at precomputed offset (in parent local coordinates)
            painter.drawPixmap(self._pixmap_offset, self._pixmap)
            # Uncomment the following line to show that functionality is working
            print(f"[DEBUG] Painting Bresenham line with {len(self._pixels)} pixels")
    
class BezierEdgeItem(EdgeItem):
    def __init__(self, edge: Bezier, parent):
        if edge.type != EdgeType.BEZIER:
            pass # Should implement raising an error
        super().__init__(edge, parent)
        self._pixels = []
        self._pixmap = None
        self._pixmap_offset = QPointF(0, 0)

        # path cache used only for shape() / hit-testing (kept up-to-date)
        self._path_cache = None

        self.control_handle_1 = ControlPointItem(edge.c1, parent=self)
        self.control_handle_2 = ControlPointItem(edge.c2, parent=self)
        
        # On init place handles to correct positions
        self._place_control_handles()
        self.update_edge()

    def _place_control_handles(self):
        # map model (scene coords) to local parent coords and set pos without triggering callbacks
        self.updating_from_parent = True
        try:
            p1 = self.mapFromScene(QPointF(self.edge.c1.x, self.edge.c1.y))
            p2 = self.mapFromScene(QPointF(self.edge.c2.x, self.edge.c2.y))
            self.control_handle_1.setPos(p1)
            self.control_handle_2.setPos(p2)
        finally:
            self.updating_from_parent = False

    def on_control_moved(self, control_vertex: Vertex, new_scene_pos: QPointF):
        # update model control point (scene coords)
        control_vertex.x = new_scene_pos.x()
        control_vertex.y = new_scene_pos.y()
        # update caches / redraw
        self.update_edge()
        self.update()
    
    def update_edge(self):
        # Convert control points to local (parent) coordinates for rasterization
        p0 = self.mapFromScene(QPointF(self.edge.v1.x, self.edge.v1.y))
        p1 = self.mapFromScene(QPointF(self.edge.c1.x, self.edge.c1.y))
        p2 = self.mapFromScene(QPointF(self.edge.c2.x, self.edge.c2.y))
        p3 = self.mapFromScene(QPointF(self.edge.v2.x, self.edge.v2.y))

        # Build control-polygon path and its bounding rect (local coords)
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
        xs = [p[0] for p in self._pixels]
        ys = [p[1] for p in self._pixels]
        minx = min(xs) - 1
        miny = min(ys) - 1
        maxx = max(xs) + 1
        maxy = max(ys) + 1

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

        # Compute final bounding as union of pixel bbox and control polygon bbox
        pix_rect = QRectF(minx, miny, width, height)
        new_bounding = control_rect.united(pix_rect)

        # prepare for geometry change BEFORE updating cached geometry
        self.prepareGeometryChange()

        # create image and rasterize pixels relative to minx/miny
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
        p0 = self.mapFromScene(QPointF(self.edge.v1.x, self.edge.v1.y))
        p1 = self.mapFromScene(QPointF(self.edge.c1.x, self.edge.c1.y))
        p2 = self.mapFromScene(QPointF(self.edge.c2.x, self.edge.c2.y))
        p3 = self.mapFromScene(QPointF(self.edge.v2.x, self.edge.v2.y))
        painter.drawLine(p0, p1)
        painter.drawLine(p1, p2)
        painter.drawLine(p2, p3)

        # Draw bezier curve
        if self._pixmap:
            painter.drawPixmap(self._pixmap_offset, self._pixmap)

    def shape(self):
        """
        Provide a path used for hit-testing/selection. We return the control-polygon
        path (mapped to local coordinates) expanded slightly by the pixmap bounding rect.
        """
        # Ensure we always have a path cache
        # if getattr(self, "_path_cache", None) is not None:
        #     return self._path_cache
        # fallback: build transient path from current control points
        p0 = self.mapFromScene(QPointF(self.edge.v1.x, self.edge.v1.y))
        p1 = self.mapFromScene(QPointF(self.edge.c1.x, self.edge.c1.y))
        p2 = self.mapFromScene(QPointF(self.edge.c2.x, self.edge.c2.y))
        p3 = self.mapFromScene(QPointF(self.edge.v2.x, self.edge.v2.y))
        path = QPainterPath()
        path.moveTo(p0)
        path.lineTo(p1)
        path.lineTo(p2)
        path.lineTo(p3)
        self._path_cache = path
        return path

class PolygonItem(QGraphicsItem):
    def __init__(self, polygon: Polygon):
        super().__init__()
        self.polygon = polygon
        # We disable QGraphics Framework's built-in moving mechanism
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        # Default line drawing mode
        self.line_drawing_mode = LineDrawingMode.QGRAPHICS

        # Flag indicating whether the position of vertices is being currently 
        # updated by the parent (this class)
        self.updating_from_parent = False

        # Properties used for implementing polygon dragging
        self._dragging = False
        self._drag_start_scene = None
        self._original_vertices_positions = None
        self._original_control_positions = None

        self.vertex_items = {}
        self.edge_items = []

        self._setup_childitems()

    def boundingRect(self):
        # Build union of:
        #  - vertex bounding box (scene coords -> local)
        #  - bounding rects of all child edge items (they are in local coords)
        rects = []

        if self.polygon.vertices:
            minx = min(v.x for v in self.polygon.vertices)
            miny = min(v.y for v in self.polygon.vertices)
            maxx = max(v.x for v in self.polygon.vertices)
            maxy = max(v.y for v in self.polygon.vertices)
            top_left = self.mapFromScene(QPointF(minx, miny))
            bottom_right = self.mapFromScene(QPointF(maxx, maxy))
            rects.append(QRectF(top_left, bottom_right).normalized())

        # include child edge items' bounding rects (already in local coords)
        for e_item in getattr(self, "edge_items", []):
            try:
                r = e_item.boundingRect()
            except Exception:
                r = QRectF(0, 0, 0, 0)
            if not r.isNull():
                rects.append(r)

        if not rects:
            return QRectF(0, 0, 0, 0)

        # union all rects
        united = rects[0]
        for r in rects[1:]:
            united = united.united(r)
        # add a small margin so handles/pen fit
        return united.adjusted(-4, -4, 4, 4)

    def shape(self):
        """
        Build path corresponding to actual edges. This is used only for hit-testing
        and selection. For LINE edges we add straight segments, for BEZIER we add a
        cubicTo (used only by shape() — actual drawing of bezier is pixelized in
        BezierEdgeItem).
        """
        path = QPainterPath()
        if not self.polygon.edges:
            return path

        # start from first edge's v1
        first_edge = self.polygon.edges[0]
        start = self.mapFromScene(QPointF(first_edge.v1.x, first_edge.v1.y))
        path.moveTo(start)

        for e in self.polygon.edges:
            if getattr(e, "type", None) == EdgeType.LINE:
                p2 = self.mapFromScene(QPointF(e.v2.x, e.v2.y))
                path.lineTo(p2)
            elif getattr(e, "type", None) == EdgeType.BEZIER:
                # add cubicTo for hit-testing (control points in scene coords -> map)
                c1 = self.mapFromScene(QPointF(e.c1.x, e.c1.y))
                c2 = self.mapFromScene(QPointF(e.c2.x, e.c2.y))
                p3 = self.mapFromScene(QPointF(e.v2.x, e.v2.y))
                path.cubicTo(c1, c2, p3)
            else:
                # fallback to straight line
                p2 = self.mapFromScene(QPointF(e.v2.x, e.v2.y))
                path.lineTo(p2)

        return path
    
    def paint(self, painter, option, widget):
        # Do not draw polygon edges here — EdgeItem children are responsible
        # for drawing their own representation (line / bresenham / bezier).
        # Optionally draw selection outline when selected:
        if self.isSelected():
            painter.setPen(QPen(QColor("blue"), 1, Qt.DashLine))
            painter.drawPath(self.shape())

    def _setup_childitems(self):
        self.updating_from_parent = True
        try:
            # Setting up VertexItems
            for v in self.polygon.vertices:
                v_item = VertexItem(v, parent=self)
                # We convert vertex position from scene coordinates to parent 
                # coordinates
                vertex_parent_coords = self.mapFromScene(QPointF(v.x, v.y))
                # "updating_from_parent" flag prevents from calling 
                # parent.on_vertex_moved by children vertices (which whould
                # cause the infinite loop) after the following setPos 
                # method call
                v_item.setPos(vertex_parent_coords)
                self.vertex_items[v] = v_item
        finally:
            self.updating_from_parent = False

        # Setting up EdgeItems
        for e in self.polygon.edges:
            e_item = self.EdgeItemFactory(e, parent=self)
            self.edge_items.append(e_item)
            e_item.update_edge()

    def _rebuild_childitems(self):
        # Remove all childitems
        for child in list(self.childItems()):
            child.setParentItem(None)
            sc = self.scene()
            if sc:
                sc.removeItem(child)
        self.vertex_items.clear()
        self.edge_items.clear()

        # Rebuild
        self._setup_childitems()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start_scene = event.scenePos()
            # We save original positions of vertices and control points
            self._original_vertices_positions = [(v, v.x, v.y) for v in self.polygon.vertices]
            self._original_control_positions = [(e, e.c1.x, e.c1.y, e.c2.x, e.c2.y) for e in self.polygon.edges if e.type == EdgeType.BEZIER]
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.scenePos() - self._drag_start_scene
            dx, dy = delta.x(), delta.y()

            # We update original positions of vertices and control points
            for v, ox, oy in self._original_vertices_positions:
                v.x = ox + dx
                v.y = oy + dy
            for e, c1x, c1y, c2x, c2y in self._original_control_positions:
                e.c1.x = c1x + dx
                e.c1.y = c1y + dy
                e.c2.x = c2x + dx
                e.c2.y = c2y + dy

            self.updating_from_parent = True
            try:
                for v, v_item in self.vertex_items.items():
                    # We convert new vertex position from scene coordinates to 
                    # parent coordinates
                    vertex_new_parent_coords = self.mapFromScene(QPointF(v.x, v.y))
                    # "updating_from_parent" flag prevents from calling 
                    # parent.on_vertex_moved by children vertices (which whould
                    # cause the infinite loop) after the following setPos 
                    # method call
                    v_item.setPos(vertex_new_parent_coords)
                for e_item in self.edge_items:
                    e_item.update_edge()
            finally:
                self.updating_from_parent = False

            self.update()
            event.accept()
        else:
            return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._drag_start_scene = None
            self._original_vertices_positions = None
            self._original_control_positions = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def EdgeItemFactory(self, edge: Edge, parent):
        if edge.type == EdgeType.LINE:
            if self.line_drawing_mode == LineDrawingMode.QGRAPHICS:
                return StandardLineEdgeItem(edge, parent)
            elif self.line_drawing_mode == LineDrawingMode.BRESENHAM:
                return BresenhamLineEdgeItem(edge, parent)
        elif edge.type == EdgeType.BEZIER:
            return BezierEdgeItem(edge, parent)

    # Method called by VertexItem when user directly drags a single vertex
    def on_vertex_moved(self, vertex: Vertex, vertex_new_scene_coords: QPointF):
        vertex.x = vertex_new_scene_coords.x()
        vertex.y = vertex_new_scene_coords.y()

        # PRZEIMPLEMENTOWAĆ W TAKI SPOSÓB, ŻEBY ODPOWIEDNIO MODYFIKOWAĆ
        # KRAWĘDZIE GDY PRZESUWANE SĄ DANE WIERZCHOŁKI
        for e_item in self.edge_items:
            if e_item.edge.v1 is vertex or e_item.edge.v2 is vertex:
                e_item.update_edge()

        self.update()

    # Method called by LineEdgeItem when user wants to create new vertex
    def add_vertex_on_edge(self, edge: Edge):
        v1 = edge.v1
        v2 = edge.v2
        new_vertex = Vertex((v1.x + v2.x) / 2, (v1.y + v2.y) / 2)
        old_edge_index = self.polygon.edges.index(edge)

        # Insert new vertex in polygon.vertices right after v1
        try:
            v1_idx = self.polygon.vertices.index(v1)
        except ValueError:
            v1_idx = len(self.polygon.vertices) - 1
        self.polygon.vertices.insert(v1_idx + 1, new_vertex)

        # Replace edges: edge -> [edge(v1,new_v), edge(new_v,v2)]
        new_edge1 = Edge(v1, new_vertex)
        new_edge2 = Edge(new_vertex, v2)
        self.polygon.edges[old_edge_index] = new_edge1
        self.polygon.edges.insert(old_edge_index + 1, new_edge2)

        self._rebuild_childitems()

    # Method called by MainWindow when line drawing mode is changed
    def redraw_with_new_mode(self, mode: LineDrawingMode):
        # Update line drawing mode
        self.line_drawing_mode = mode

        # Remove old edge items
        for e_item in self.edge_items:
            e_item.setParentItem(None)
            scene = self.scene()
            if scene:
                scene.removeItem(e_item)
        self.edge_items.clear()

        # Create new edge items according to new drawing mode
        for e in self.polygon.edges:
            e_item = self.EdgeItemFactory(e, parent=self)
            self.edge_items.append(e_item)
            # Redrawing
            e_item.update_edge()

        self.update()