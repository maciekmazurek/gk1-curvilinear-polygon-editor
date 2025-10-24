from enum import Enum
from config import *

class EdgeType(Enum):
    LINE = 1
    BEZIER = 2
    ARC = 3

class LineDrawingMode(Enum):
    QGRAPHICS = 1
    BRESENHAM = 2

class Vertex:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
        self.radius = VERTEX_DIAMETER / 2

class Edge:
    def __init__(self, v1: Vertex, v2: Vertex, type: EdgeType):
        self.v1 = v1
        self.v2 = v2
        self.type = type

class Polygon:
    def __init__(self):
        self.vertices = [Vertex(1, 4), Vertex(50, -10), Vertex(200, 40)]
        self.edges: list[Edge] = []
        for i in range(len(self.vertices)):
            self.edges.append(Edge(self.vertices[i % 3], 
                                   self.vertices[(i + 1) % 3], 
                                   EdgeType.LINE))

# Tu w przyszłości będą zaimplementowane klasy BezierEdge i ArcEdge dziedziczące
# po klasie Edge