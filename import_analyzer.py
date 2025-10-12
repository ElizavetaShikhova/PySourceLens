from pathlib import Path
from typing import Dict
import ast_parser
import ast
import importlib.util as util


class ImportAnalyzer:
    def __init__(self):
        self.imports : Dict[str, str] = {}
        self._checked : Dict[str, str] = {}
        self._importlib_aliases: set[str] = {"importlib"}
        self._importlib_functions: set[str] = {     
        "import_module", 
        "__import__"}
        self._string_literals: Dict[str, str] = {}

    def find_imports(self, all_paths: list[Path]) -> dict[str]:
        for path in all_paths:
            self._find_import_in_file(path)
        return self.imports

    def _find_import_in_file(self, path: Path) -> None:
        try:
            module = ast_parser.parse_file(path)
        except SyntaxError:
            return  
        for node in ast.walk(module):
            self._simple_import(node)
            self._from_import(node, path)
            self._importlib_import(node)
            self._assigning_variable_importlib(node)
            self._builtin_import(node)
            self._track_string_assignments(node)
        print(self.imports)

    def _check_import(self, import_name: str) -> str:
        if not import_name or not isinstance(import_name, str):
            return ""
        if import_name in self._checked:
            return self._checked[import_name]
        
        try:
            spec = util.find_spec(import_name)
            if spec is None:
                result = ""
            elif spec.origin is None:
                result = ""
            else:
                path = Path(spec.origin).resolve()
                result = str(path)
        except (AttributeError, ValueError, ImportError, OSError):
            result = ""
        
        self._checked[import_name] = result
        return result
        
    
    def _simple_import(self, node) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                name_import = alias.name
                self.imports[name_import] = self._check_import(name_import)

                if name_import == "importlib":
                    alias_name = alias.asname if alias.asname else "importlib"
                    self._importlib_aliases.add(alias_name)

    def _from_import(self, node, path) -> None:
        if isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                    return
            if node.module == "importlib":
                for alias in node.names:
                    if alias.name in ("import_module", "__import__"):
                        alias_name = alias.asname or alias.name
                        self._importlib_functions.add(alias_name)
                self.imports["importlib"] = self._check_import("importlib")
            else:
                if node.module:
                    self.imports[node.module] = self._check_import(node.module)
                else:
                    for alias in node.names:
                        name_import = alias.name
                        self.imports[name_import] = self._check_import(name_import)        

    def _importlib_import(self, node) -> None:
        if isinstance(node, ast.Expr):
            val = node.value
            if isinstance(val, ast.Call):
                if isinstance(val.func, ast.Name):
                    if val.func.id in self._importlib_functions:
                        if val.args and isinstance(val.args[0], ast.Constant):
                            module_name = val.args[0].value
                            if isinstance(module_name, str) and module_name.strip():
                                self.imports[module_name] = self._check_import(module_name)

                if isinstance(val.func, ast.Attribute):
                    func_val = val.func.value
                    attr = val.func.attr
                    if (isinstance(func_val, ast.Name) and
                        func_val.id in self._importlib_aliases and
                        attr in ('import_module', '__import__')):
                        if val.args and isinstance(val.args[0], ast.Constant):
                            module_name = val.args[0].value
                            if isinstance(module_name, str):
                                self.imports[module_name] = self._check_import(module_name)

                

    def _assigning_variable_importlib(self, node) -> None:
        if isinstance(node, ast.Assign):
            value = node.value
            if isinstance(value, ast.Name) and value.id == "importlib":
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self._importlib_aliases.add(target.id)
            elif isinstance(value, ast.Name) and value.id in self._importlib_aliases:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self._importlib_aliases.add(target.id)

    def _builtin_import(self, node):
        if isinstance(node, ast.Expr):
            val = node.value
            if isinstance(val, ast.Call) and isinstance(val.func, ast.Name):
                if val.func.id == "__import__":
                    if val.args and isinstance(val.args[0], ast.Constant):
                        module_name = val.args[0].value
                        if isinstance(module_name, str) and module_name.strip():
                            self.imports[module_name] = self._check_import(module_name)

    def _track_string_assignments(self, node) -> None:
        if isinstance(node, ast.Assign):
            if (len(node.targets) == 1 and 
                isinstance(node.targets[0], ast.Name) and
                isinstance(node.value, ast.Constant) and
                isinstance(node.value.value, str)):
                var_name = node.targets[0].id
                self._string_literals[var_name] = node.value.value
                    
    
if __name__ == "__main__":
    analyzer = ImportAnalyzer()
    analyzer._find_import_in_file(Path("file_searcher.py"))