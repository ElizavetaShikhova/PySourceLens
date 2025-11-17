import ast
import sys
import tokenize
from pathlib import Path
from typing import Iterable

from ASTParseError import ASTParseError


def parse_source(source: str, filename: str = "<string>", *, attach_parents: bool = True,
                 type_comments: bool = True) -> ast.Module:
    try:
        tree = ast.parse(source, filename=filename, mode="exec", type_comments=type_comments)
    except SyntaxError as e:
        raise ASTParseError(e.msg, filename=e.filename or filename, lineno=e.lineno, col=e.offset)

    if attach_parents:
        set_parent_pointers(tree)

    return tree


def parse_file(file_path: str | Path, *, attach_parents: bool = True, type_comments: bool = True) -> ast.Module:
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f'File not found: "{path}"')

    source = _read_source(path)
    return parse_source(source, filename=str(path), attach_parents=attach_parents, type_comments=type_comments)


def iter_child_nodes(node: ast.AST) -> Iterable[ast.AST]:
    return ast.iter_child_nodes(node)


def set_parent_pointers(root: ast.AST) -> None:
    for parent in ast.walk(root):
        for child in iter_child_nodes(parent):
            setattr(child, "parent", parent)


def _read_source(path: Path) -> str:
    with tokenize.open(str(path)) as f:
        return f.read()


if __name__ == "__main__":
    # python ast_parser.py path/to/file.py
    module = parse_file(sys.argv[1])
    print(ast.dump(module, indent=2, include_attributes=True))
