from pathlib import Path
from typing import Dict, List
import ast_parser
import ast
from ASTParseError import ASTParseError
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

    def find_imports(self, all_paths: list[Path]) -> Dict[str, str]:
        for path in all_paths:
            self._find_import_in_file(path)
        return self.imports

    def _find_import_in_file(self, path: Path) -> None:
        try:
            module = ast_parser.parse_file(path)
        except (SyntaxError, ASTParseError):
            return  
        for node in ast.walk(module):
            self._simple_import(node)
            self._from_import(node, path)
            self._assigning_variable_importlib(node)
            self._track_string_assignments(node)
            if isinstance(node, ast.Call):
                self._handle_call(node)

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
                try :
                    path = Path(spec.origin).resolve()
                    result = str(path)
                except (OSError, RuntimeError):
                    result = ""
        except (AttributeError, ValueError, ImportError, OSError, ModuleNotFoundError):
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

    def _from_import(self, node, current_file_path: Path) -> None:
        if not isinstance(node, ast.ImportFrom):
            return

        if node.module == "future":
            return

        if node.module == "importlib":
            for alias in node.names:
                if alias.name in ("import_module", "import"):
                    alias_name = alias.asname or alias.name
                    self._importlib_functions.add(alias_name)
            self.imports["importlib"] = self._check_import("importlib")
            return
        
        if node.level > 0:
            current_dir = current_file_path.parent
            base_dir = current_dir
            for _ in range(node.level - 1):
                base_dir = base_dir.parent
                if base_dir == base_dir.parent:
                    return

            if node.module:
                module_parts = node.module.split(".")
                candidate_path = base_dir.joinpath(*module_parts)
                candidates = [
                    candidate_path.with_suffix(".py"),
                    candidate_path / "init.py"
                ]
                resolved = None
                for cand in candidates:
                    if cand.exists():
                        resolved = cand.resolve()
                        break
                if resolved:
                    key = str(resolved)
                    self.imports[key] = str(resolved)
            else:
                for alias in node.names:
                    mod_name = alias.name
                    candidate_path = base_dir / mod_name
                    candidates = [
                        candidate_path.with_suffix(".py"),
                        candidate_path / "init.py"
                    ]
                    resolved = None
                    for cand in candidates:
                        if cand.exists():
                            resolved = cand.resolve()
                            break
                    if resolved:
                        key = str(resolved)
                        self.imports[key] = str(resolved)

        else:
            if node.module:
                self.imports[node.module] = self._check_import(node.module)
            else:
                for alias in node.names:
                    name_import = alias.name
                    self.imports[name_import] = self._check_import(name_import)  

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

    def _handle_call(self, call_node: ast.Call) -> None:
        if isinstance(call_node.func, ast.Name) and call_node.func.id == "__import__":
            if call_node.args and isinstance(call_node.args[0], ast.Constant):
                mod_name = call_node.args[0].value
                if isinstance(mod_name, str) and mod_name.strip():
                    self.imports[mod_name] = self._check_import(mod_name)
            return

        if isinstance(call_node.func, ast.Attribute):
            obj = call_node.func.value
            attr = call_node.func.attr
            if (attr in ('import_module', '__import__') and
                isinstance(obj, ast.Name) and
                obj.id in self._importlib_aliases):
                if call_node.args and isinstance(call_node.args[0], ast.Constant):
                    mod_name = call_node.args[0].value
                    if isinstance(mod_name, str) and mod_name.strip():
                        self.imports[mod_name] = self._check_import(mod_name)
            return
        
        if isinstance(call_node.func, ast.Name) and call_node.func.id in self._importlib_functions:
            if call_node.args and isinstance(call_node.args[0], ast.Constant):
                mod_name = call_node.args[0].value
                if isinstance(mod_name, str) and mod_name.strip():
                    self.imports[mod_name] = self._check_import(mod_name)

    def _track_string_assignments(self, node) -> None:
        if isinstance(node, ast.Assign):
            if (len(node.targets) == 1 and 
                isinstance(node.targets[0], ast.Name) and
                isinstance(node.value, ast.Constant) and
                isinstance(node.value.value, str)):
                var_name = node.targets[0].id
                self._string_literals[var_name] = node.value.value

    def find_imports_with_sources(self, all_paths: list[Path]) -> Dict[Path, List[str]]:
        result: Dict[Path, List[str]] = {}
        for path in all_paths:
            original_imports = self.imports.copy()
            self.imports = {}
            self._find_import_in_file(path)
            result[path] = list(self.imports.keys())
            self.imports.update(original_imports)
        
        return result
                    
    
if __name__ == "__main__":
    analyzer = ImportAnalyzer()
    analyzer._find_import_in_file(Path("file_searcher.py"))