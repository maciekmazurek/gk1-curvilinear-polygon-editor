from enum import Enum
from config import *

class EdgeType(Enum):
    LINE = 1
    BEZIER = 2
    ARC = 3

class ConstraintType(Enum):
    NONE = 0
    VERTICAL = 1
    DIAGONAL_45 = 2
    FIXED_LENGTH = 3


class ContinuityType(Enum):
    G0 = 0
    G1 = 1
    C1 = 2

class LineDrawingMode(Enum):
    QGRAPHICS = 1
    BRESENHAM = 2

class Vertex:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
        self.radius = VERTEX_DIAMETER / 2
        self.continuity: ContinuityType = ContinuityType.G0

class Edge:
    def __init__(self, v1: Vertex, v2: Vertex, type: EdgeType = EdgeType.LINE):
        self.v1 = v1
        self.v2 = v2
        self.type = type
        # Constraint info
        self.constraint_type: ConstraintType = ConstraintType.NONE
        # For FIXED_LENGTH store desired length in same units as vertex coords
        self.constraint_value: float | None = None

class Polygon:
    def __init__(self):
        self.vertices: list[Vertex] = []
        self.edges: list[Edge] = []
        self.edges_dict = {}
        self.create()
            
    def create(self):
        self.vertices = [Vertex(-20, 60), Vertex(50, -30), Vertex(200, 40)]
        self.edges = [Bezier(self.vertices[0], self.vertices[1], Vertex(-50, 20), Vertex(0, -70)),
                      Edge(self.vertices[1], self.vertices[2]),
                      Edge(self.vertices[2], self.vertices[0])]
        for edge in self.edges:
            self.edges_dict[(edge.v1, edge.v2)] = edge
            self.edges_dict[(edge.v2, edge.v1)] = edge
            
class Bezier(Edge):
    def __init__(self, v1: Vertex, v2: Vertex, c1: Vertex, c2: Vertex):
        super().__init__(v1, v2, EdgeType.BEZIER)
        self.c1 = c1 # First control point
        self.c2 = c2 # Second control point