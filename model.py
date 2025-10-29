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
        self.continuity: ContinuityType = ContinuityType.G0

class Edge:
    def __init__(self, v1: Vertex, v2: Vertex, type: EdgeType = EdgeType.LINE):
        self.v1 = v1
        self.v2 = v2
        self.type = type
        self.constraint_type: ConstraintType = ConstraintType.NONE
        self.constraint_value: float | None = None

class Polygon:
    def __init__(self):
        self.vertices: list[Vertex] = []
        self.edges: list[Edge] = []
        self.edges_dict = {}
        self.create()
            
    def create(self):
        vertex_0 = Vertex(-20, 120)
        vertex_0.continuity = ContinuityType.C1
        vertex_1 = Vertex(-30, -30)
        vertex_1.continuity = ContinuityType.G1
        vertex_2 = Vertex(60, -60)
        vertex_3 = Vertex(180, -10)
        vertex_4 = Vertex(140, 100)
        edge_01 = Bezier(vertex_0, vertex_1, Vertex(-110, 100), Vertex(-100, 10))
        edge_12 = Edge(vertex_1, vertex_2)
        edge_23 = Edge(vertex_2, vertex_3)
        edge_23.constraint_type = ConstraintType.DIAGONAL_45
        edge_34 = Edge(vertex_3, vertex_4)
        edge_34.constraint_type = ConstraintType.VERTICAL
        edge_40 = Edge(vertex_4, vertex_0)
        edge_40.constraint_type = ConstraintType.FIXED_LENGTH
        edge_40.constraint_value = 150.0

        self.vertices = [vertex_0, vertex_1, vertex_2, vertex_3, vertex_4]
        self.edges = [edge_01, edge_12, edge_23, edge_34, edge_40]
        for edge in self.edges:
            self.edges_dict[(edge.v1, edge.v2)] = edge
            self.edges_dict[(edge.v2, edge.v1)] = edge
            
class Bezier(Edge):
    def __init__(self, v1: Vertex, v2: Vertex, c1: Vertex, c2: Vertex):
        super().__init__(v1, v2, EdgeType.BEZIER)
        self.c1 = c1 # Control point associated with v1
        self.c2 = c2 # Control point associated with v2

class Arc(Edge):
    def __init__(self, v1: Vertex, v2: Vertex):
        super().__init__(v1, v2, EdgeType.ARC)