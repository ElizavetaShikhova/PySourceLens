from dataclasses import dataclass
from typing import Any, List, Optional

@dataclass
class Node:
    id: str
    data: Any

@dataclass
class Edge:
    from_node: str
    to_node: str

@dataclass
class Graph:
    edges: List[Edge]
    nodes: dict[str, Node]