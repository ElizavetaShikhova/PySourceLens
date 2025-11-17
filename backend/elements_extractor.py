from __future__ import annotations

import ast
from dataclasses import asdict
from typing import Any, Union

from models import ArgInfo, FunctionInfo, VariableInfo, ClassInfo


def extract_elements(
        tree: ast.Module,
        *,
        module_name: str | None,
        file_path: str | None,
) -> dict[str, Any]:
    if not isinstance(tree, ast.Module):
        raise TypeError("extract_elements: expected ast.Module")

    top_classes: list[ClassInfo] = []
    top_functions: list[FunctionInfo] = []
    module_vars: list[VariableInfo] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            top_classes.append(_extract_class(node, qual_prefix=module_name or ""))

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_functions.append(_extract_function(node, qual_prefix=module_name or "", inside_class=False))

        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    module_vars.append(
                        VariableInfo(
                            target=t.id,
                            annotation=None,
                            value_preview=_safe_unparse(node.value),
                            scope="module",
                            loc=_loc(node),
                        )
                    )
        elif isinstance(node, ast.AnnAssign):
            t = node.target
            if isinstance(t, ast.Name):
                module_vars.append(
                    VariableInfo(
                        target=t.id,
                        annotation=_safe_unparse(node.annotation),
                        value_preview=_safe_unparse(node.value) if node.value is not None else None,
                        scope="module",
                        loc=_loc(node),
                    )
                )
        else:
            pass

    module_doc = ast.get_docstring(tree)
    result: dict[str, Any] = {
        "module": {
            "name": module_name or "<module>",
            "path": file_path,
            "docstring": module_doc,
            "loc": _loc(tree),
        },
        "classes": [asdict(ci) for ci in top_classes],
        "functions": [asdict(fi) for fi in top_functions],
        "variables": [asdict(vi) for vi in module_vars],
    }
    return result


def _loc(n: ast.AST) -> dict[str, int | None]:
    return {
        "start_line": getattr(n, "lineno", None),
        "start_col": getattr(n, "col_offset", None),
        "end_line": getattr(n, "end_lineno", None),
        "end_col": getattr(n, "end_col_offset", None),
    }


def _safe_unparse(n: ast.AST | None) -> str | None:
    if n is None:
        return None
    try:
        return ast.unparse(n)  # py>=3.9
    except Exception:
        return n.__class__.__name__


def _decorator_names(decos: list[ast.expr]) -> list[str]:
    names: list[str] = []
    for d in decos:
        try:
            names.append(ast.unparse(d))
        except Exception:
            if isinstance(d, ast.Name):
                names.append(d.id)
            elif isinstance(d, ast.Attribute):
                parts = []
                cur: ast.AST | None = d
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    parts.append(cur.id)
                names.append(".".join(reversed(parts)))
            else:
                names.append(d.__class__.__name__)
    return names


def _visibility(name: str) -> str:
    if name.startswith("__") and name.endswith("__"):
        return "magic"
    if name.startswith("_"):
        return "private"
    return "public"


def _collect_args(a: ast.arguments) -> tuple[list[ArgInfo], str]:
    args: list[ArgInfo] = []

    def add_args(seq: list[ast.arg], defaults_seq: list[ast.expr]):
        n = len(seq)
        d = len(defaults_seq)
        for i, arg in enumerate(seq):
            has_def = i >= (n - d) if d else False
            args.append(
                ArgInfo(
                    name=arg.arg,
                    annotation=_safe_unparse(arg.annotation),
                    has_default=has_def,
                )
            )

    posonly = getattr(a, "posonlyargs", [])
    add_args(posonly, [])
    add_args(a.args, a.defaults or [])

    if a.vararg:
        args.append(ArgInfo(name="*" + a.vararg.arg, annotation=_safe_unparse(a.vararg.annotation), has_default=False))

    for kw, dflt in zip(a.kwonlyargs, a.kw_defaults or [None] * len(a.kwonlyargs)):
        args.append(ArgInfo(name=kw.arg, annotation=_safe_unparse(kw.annotation), has_default=dflt is not None))

    if a.kwarg:
        args.append(ArgInfo(name="**" + a.kwarg.arg, annotation=_safe_unparse(a.kwarg.annotation), has_default=False))

    try:
        sig = "(" + ", ".join(
            ai.name + (": " + ai.annotation if ai.annotation else "") + ("=…" if ai.has_default else "")
            for ai in args) + ")"
    except Exception:
        sig = "(...)"

    return args, sig


