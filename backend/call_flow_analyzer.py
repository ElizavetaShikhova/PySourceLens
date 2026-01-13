from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import ast_parser
from graph import Edge, Node


class CallFlowAnalyzer:
    def build_edges(
        self,
        *,
        files: List[Path],
        elements: Dict[str | Path, dict],
        nodes: Dict[str, Node],
        project_root: Path,
    ) -> List[Edge]:
        edges: Set[Tuple[str, str]] = set()
        node_ids: Set[str] = set(nodes.keys())
        for file in files:
            try:
                tree = ast_parser.parse_file(file, attach_parents=True)
            except Exception:
                continue
            module_name = self._module_name_for_file(file, project_root)
            el = elements.get(file) or elements.get(str(file))
            module_symbols = self._build_symbol_tables(module_name, el)
            for frm, to in self._iter_calls(tree, module_name, module_symbols):
                if to in node_ids and frm in node_ids:
                    edges.add((frm, to))
        return [Edge(from_node=f, to_node=t) for (f, t) in sorted(edges)]

    def _module_name_for_file(self, file: Path, root: Path) -> str:
        try:
            rel = file.relative_to(root)
        except ValueError:
            rel = file
        if rel.name == "__init__.py":
            parts = list(rel.parent.parts)
        else:
            parts = list(rel.with_suffix("").parts)
        return ".".join(parts)

    def _build_symbol_tables(self, module_name: str, elements_blob: Optional[dict]):
        funcs: Dict[str, str] = {}
        classes: Dict[str, str] = {}
        methods: Dict[Tuple[str, str], str] = {}
        if not elements_blob:
            return {"funcs": funcs, "classes": classes, "methods": methods}
        for f in elements_blob.get("functions", []) or []:
            funcs[f["name"]] = f.get("qualname") or f"{module_name}.{f['name']}"
        for c in elements_blob.get("classes", []) or []:
            classes[c["name"]] = c.get("qualname") or f"{module_name}.{c['name']}"
            for m in c.get("methods", []) or []:
                methods[(c["name"], m["name"])] = m.get("qualname") or f"{classes[c['name']]}.{m['name']}"
        return {"funcs": funcs, "classes": classes, "methods": methods}

    def _iter_calls(self, tree: ast.AST, module_name: str, sym: dict) -> Iterable[Tuple[str, str]]:
        funcs: Dict[str, str] = sym["funcs"]
        classes: Dict[str, str] = sym["classes"]
        methods: Dict[Tuple[str, str], str] = sym["methods"]

        class Visitor(ast.NodeVisitor):
            def __init__(self):
                self.cur_class: Optional[str] = None
                self.cur_func: Optional[str] = None

            def _caller(self) -> str:
                if self.cur_class and self.cur_func:
                    cls_qn = classes.get(self.cur_class, f"{module_name}.{self.cur_class}")
                    return f"{cls_qn}.{self.cur_func}"
                if self.cur_func:
                    return funcs.get(self.cur_func, f"{module_name}.{self.cur_func}")
                return module_name

            def _resolve_attribute(self, attr: ast.Attribute) -> Optional[str]:
                if isinstance(attr.value, ast.Name) and attr.value.id == "self" and self.cur_class:
                    q = methods.get((self.cur_class, attr.attr))
                    if q:
                        return q
                    return f"{module_name}.{self.cur_class}.{attr.attr}"
                if isinstance(attr.value, ast.Name) and attr.value.id in classes:
                    cls_q = classes[attr.value.id]
                    return f"{cls_q}.{attr.attr}"
                if isinstance(attr.value, ast.Name):
                    base = attr.value.id
                    if base and base in classes:
                        return f"{classes[base]}.{attr.attr}"
                    if base:
                        return f"{base}.{attr.attr}"
                return None

            def _resolve_call(self, call: ast.Call) -> Optional[str]:
                f = call.func
                if isinstance(f, ast.Name):
                    if f.id in funcs:
                        return funcs[f.id]
                    if f.id in classes:
                        return classes[f.id]
                    if f.id:
                        return f.id
                    return None
                if isinstance(f, ast.Attribute):
                    return self._resolve_attribute(f)
                return None

            def visit_ClassDef(self, node: ast.ClassDef):
                prev = self.cur_class
                self.cur_class = node.name
                self.generic_visit(node)
                self.cur_class = prev

            def visit_FunctionDef(self, node: ast.FunctionDef):
                prev = self.cur_func
                self.cur_func = node.name
                self.generic_visit(node)
                self.cur_func = prev

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
                prev = self.cur_func
                self.cur_func = node.name
                self.generic_visit(node)
                self.cur_func = prev

        v = Visitor()
        out: List[Tuple[str, str]] = []

        def _walk(n: ast.AST):
            if isinstance(n, ast.Call):
                callee = v._resolve_call(n)
                if callee:
                    out.append((v._caller(), callee))

            if isinstance(n, ast.ClassDef):
                prev_class = v.cur_class
                v.cur_class = n.name
                for child in n.body:
                    _walk(child)
                v.cur_class = prev_class

            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                prev_func = v.cur_func
                v.cur_func = n.name
                for child in n.body:
                    _walk(child)
                v.cur_func = prev_func

            else:
                for child in ast.iter_child_nodes(n):
                    _walk(child)
        _walk(tree)
        return out


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    from dependency_analyzer import DependencyAnalyzer
    da = DependencyAnalyzer(root)
    graph = da.create_dependency()
    edges = CallFlowAnalyzer().build_edges(files=da.files, elements=da.elements, nodes=graph.nodes if isinstance(graph.nodes, dict) else {n.id: n for n in graph.nodes}, project_root=root)
    print(f"edges: {len(edges)}")

