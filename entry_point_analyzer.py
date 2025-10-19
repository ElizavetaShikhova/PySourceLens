import ast
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

from ast_parser import parse_file, ASTParseError
from file_searcher import get_files_in_directory


def is_simple_main_guard(test_node: ast.AST) -> bool:
    """Проверяет простое сравнение __name__ == '__main__'"""
    return (isinstance(test_node, ast.Compare) and
            isinstance(test_node.left, ast.Name) and
            test_node.left.id == '__name__' and
            len(test_node.ops) == 1 and
            isinstance(test_node.ops[0], ast.Eq) and
            len(test_node.comparators) == 1 and
            isinstance(test_node.comparators[0], ast.Constant) and
            test_node.comparators[0].value == '__main__')


def find_first_executable_line_heuristic(lines: List[str]) -> dict[str, int | str] | None:
    """
    Эвристический поиск первой исполняемой строки когда AST-парсинг невозможен
    """
    for i, line in enumerate(lines, 1):
        stripped_line = line.strip()

        if (not stripped_line or
                stripped_line.startswith('#') or
                stripped_line.startswith(('import ', 'from ')) or
                stripped_line.startswith(('class ', 'def ', 'async def '))):
            continue

        return {
            'line_number': i,
            'code': line
        }

    return None


class EntryPointAnalyzer:
    def __init__(self):
        self.entry_points = []
        self.visited_files = set()
        self.all_python_files = []

    def analyze_project(self, project_path: str) -> List[Dict[str, Any]]:
        """
        Анализирует весь проект и находит точки входа следующих типов:
           1. if __name__ == "__main__" и более сложные условия с and/or
           2. Указанные в setup
           3. Flask(), FastAPI() приложения
           4. Click команды
           5. argparse скрипты
           6. Исполняемые shebang-файлы
           7. Fallback: первая исполняемая строка кода
        """
        project_path = Path(project_path)

        if not project_path.exists():
            raise FileNotFoundError(f"Project path not found: {project_path}")

        self.all_python_files = get_files_in_directory(project_path)
        for file_path in self.all_python_files:
            self.analyze_file(file_path, project_path)

        if not self.entry_points:
            self.find_fallback_entry_points(project_path)

        return self.entry_points

    def analyze_file(self, file_path: Path, project_root: Path) -> None:
        """Анализирует один файл на наличие точек входа"""
        if file_path in self.visited_files:
            return

        self.visited_files.add(file_path)

        try:
            module = parse_file(file_path, attach_parents=True)
            relative_path = file_path.relative_to(project_root)

            self.find_main_guard(module, file_path, relative_path)
            self.find_setup_py_entry_points(file_path, relative_path)
            self.find_fastapi_app(module, file_path, relative_path)
            self.find_django_settings(module, file_path, relative_path)
            self.find_flask_app(module, file_path, relative_path)
            self.find_click_commands(module, file_path, relative_path)
            self.find_argparse_scripts(module, file_path, relative_path)
            self.find_executable_scripts(module, file_path, relative_path)

        except (ASTParseError, SyntaxError) as e:
            print(f"Syntax error in {file_path}: {e}")
        except Exception as e:
            print(f"Error analyzing {file_path}: {e}")

    def find_fallback_entry_points(self, project_root: Path) -> None:
        """
        Fallback-метод: находит первую исполняемую строку кода в каждом файле,
        которая не является импортом, определением класса/функции или комментарием.
        """
        for file_path in self.all_python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                relative_path = file_path.relative_to(project_root)
                first_executable_line = self.find_first_executable_line(file_path, lines)

                if first_executable_line:
                    self.entry_points.append({
                        'type': 'fallback_executable_code',
                        'file': str(relative_path),
                        'line': first_executable_line['line_number'],
                        'description': f"First executable code: {first_executable_line['code'].strip()}",
                        'code_snippet': first_executable_line['code'].strip()
                    })

            except Exception as e:
                print(f"Error in fallback analysis for {file_path}: {e}")

    def find_first_executable_line(self, file_path: Path, lines: List[str]) -> dict[str, int | str] | None:
        """
        Находит первую исполняемую строку кода, которая не является:
        - комментарием
        - импортом
        - определением класса/функции
        - пустой строкой
        """
        try:
            module = parse_file(file_path, attach_parents=True)
            definition_lines = set()
            for node in module.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                    definition_lines.add(node.lineno)
                for decorator in getattr(node, 'decorator_list', []):
                    if hasattr(decorator, 'lineno'):
                        definition_lines.add(decorator.lineno)

            for i, line in enumerate(lines, 1):
                stripped_line = line.strip()

                if not stripped_line or stripped_line.startswith('#'):
                    continue

                if stripped_line.startswith(('import ', 'from ')):
                    continue

                if i in definition_lines:
                    continue

                if stripped_line.startswith(('class ', 'def ', 'async def ')):
                    continue

                return {
                    'line_number': i,
                    'code': line
                }

        except (ASTParseError, SyntaxError, Exception) as e:
            return find_first_executable_line_heuristic(lines)

        return None

    def find_main_guard(self, module: ast.Module, file_path: Path, relative_path: Path) -> None:
        """Ищет стандартную конструкцию if __name__ == '__main__'"""
        for node in module.body:
            if isinstance(node, ast.If):
                test = node.test
                if is_simple_main_guard(test) or self.has_main_guard_in_bool_op(test):
                    self.entry_points.append({
                        'type': 'main_guard',
                        'file': str(relative_path),
                        'line': node.lineno,
                        'description': 'Standard Python entry point (if __name__ == "__main__")',
                    })
                else:
                    break

    def has_main_guard_in_bool_op(self, test_node: ast.AST) -> bool:
        """Проверяет есть ли __name__ == '__main__' в сложных условиях"""
        if isinstance(test_node, ast.BoolOp):
            for value in test_node.values:
                if is_simple_main_guard(value):
                    return True
                elif isinstance(value, ast.BoolOp):
                    if self.has_main_guard_in_bool_op(value):
                        return True
        return False

    def find_setup_py_entry_points(self, file_path: Path, relative_path: Path) -> None:
        """Ищет entry_points в setup.py"""
        if file_path.name == 'setup.py':
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                if 'entry_points' in content:
                    self.entry_points.append({
                        'type': 'setup_py_entry_points',
                        'file': str(relative_path),
                        'line': None,
                        'description': 'Package entry points defined in setup.py'
                    })
            except:
                pass

    def find_fastapi_app(self, module: ast.Module, file_path: Path, relative_path: Path) -> None:
        """Ищет FastAPI приложения"""
        for node in module.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value if hasattr(node, 'value') else None
                if (value and isinstance(value, ast.Call) and
                        isinstance(value.func, ast.Name) and
                        value.func.id == 'FastAPI'):

                    self.entry_points.append({
                        'type': 'fastapi_app',
                        'file': str(relative_path),
                        'line': node.lineno,
                        'description': 'FastAPI application instance'
                    })

    def find_django_settings(self, module: ast.Module, file_path: Path, relative_path: Path) -> None:
        """Ищет Django настройки и manage.py"""
        if file_path.name in ['manage.py', 'wsgi.py', 'asgi.py']:
            self.entry_points.append({
                'type': 'django_entry',
                'file': str(relative_path),
                'line': 1,
                'description': f'Django entry point: {file_path.name}'
            })

    def find_flask_app(self, module: ast.Module, file_path: Path, relative_path: Path) -> None:
        """Ищет Flask приложения"""
        for node in module.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value if hasattr(node, 'value') else None
                if (value and isinstance(value, ast.Call) and
                        isinstance(value.func, ast.Name) and
                        value.func.id == 'Flask'):

                    self.entry_points.append({
                        'type': 'flask_app',
                        'file': str(relative_path),
                        'line': node.lineno,
                        'description': 'Flask application instance'
                    })

    def find_click_commands(self, module: ast.Module, file_path: Path, relative_path: Path) -> None:
        """Ищет Click команды"""
        for node in module.body:
            if (isinstance(node, ast.FunctionDef) and
                    node.decorator_list):

                for decorator in node.decorator_list:
                    if (isinstance(decorator, ast.Call) and
                            isinstance(decorator.func, ast.Attribute) and
                            isinstance(decorator.func.value, ast.Name) and
                            decorator.func.value.id == 'click' and
                            decorator.func.attr == 'command'):

                        self.entry_points.append({
                            'type': 'click_command',
                            'file': str(relative_path),
                            'line': node.lineno,
                            'description': f'Click command: {node.name}'
                        })

    def find_argparse_scripts(self, module: ast.Module, file_path: Path, relative_path: Path) -> None:
        """Ищет скрипты использующие argparse"""
        has_argparse = False
        has_parser_creation = False

        # Проверяем импорт argparse
        for node in module.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if 'argparse' in alias.name:
                        has_argparse = True
                        break

        # Ищем создание парсера
        for node in module.body:
            if (isinstance(node, ast.Assign) and
                    isinstance(node.value, ast.Call) and
                    isinstance(node.value.func, ast.Attribute) and
                    node.value.func.attr == 'ArgumentParser'):

                has_parser_creation = True
                break

        if has_argparse and has_parser_creation:
            self.entry_points.append({
                'type': 'argparse_script',
                'file': str(relative_path),
                'line': None,
                'description': 'Script using argparse for command line interface'
            })

    def find_executable_scripts(self, module: ast.Module, file_path: Path, relative_path: Path) -> None:
        """Ищет исполняемые скрипты по shebang"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()

            if first_line.startswith('#!/usr/bin/env python') or first_line.startswith('#!/usr/bin/python'):
                self.entry_points.append({
                    'type': 'executable_script',
                    'file': str(relative_path),
                    'line': 1,
                    'description': 'Executable script with Python shebang'
                })
        except:
            pass


def main():
    if len(sys.argv) == 1:
        project_path = os.getcwd()
    elif len(sys.argv) == 2:
        project_path = sys.argv[1]
    else:
        sys.exit(1)

    analyzer = EntryPointAnalyzer()

    try:
        entry_points = analyzer.analyze_project(project_path)
        print(entry_points)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()