def _collect_instance_attrs(func_node: Union[ast.FunctionDef, ast.AsyncFunctionDef], class_qualname: str) -> list[
    VariableInfo]:
    results: list[VariableInfo] = []

    class SelfAssignVisitor(ast.NodeVisitor):
        def visit_Assign(self, node: ast.Assign) -> None:
            for t in node.targets:
                if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                    results.append(
                        VariableInfo(
                            target=t.attr,
                            annotation=None,
                            value_preview=_safe_unparse(node.value),
                            scope="instance",
                            loc=_loc(node),
                        )
                    )

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
            t = node.target
            if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self":
                results.append(
                    VariableInfo(
                        target=t.attr,
                        annotation=_safe_unparse(node.annotation),
                        value_preview=_safe_unparse(node.value) if node.value is not None else None,
                        scope="instance",
                        loc=_loc(node),
                    )
                )

    SelfAssignVisitor().visit(func_node)
    return results


def _function_kind(decorators: list[str], is_async: bool, is_inside_class: bool) -> str:
    decos = set(decorators)
    base_names = set(d.split("(")[0] for d in decos)
    if "staticmethod" in base_names:
        return "async_method" if is_async else "static_method"
    if "classmethod" in base_names:
        return "async_method" if is_async else "class_method"
    if any(n.endswith(".setter") or n.endswith(".getter") or n == "property" for n in base_names):
        return "async_method" if is_async else "property"
    if is_inside_class:
        return "async_method" if is_async else "method"
    return "async_function" if is_async else "function"


def _extract_function(node: Union[ast.FunctionDef, ast.AsyncFunctionDef], qual_prefix: str, *,
                      inside_class: bool) -> FunctionInfo:
    decorators = _decorator_names(node.decorator_list)
    args, _sig = _collect_args(node.args)
    returns = _safe_unparse(node.returns)
    ds = ast.get_docstring(node)
    async_ = isinstance(node, ast.AsyncFunctionDef)
    kind = _function_kind(decorators, async_, inside_class)
    qn = f"{qual_prefix}.{node.name}" if qual_prefix else node.name

    nested: list[FunctionInfo] = []
    for b in node.body:
        if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nested.append(_extract_function(b, qn, inside_class=False))

    return FunctionInfo(
        name=node.name,
        qualname=qn,
        kind=kind,
        visibility=_visibility(node.name),
        async_=async_,
        decorators=decorators,
        returns=returns,
        args=args,
        docstring=ds,
        loc=_loc(node),
        nested_functions=nested,
    )


def _extract_class(node: ast.ClassDef, qual_prefix: str) -> ClassInfo:
    qn = f"{qual_prefix}.{node.name}" if qual_prefix else node.name
    bases = [_safe_unparse(b) for b in node.bases]
    decorators = _decorator_names(node.decorator_list)
    ds = ast.get_docstring(node)

    class_attrs: list[VariableInfo] = []
    instance_attrs: list[VariableInfo] = []
    methods: list[FunctionInfo] = []

    for b in node.body:
        if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
            finfo = _extract_function(b, qn, inside_class=True)
            methods.append(finfo)
            instance_attrs.extend(_collect_instance_attrs(b, qn))
        elif isinstance(b, ast.Assign):
            for t in b.targets:
                if isinstance(t, ast.Name):
                    class_attrs.append(
                        VariableInfo(
                            target=t.id,
                            annotation=None,
                            value_preview=_safe_unparse(b.value),
                            scope="class",
                            loc=_loc(b),
                        )
                    )
        elif isinstance(b, ast.AnnAssign):
            target = b.target
            if isinstance(target, ast.Name):
                class_attrs.append(
                    VariableInfo(
                        target=target.id,
                        annotation=_safe_unparse(b.annotation),
                        value_preview=_safe_unparse(b.value) if b.value is not None else None,
                        scope="class",
                        loc=_loc(b),
                    )
                )

    instance_attrs = _dedup_instance_attrs(instance_attrs)

    return ClassInfo(
        name=node.name,
        qualname=qn,
        visibility=_visibility(node.name),
        bases=[b for b in bases if b],
        decorators=decorators,
        docstring=ds,
        loc=_loc(node),
        class_attributes=class_attrs,
        instance_attributes=instance_attrs,
        methods=methods,
    )


def _dedup_instance_attrs(attrs: list[VariableInfo]) -> list[VariableInfo]:
    by_name: dict[str, VariableInfo] = {}
    for v in attrs:
        if v.target not in by_name:
            by_name[v.target] = v
        else:
            prev = by_name[v.target]
            if prev.annotation is None and v.annotation is not None:
                prev.annotation = v.annotation
    return list(by_name.values())
