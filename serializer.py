from __future__ import annotations
from dataclasses import asdict
from typing import Any, Dict

from graph import Graph, Node, Edge


class GraphSerializer:
    @staticmethod
    def _nodes_iter(graph: Graph):
        if isinstance(graph.nodes, dict):
            return graph.nodes.values()
        elif isinstance(graph.nodes, list):
            return graph.nodes
        else:
            return list(graph.nodes)

    @staticmethod
    def to_dict(graph: Graph) -> Dict[str, Any]:
        nodes_list = []
        for n in GraphSerializer._nodes_iter(graph):
            if isinstance(n, Node):
                nodes_list.append({"id": n.id, "data": n.data})
            elif isinstance(n, dict) and "id" in n:
                nodes_list.append(n)
            else:
                nodes_list.append(asdict(n))
        edges_list = []
        for e in getattr(graph, "edges", []) or []:
            if isinstance(e, Edge):
                edges_list.append({"from": e.from_node, "to": e.to_node})
            elif isinstance(e, dict) and "from" in e and "to" in e:
                edges_list.append(e)
            else:
                try:
                    d = asdict(e)
                    edges_list.append({"from": d.get("from_node"), "to": d.get("to_node")})
                except Exception:
                    pass
        return {"nodes": nodes_list, "edges": edges_list}

    @staticmethod
    def to_json(graph: Graph, *, pretty: bool = False) -> str:
        import json
        return json.dumps(GraphSerializer.to_dict(graph), indent=2 if pretty else None, ensure_ascii=False)