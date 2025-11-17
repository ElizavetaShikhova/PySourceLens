from entry_point_analyzer import EntryPointAnalyzer
import file_searcher
from import_analyzer import ImportAnalyzer
import elements_extractor
from graph import Graph, Node, Edge
from pathlib import Path
import ast_parser
from typing import List, Dict, Any
from ASTParseError import ASTParseError

class DependencyAnalyzer:
    def __init__(self, directory_path: str | Path):
        self.directory_path = Path(directory_path)
        if not self.directory_path.exists():
            raise FileNotFoundError(f"Project path not found: {directory_path}")
        self.files = self._get_files()
        self.imports = self._get_imports()
        self.entry_points = self._get_entry_point()
        self.elements = self._get_elements()

    def create_dependency(self):
        nodes: dict[str, Node] = self._get_nodes()
        graph = Graph(nodes=list(nodes.values()), edges=[])
        # graph.edges = call_flow_analyzer()
        return graph

    def _get_files(self) -> List[Path]:
        return file_searcher.get_files_in_directory(self.directory_path)

    def _get_imports(self) -> Dict[str, str]:
        import_analyzer = ImportAnalyzer()
        return import_analyzer.find_imports(self.files)

    def _get_entry_point(self) -> List[Dict[str, Any]]:
        try:
            entry_point_analyzer = EntryPointAnalyzer()
            return entry_point_analyzer.analyze_project(self.directory_path)
        except:
            raise 

    def _get_elements(self) -> Dict[str, Any]:
        elements = {}
        for file in self.files:
            try:
                module = ast_parser.parse_file(file)
                module_name = self.path_to_module_name(Path(file), self.directory_path)
                data = elements_extractor.extract_elements(module, module_name=module_name, file_path=str(file))
                elements[file] = data
            except (SyntaxError, ASTParseError):
                continue
            except:
                raise
        return elements
    
    def path_to_module_name(self, file_path: Path, directory: Path) -> str:
        try:
            rel_path = file_path.relative_to(directory)
        except ValueError:
            raise ValueError(f"File {file_path} is not inside project root {directory}")

        if rel_path.name == "__init__.py":
            module_parts = list(rel_path.parent.parts)
        else:
            if rel_path.suffix != ".py":
                raise ValueError(f"Not a Python file: {file_path}")
            stem = rel_path.with_suffix("") 
            module_parts = list(stem.parts)
        return ".".join(module_parts)
    
    def _add_nodes_functions(self, list_functions, nodes):
        for function_element in list_functions:
                function_id = function_element["qualname"]
                if function_id not in nodes:
                    node_function = Node(id=function_id, data=function_element)
                    nodes[function_id] = node_function
                    self._add_nodes_functions(function_element.get("nested_functions", []), nodes)
    
    def _get_nodes(self) -> dict[str, Node]:
        nodes: dict[str, Node] = dict()
        for file_path, data in self.elements.items():
            module_id = data["module"]["name"]
            node_module = Node(id=module_id, data=data["module"])
            nodes[module_id] = node_module
            for class_element in data["classes"]:
                class_id = class_element["qualname"]
                node_class = Node(id=class_id, data=class_element)
                nodes[class_id] = node_class
                self._add_nodes_functions(class_element["methods"], nodes)
            self._add_nodes_functions(data["functions"], nodes)
        for import_name, resolved_path in self.imports.items():
            if import_name in nodes:
                continue
            if resolved_path:
                nodes[import_name] = Node(id=import_name,
                    data={
                        "name": import_name,
                        "path": resolved_path,
                        "type": "external_module"
                    }
                )
            else:
                nodes[import_name] = Node(
                    id=import_name,
                    data={
                        "name": import_name,
                        "path": None,
                        "type": "builtin_or_unknown"
                    }
                )

        for entry_point in self.entry_points:
            file_path_str = entry_point["file"]
            file_path = Path(file_path_str)
            full_path = self.directory_path / file_path

            if full_path in self.files:
                module_name = self.path_to_module_name(full_path, self.directory_path)
            else:
                continue

            if entry_point["type"] == "main_guard":
                entry_id = module_name
            elif entry_point["type"] == "function_call":
                entry_id = f"{module_name}.{entry_point['function_name']}"
            else:
                continue

            if entry_id not in nodes:
                nodes[entry_id] = Node(
                    id=entry_id,
                    data={
                        "name": entry_id,
                        "type": "entry_point_stub",
                        "file": entry_point.get("file"),
                        "line": entry_point.get("line")
                    }
                )

        return nodes

if __name__ == "__main__":
    print(DependencyAnalyzer(r"").create_dependency())