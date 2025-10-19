import ast
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from entry_point_analyzer import EntryPointAnalyzer

class TestEntryPointAnalyzer:
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.analyzer = EntryPointAnalyzer()
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir)

    def teardown_method(self):
        """Очистка после каждого теста"""
        import shutil
        shutil.rmtree(self.temp_dir)

    def _create_test_file(self, filename: str, content: str) -> Path:
        """Создает тестовый файл с указанным содержимым"""
        file_path = self.project_path / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')
        return file_path

    def test_find_main_guard(self):
        """Тест поиска стандартной конструкции if __name__ == '__main__'"""
        content = '''
def main():
    print("Hello World")

if __name__ == "__main__":
    main()
'''
        self._create_test_file("main_script.py", content)
        module = ast.parse(content)

        self.analyzer.find_main_guard(module, self.project_path / "main_script.py", Path("main_script.py"))

        assert len(self.analyzer.entry_points) == 1
        ep = self.analyzer.entry_points[0]
        assert ep['type'] == 'main_guard'
        assert ep['file'] == "main_script.py"

    def test_find_main_guard_variations(self):
        """Тест различных вариантов main guard"""
        variations = [
            "if __name__ == '__main__':",
            "if __name__ == \"__main__\":",
            "if __name__  ==  '__main__' :",
        ]

        for i, guard in enumerate(variations):
            content = f'''
def func():
    pass

{guard}
    func()
'''
            self._create_test_file(f"main_{i}.py", content)
            module = ast.parse(content)
            self.analyzer.find_main_guard(module, self.project_path / f"main_{i}.py", Path(f"main_{i}.py"))

        assert len(self.analyzer.entry_points) == len(variations)

    def test_no_main_guard(self):
        """Тест файла без main guard"""
        content = '''
def hello():
    print("Hello")

hello()
'''
        self._create_test_file("no_main.py", content)
        module = ast.parse(content)

        self.analyzer.find_main_guard(module, self.project_path / "no_main.py", Path("no_main.py"))

        assert len(self.analyzer.entry_points) == 0

    def test_find_fastapi_app(self):
        """Тест поиска FastAPI приложения"""
        content = '''
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}
'''
        self._create_test_file("fastapi_app.py", content)
        module = ast.parse(content)

        self.analyzer.find_fastapi_app(module, self.project_path / "fastapi_app.py", Path("fastapi_app.py"))

        assert len(self.analyzer.entry_points) == 1
        ep = self.analyzer.entry_points[0]
        assert ep['type'] == 'fastapi_app'
        assert ep['description'] == 'FastAPI application instance'

    def test_find_flask_app(self):
        """Тест поиска Flask приложения"""
        content = '''
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello World!"
'''
        self._create_test_file("flask_app.py", content)
        module = ast.parse(content)

        self.analyzer.find_flask_app(module, self.project_path / "flask_app.py", Path("flask_app.py"))

        assert len(self.analyzer.entry_points) == 1
        ep = self.analyzer.entry_points[0]
        assert ep['type'] == 'flask_app'

    def test_find_click_commands(self):
        """Тест поиска Click команд"""
        content = '''
import click

@click.command()
def hello():
    """Simple program that greets NAME."""
    click.echo("Hello World!")

@click.group()
def cli():
    """Main CLI group"""
    pass

@cli.command()
def subcommand():
    """A subcommand"""
    click.echo("Subcommand")
'''
        self._create_test_file("click_app.py", content)
        module = ast.parse(content)

        self.analyzer.find_click_commands(module, self.project_path / "click_app.py", Path("click_app.py"))

        assert len(self.analyzer.entry_points) >= 1
        click_commands = [ep for ep in self.analyzer.entry_points if ep['type'] == 'click_command']
        assert len(click_commands) >= 1

    def test_find_argparse_scripts(self):
        """Тест поиска argparse скриптов"""
        content = '''
import argparse

parser = argparse.ArgumentParser(description='Test script')
parser.add_argument('--input', help='Input file')
args = parser.parse_args()
'''
        self._create_test_file("argparse_script.py", content)
        module = ast.parse(content)

        self.analyzer.find_argparse_scripts(module, self.project_path / "argparse_script.py", Path("argparse_script.py"))

        assert len(self.analyzer.entry_points) == 1
        ep = self.analyzer.entry_points[0]
        assert ep['type'] == 'argparse_script'

    def test_find_executable_scripts(self):
        """Тест поиска исполняемых скриптов по shebang"""
        content = '''#!/usr/bin/env python3
print("Hello World")
'''
        self._create_test_file("executable_script.py", content)
        module = ast.parse("") 

        self.analyzer.find_executable_scripts(module, self.project_path / "executable_script.py", Path("executable_script.py"))

        assert len(self.analyzer.entry_points) == 1
        ep = self.analyzer.entry_points[0]
        assert ep['type'] == 'executable_script'
        assert ep['file'] == "executable_script.py"
        assert ep['line'] == 1

    def test_find_django_entry_points(self):
        """Тест поиска Django точек входа"""
        for filename in ['manage.py', 'wsgi.py', 'asgi.py']:
            content = f'''
#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
'''
            self._create_test_file(filename, content)
            module = ast.parse(content)

            self.analyzer.find_django_settings(module, self.project_path / filename, Path(filename))

        django_entries = [ep for ep in self.analyzer.entry_points if ep['type'] == 'django_entry']
        assert len(django_entries) == 3

    def test_find_setup_py_entry_points(self):
        """Тест поиска entry_points в setup.py"""
        content = '''
from setuptools import setup, find_packages

setup(
    name="test-package",
    version="1.0",
    packages=find_packages(),
    entry_points={
        'console_scripts': [
            'my_command=my_package.cli:main',
        ],
    },
)
'''
        self._create_test_file("setup.py", content)

        with patch('pathlib.Path.read_text') as mock_read:
            mock_read.return_value = content
            self.analyzer.find_setup_py_entry_points(
                self.project_path / "setup.py",
                Path("setup.py")
            )

        assert len(self.analyzer.entry_points) == 1
        ep = self.analyzer.entry_points[0]
        assert ep['type'] == 'setup_py_entry_points'

    def test_analyze_project_integration(self):
        """Интеграционный тест анализа всего проекта"""
        test_files = {
            "main_app.py": '''
if __name__ == "__main__":
    print("Main app")
''',
            "web_app.py": '''
from fastapi import FastAPI
app = FastAPI()
''',
            "cli_tool.py": '''
import click

@click.command()
def cli():
    print("CLI tool")
''',
            "subpackage/__init__.py": "",
            "subpackage/utils.py": '''
# Утилиты без точки входа
def helper():
    pass
''',
        }

        for filename, content in test_files.items():
            self._create_test_file(filename, content)

        entry_points = self.analyzer.analyze_project(self.temp_dir)

        assert len(entry_points) >= 3

        types_found = {ep['type'] for ep in entry_points}
        expected_types = {'main_guard', 'fastapi_app', 'click_command'}
        assert expected_types.issubset(types_found)

    def test_error_handling(self):
        """Тест обработки ошибок при анализе"""
        self._create_test_file("syntax_error.py", 'if __name__ == "__main__" \n    pass')  # Нет двоеточия

        self._create_test_file("good_script.py", 'if __name__ == "__main__": pass')

        entry_points = self.analyzer.analyze_project(self.temp_dir)

        assert len(entry_points) == 1
        assert entry_points[0]['file'] == "good_script.py"

    def test_file_not_found(self):
        """Тест обработки несуществующего пути"""
        with pytest.raises(FileNotFoundError):
            self.analyzer.analyze_project("/non/existent/path")

    def test_empty_project(self):
        """Тест анализа пустого проекта"""
        empty_dir = self.project_path / "empty"
        empty_dir.mkdir()

        entry_points = self.analyzer.analyze_project(empty_dir)

        assert len(entry_points) == 0

    def test_complex_main_guard(self):
        """Тест сложных вариантов main guard"""
        complex_cases = [
            '''
if __name__ == "__main__" and len(sys.argv) > 1:
    main()
''',
            '''
import sys

def setup():
    pass

if __name__ == "__main__":
    setup()

def cleanup():
    pass
''',
        ]

        for i, case in enumerate(complex_cases):
            self._create_test_file(f"complex_{i}.py", case)
            module = ast.parse(case)
            self.analyzer.find_main_guard(module, self.project_path / f"complex_{i}.py", Path(f"complex_{i}.py"))

        assert len(self.analyzer.entry_points) == len(complex_cases)

    def test_fallback(self):
        """Тест, когда явные точки входа не найдены"""
        case = '''
    def func():
        pass
    #some comment
    func()
    '''
        self._create_test_file("fallback.py", case)
        self.analyzer.analyze_project(self.temp_dir)
    
        assert len(self.analyzer.entry_points) == 1