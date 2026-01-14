import sys
import json
import argparse
from pathlib import Path

from dependency_analyzer import DependencyAnalyzer
from call_flow_analyzer import CallFlowAnalyzer
from serializer import GraphSerializer


def _analyze_once(project_path: str | Path, pretty: bool = False) -> dict:
    project_path = str(project_path)
    da = DependencyAnalyzer(project_path)
    graph = da.create_dependency()

    if isinstance(graph.nodes, dict):
        nodes_dict = graph.nodes
    else:
        nodes_dict = {n.id: n for n in graph.nodes}

    cfa = CallFlowAnalyzer()
    call_edges = cfa.build_edges(
        files=da.files,
        elements=da.elements,
        nodes=nodes_dict,
        project_root=Path(project_path),
    )
    
    import_edges = da._build_import_edges(nodes_dict)
    all_edges = call_edges + import_edges
    graph.edges = all_edges
    
    return GraphSerializer.to_dict(graph)


def _json_loop():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            print(json.dumps({"ok": False, "error": f"Invalid JSON: {e}"}), flush=True)
            continue
        cmd = msg.get("cmd")
        try:
            if cmd == "version":
                print(json.dumps({"ok": True, "version": "1.0"}), flush=True)
            elif cmd == "analyze":
                project_path = msg.get("path") or "."
                pretty = bool(msg.get("pretty", False))
                graph_dict = _analyze_once(project_path, pretty=pretty)
                print(json.dumps({"ok": True, "graph": graph_dict}), flush=True)
            else:
                print(json.dumps({"ok": False, "error": f"Unknown cmd: {cmd}"}), flush=True)
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="code-analyzer", description="Analyze a Python project and output a call/dependency graph as JSON")
    sub = parser.add_subparsers(dest="sub")

    p_an = sub.add_parser("analyze", help="Analyze a project and print graph JSON")
    p_an.add_argument("path", nargs="?", default=".", help="Path to project root (default: current dir)")
    p_an.add_argument("--output", "-o", help="Path to write JSON. If omitted, prints to stdout")
    p_an.add_argument("--pretty", action="store_true", help="Pretty-print JSON")

    sub.add_parser("serve", help="Run simple JSON-over-stdin/stdout protocol")

    args = parser.parse_args(argv)

    if args.sub == "serve" or (args.sub is None and not sys.stdin.isatty()):
        _json_loop()
        return 0

    if args.sub == "analyze" or args.sub is None:
        graph_dict = _analyze_once(args.path, pretty=args.pretty if hasattr(args, "pretty") else False)
        out = json.dumps(graph_dict, indent=2 if getattr(args, "pretty", False) else None, ensure_ascii=False)
        if getattr(args, "output", None):
            Path(args.output).write_text(out, encoding="utf-8")
        else:
            print(out)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())