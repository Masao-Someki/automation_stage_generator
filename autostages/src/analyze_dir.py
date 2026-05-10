import argparse
import ast
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, Union

ARCHIVE_LIKE_EXTS = {
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".sph",
    ".arc",
    ".zst",
    ".lz4",
    ".cab",
    ".rpm",
    ".img",
    ".iso",
    ".bin",
    ".dat",
}

IGNORED_DIR_NAMES = {"__pycache__"}


def summarize_tree(path, max_dirs=5, max_files=100):
    def summarize_dir(current_path) -> Dict[str, Union[list, dict]]:
        summary = {}
        try:
            entries = sorted(os.scandir(current_path), key=lambda e: e.name)
        except Exception as e:
            return {"_error": str(e)}

        dirs = []
        files_by_ext = defaultdict(list)
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                if entry.name in IGNORED_DIR_NAMES:
                    continue
                dirs.append(entry.name)
                continue

            ext = os.path.splitext(entry.name)[1]
            if ext in ARCHIVE_LIKE_EXTS:
                continue
            files_by_ext[ext].append(entry.name)

        bulk_exts = {
            ext for ext, files in files_by_ext.items()
            if ext != ".py" and len(files) >= max_files
        }

        file_summary = {}
        for ext, files in files_by_ext.items():
            tag = "_bulk" if ext in bulk_exts else "_meta"
            display = files if ext == ".py" else files[:5]
            if ext != ".py" and len(files) > 5:
                display.append(f"... and {len(files) - 5} more")
            if tag not in file_summary:
                file_summary[tag] = []
            file_summary[tag].extend(display)

        dir_summaries = {}
        for subdir in dirs[:max_dirs]:
            dir_summaries[subdir] = summarize_dir(os.path.join(current_path, subdir))
        if len(dirs) > max_dirs:
            dir_summaries["_more_dirs"] = f"... and {len(dirs) - max_dirs} more"

        summary.update(dir_summaries)
        summary.update(file_summary)
        return summary

    return summarize_dir(path)


def print_summary_to_string(summary, indent=0) -> str:
    lines = []
    for name, content in summary.items():
        if name == "_bulk":
            for file_name in content:
                lines.append("    " * indent + f"- [bulk] {file_name}")
        elif name == "_meta":
            for file_name in content:
                lines.append("    " * indent + f"- [meta] {file_name}")
        elif name == "_more_dirs":
            lines.append("    " * indent + content)
        elif name == "_error":
            lines.append("    " * indent + f"- [error] {content}")
        else:
            lines.append("    " * indent + f"{name}/")
            lines.append(print_summary_to_string(content, indent + 1))
    return "\n".join(lines)


def read_text_file(file_path: Union[str, Path]) -> str:
    path = Path(file_path)
    with path.open("r", encoding="utf-8", errors="ignore") as file_obj:
        return file_obj.read()


def list_python_files(root_path: Union[str, Path]) -> list[Path]:
    root = Path(root_path)
    python_files = []
    for current_root, dir_names, file_names in os.walk(root):
        dir_names[:] = sorted(
            name for name in dir_names
            if not name.startswith(".") and name not in IGNORED_DIR_NAMES
        )
        for file_name in sorted(file_names):
            if file_name.startswith(".") or not file_name.endswith(".py"):
                continue
            python_files.append(Path(current_root) / file_name)
    return python_files


def extract_python_symbols(file_path: Union[str, Path]) -> dict[str, list[str]]:
    path = Path(file_path)
    source = read_text_file(path)
    tree = ast.parse(source, filename=str(path))

    classes = []
    functions = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)

    return {
        "classes": classes,
        "functions": functions,
    }


def get_symbols_markdown(root_path: Union[str, Path]) -> str:
    root = Path(root_path)
    sections = [f"## Python symbols under: {root}"]
    for file_path in list_python_files(root):
        rel_path = file_path.relative_to(root)
        try:
            symbols = extract_python_symbols(file_path)
        except Exception as exc:
            sections.append(
                f"**{rel_path}**\n- [error] {exc}"
            )
            continue

        sections.append(f"**{rel_path}**")
        if symbols["classes"]:
            sections.append("- classes: " + ", ".join(symbols["classes"]))
        if symbols["functions"]:
            sections.append("- functions: " + ", ".join(symbols["functions"]))
        if not symbols["classes"] and not symbols["functions"]:
            sections.append("- no top-level classes or functions")
    return "\n".join(sections)


def get_python_overview_markdown(root_path: Union[str, Path]) -> str:
    tree_markdown = get_tree_markdown(root_path)
    symbols_markdown = get_symbols_markdown(root_path)
    return tree_markdown + "\n\n" + symbols_markdown


def get_tree_markdown(download_path):
    tree = summarize_tree(download_path, max_dirs=5, max_files=100)
    tree_output = print_summary_to_string(tree)
    return f"""## Analyzed directory: {download_path}
**tree**
```
{tree_output}
```"""


def get_file_markdown(file_path):
    content = read_text_file(file_path)
    return f"""## Analyzed file: {file_path}
```text
{content}
```"""


def get_markdown(target_path, mode="tree"):
    if mode == "tree":
        return get_tree_markdown(target_path)
    if mode == "symbols":
        return get_symbols_markdown(target_path)
    if mode == "python-overview":
        return get_python_overview_markdown(target_path)
    if mode == "file":
        return get_file_markdown(target_path)
    raise ValueError(f"Unknown mode: {mode}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze a directory tree or print a file.")
    parser.add_argument("path", help="Target directory or file path")
    parser.add_argument(
        "--mode",
        choices=("tree", "symbols", "python-overview", "file"),
        default="tree",
        help="Choose whether to summarize a directory tree, list Python symbols, print both, or print a file",
    )
    args = parser.parse_args()
    print(get_markdown(args.path, mode=args.mode))
