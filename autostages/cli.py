import argparse
import importlib.util
import inspect
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any
import time
import uuid

import tty
import termios
import tomllib

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.prompt import Prompt
from rich.text import Text

from autostages.src.stages.abs_stage import AbsStage
from autostages.src.orchestration import build_worker_command, submit_job, poll_job
from autostages.src.utils import load_resource

DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "o4-mini-2025-04-16"
APP_DIRNAME = ".autosearch"


def detect_default_codex_model() -> str:
    config_path = Path.home() / ".codex" / "config.toml"
    if not config_path.exists():
        return "gpt-5.4"
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return "gpt-5.4"
    return config.get("model", "gpt-5.4")


DEFAULT_CODEX_CLI_MODEL = detect_default_codex_model()


DEFAULT_SESSION = {
    "menu_action": "1",
    "generation_backend": "codex_cli",
    "stage_script": None,
}
DEFAULT_APP_CONFIG = {
    "models": {
        "stage_execution_openai": "o4-mini-2025-04-16",
        "stage_execution_gemini": "gemini-pro",
        "stage_execution_codex": DEFAULT_CODEX_CLI_MODEL,
        "stage_execution_claude": "claude-sonnet-4-20250514",
        "codex_cli": DEFAULT_CODEX_CLI_MODEL,
        "openai_api": "o4-mini-2025-04-16",
        "google_api": "gemini-pro",
        "claude_cli": "sonnet",
        "claude_api": "claude-sonnet-4-20250514",
    },
    "orchestration": {
        "executor_type": "local",
        "poll_interval_sec": 10.0,
        "max_stage_steps": 100,
        "slurm": {
            "partition": None,
            "cpus_per_task": 1,
            "mem": None,
            "time": None,
        },
    },
}
START_NODE = "Start"
END_NODE = "End"
GENERATION_BACKENDS = [
    ("codex_cli", "Codex CLI"),
    ("claude_cli", "Claude CLI"),
    ("openai_api", "OpenAI API"),
    ("google_api", "Google API"),
    ("claude_api", "Claude API"),
]

console = Console()


def get_runtime_dirs() -> dict[str, Path]:
    current_dir = Path.cwd().resolve()
    app_dir = current_dir / APP_DIRNAME
    legacy_dirs = [current_dir / ".autostages", current_dir / ".autoespnet3"]
    if not app_dir.exists():
        for legacy_app_dir in legacy_dirs:
            if legacy_app_dir.exists():
                legacy_app_dir.rename(app_dir)
                break
    cache_dir = app_dir / "cache"
    store_dir = app_dir / "store"
    config_path = app_dir / "config.json"
    stages_dir = app_dir / "stages"
    src_dir = app_dir / "src"
    generated_stages_dir = src_dir / "stages"
    session_path = cache_dir / "session.json"
    app_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    store_dir.mkdir(parents=True, exist_ok=True)
    stages_dir.mkdir(parents=True, exist_ok=True)
    src_dir.mkdir(parents=True, exist_ok=True)
    generated_stages_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "__init__.py").touch()
    (generated_stages_dir / "__init__.py").touch()
    return {
        "current_dir": current_dir,
        "app_dir": app_dir,
        "cache_dir": cache_dir,
        "store_dir": store_dir,
        "config_path": config_path,
        "stages_dir": stages_dir,
        "src_dir": src_dir,
        "generated_stages_dir": generated_stages_dir,
        "session_path": session_path,
    }


def init_workspace(runtime_dirs: dict[str, Path]) -> None:
    load_app_config(runtime_dirs["config_path"])
    console.print(f"[green]Initialized[/green] {runtime_dirs['app_dir']}")


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def auto_detect_provider() -> str:
    openai_key = os.environ.get("OPENAI_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if openai_key and not gemini_key:
        return "openai"
    if gemini_key and not openai_key:
        return "gemini"
    if anthropic_key and not openai_key and not gemini_key:
        return "claude"
    return None


def camel_to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def get_initial_messages(runtime_dirs: dict[str, Path]) -> list[dict]:
    return [
        {"role": "user", "content": load_resource("system_prompt.md")},
        {
            "role": "user",
            "content": f"Current working directory: {runtime_dirs['current_dir']}",
        },
    ]


def load_session(session_path: Path) -> dict[str, Any]:
    if not session_path.exists():
        return dict(DEFAULT_SESSION)
    try:
        data = json.loads(session_path.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_SESSION)
    return {**DEFAULT_SESSION, **data}


def load_app_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        save_app_config(config_path, dict(DEFAULT_APP_CONFIG))
        return dict(DEFAULT_APP_CONFIG)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_APP_CONFIG)

    config = dict(DEFAULT_APP_CONFIG)
    merged_models = {
        **DEFAULT_APP_CONFIG["models"],
        **data.get("models", {}),
    }
    config["models"] = merged_models
    config["orchestration"] = {
        **DEFAULT_APP_CONFIG["orchestration"],
        **data.get("orchestration", {}),
    }
    default_slurm = DEFAULT_APP_CONFIG["orchestration"]["slurm"]
    data_slurm = data.get("orchestration", {}).get("slurm", {})
    config["orchestration"]["slurm"] = {
        **default_slurm,
        **data_slurm,
    }

    # Persist schema migrations so existing config.json gains newly added keys.
    if data.get("models", {}) != merged_models or data.get("orchestration", {}) != config["orchestration"]:
        save_app_config(config_path, config)
    return config


def save_session(session_path: Path, session: dict[str, Any]) -> None:
    session_path.write_text(
        json.dumps(session, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def save_app_config(config_path: Path, config: dict[str, Any]) -> None:
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_menu_key() -> str:
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        first = sys.stdin.read(1)
        if first == "\x1b":
            second = sys.stdin.read(1)
            third = sys.stdin.read(1)
            return first + second + third
        return first
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def choose_from_menu(
    title: str,
    options: list[tuple[str, str]],
    default_value: str | None = None,
) -> str:
    if not sys.stdin.isatty():
        if default_value is not None:
            return default_value
        return options[0][0]

    values = [value for value, _ in options]
    selected_index = values.index(default_value) if default_value in values else 0

    while True:
        clear_screen()
        console.print(f"[bold]{title}[/bold]")
        console.print("[dim]Use Up/Down and Enter.[/dim]\n")
        for index, (_, label) in enumerate(options):
            prefix = "›" if index == selected_index else " "
            style = "bold cyan" if index == selected_index else "white"
            console.print(Text(f"{prefix} {label}", style=style))

        key = read_menu_key()
        if key in {"\x1b[A", "k"}:
            selected_index = (selected_index - 1) % len(options)
            continue
        if key in {"\x1b[B", "j"}:
            selected_index = (selected_index + 1) % len(options)
            continue
        if key in {"\r", "\n"}:
            return options[selected_index][0]


def choose_menu_action(session: dict[str, Any]) -> str:
    return choose_from_menu(
        "autostages",
        [
            ("1", "Run stage flow"),
            ("2", "Generate Python scripts from stage markdown"),
            ("3", "Check graph.json"),
        ],
        default_value=session.get("menu_action", DEFAULT_SESSION["menu_action"]),
    )


def choose_path(
    paths: list[Path],
    prompt_text: str,
    default_name: str | None = None,
) -> Path | None:
    if not paths:
        return None
    selected_name = choose_from_menu(
        prompt_text,
        [(path.name, path.name) for path in paths],
        default_value=default_name if default_name else paths[0].name,
    )
    for path in paths:
        if path.name == selected_name:
            return path
    return None


def choose_generation_backend(session: dict[str, Any]) -> str:
    return choose_from_menu(
        "Generation backend",
        GENERATION_BACKENDS,
        default_value=session.get("generation_backend", DEFAULT_SESSION["generation_backend"]),
    )


def parse_stage_header(markdown_path: Path) -> dict[str, str]:
    header_values: dict[str, str] = {}
    in_header = False
    for raw_line in markdown_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line == "## Header":
            in_header = True
            continue
        if in_header and line.startswith("## "):
            break
        if not in_header or not line.startswith("- "):
            continue
        key, _, value = line[2:].partition(":")
        if not _:
            continue
        header_values[key.strip()] = value.strip().strip("`")
    return header_values


def build_stage_specs(runtime_dirs: dict[str, Path]) -> dict[str, dict[str, str]]:
    specs: dict[str, dict[str, str]] = {}
    for markdown_path in sorted(runtime_dirs["stages_dir"].glob("*.md")):
        header = parse_stage_header(markdown_path)
        stage_name = header.get("Stage Name", markdown_path.stem)
        specs[stage_name] = header
    return specs


def build_stage_graph_data(specs: dict[str, dict[str, str]]) -> dict[str, Any]:
    nodes = sorted(specs.keys())
    normal_edges: list[dict[str, str]] = []
    loop_edges: list[dict[str, str]] = []
    transitions: dict[str, dict[str, str | None]] = {}

    for stage_name, header in specs.items():
        previous_stage = header.get("Previous Stage")
        if previous_stage:
            normal_edges.append(
                {
                    "from": previous_stage,
                    "to": stage_name,
                    "type": "previous_to_stage",
                }
            )

        on_success = header.get("On Success")
        if on_success:
            normal_edges.append(
                {
                    "from": stage_name,
                    "to": on_success,
                    "type": "on_success",
                }
            )

        on_incomplete = header.get("On Incomplete")
        if on_incomplete:
            loop_edges.append(
                {
                    "from": stage_name,
                    "to": on_incomplete,
                    "type": "on_incomplete",
                }
            )

        transitions[stage_name] = {
            "on_success": on_success,
            "on_incomplete": on_incomplete,
            "end_condition": header.get("End Condition"),
        }

    return {
        "nodes": nodes,
        "normal_edges": normal_edges,
        "loop_edges": loop_edges,
        "transitions": transitions,
    }


def regenerate_graph_from_markdown(runtime_dirs: dict[str, Path]) -> Path | None:
    specs = build_stage_specs(runtime_dirs)
    if not specs:
        return None
    graph_data = build_stage_graph_data(specs)
    output_path = runtime_dirs["app_dir"] / "graph.json"
    output_path.write_text(
        json.dumps(graph_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def resolve_graph_path(runtime_dirs: dict[str, Path]) -> Path | None:
    user_graph = runtime_dirs["app_dir"] / "graph.json"
    builtin_graph = Path(__file__).resolve().parent / "graph.json"
    if user_graph.exists():
        return user_graph
    if builtin_graph.exists():
        return builtin_graph
    return None


def load_stage_graph(runtime_dirs: dict[str, Path]) -> dict[str, Any]:
    graph_path = resolve_graph_path(runtime_dirs)
    if graph_path is None:
        return {
            "nodes": [],
            "normal_edges": [],
            "loop_edges": [],
            "transitions": {},
            "_path": None,
        }

    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    if not isinstance(graph, dict):
        raise ValueError(f"Graph must be a JSON object: {graph_path}")
    graph["_path"] = str(graph_path)
    for key, default in {
        "nodes": [],
        "normal_edges": [],
        "loop_edges": [],
        "transitions": {},
    }.items():
        graph.setdefault(key, default)
    return graph


def find_cycle(edges: dict[str, set[str]]) -> list[str] | None:
    visited: set[str] = set()
    active: list[str] = []
    active_set: set[str] = set()

    def dfs(node: str) -> list[str] | None:
        visited.add(node)
        active.append(node)
        active_set.add(node)

        for neighbor in sorted(edges.get(node, set())):
            if neighbor not in visited:
                cycle = dfs(neighbor)
                if cycle:
                    return cycle
            elif neighbor in active_set:
                cycle_start = active.index(neighbor)
                return active[cycle_start:] + [neighbor]

        active.pop()
        active_set.remove(node)
        return None

    for node in sorted(edges):
        if node not in visited:
            cycle = dfs(node)
            if cycle:
                return cycle
    return None


def validate_stage_graph(runtime_dirs: dict[str, Path]) -> None:
    graph = load_stage_graph(runtime_dirs)
    graph_path = graph.get("_path")
    if not graph.get("nodes"):
        return

    edges: dict[str, set[str]] = defaultdict(set)
    for edge in graph.get("normal_edges", []):
        src = edge.get("from")
        dst = edge.get("to")
        if not src or not dst:
            continue
        if src == START_NODE or dst == END_NODE:
            continue
        edges[src].add(dst)

    cycle = find_cycle(edges)
    if cycle:
        cycle_text = " -> ".join(cycle)
        raise ValueError(f"Stage graph is not a DAG on normal edges: {cycle_text}")

    console.print("[green]Stage graph check passed[/green] (normal edges form a DAG)")
    if graph_path:
        console.print(f"[green]Using graph[/green] {graph_path}")
    loop_edges = graph.get("loop_edges", [])
    if loop_edges:
        loop_text = ", ".join(f"{edge.get('from')} -> {edge.get('to')}" for edge in loop_edges)
        console.print(f"[cyan]Loop edges[/cyan]: {loop_text}")


def create_provider(provider_name: str, model_name: str):
    if provider_name == "openai":
        from autostages.src.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(model=model_name)
    if provider_name == "gemini":
        from autostages.src.providers.gemini_provider import GeminiProvider

        return GeminiProvider(model=model_name)
    if provider_name == "codex":
        from autostages.src.providers.codex_provider import CodexProvider

        return CodexProvider(model=model_name)
    if provider_name == "claude":
        from autostages.src.providers.claude_provider import ClaudeProvider

        return ClaudeProvider(model=model_name)
    raise ValueError(f"Unknown provider: {provider_name}")


def create_generation_provider(backend_name: str, model_name: str):
    if backend_name == "openai_api":
        return create_provider("openai", model_name)
    if backend_name == "google_api":
        return create_provider("gemini", model_name)
    raise ValueError(f"Unsupported API backend: {backend_name}")


def resolve_execution_model(
    provider_name: str,
    cli_model: str | None,
    app_config: dict[str, Any],
) -> str:
    if cli_model:
        return cli_model
    if provider_name == "openai":
        return app_config["models"]["stage_execution_openai"]
    if provider_name == "gemini":
        return app_config["models"]["stage_execution_gemini"]
    if provider_name == "codex":
        return app_config["models"]["stage_execution_codex"]
    if provider_name == "claude":
        return app_config["models"]["stage_execution_claude"]
    return DEFAULT_MODEL


def resolve_generation_model(
    backend_name: str,
    cli_model: str | None,
    app_config: dict[str, Any],
) -> str | None:
    if cli_model:
        return cli_model
    return app_config["models"].get(backend_name, DEFAULT_MODEL)


def create_stage_markdown(runtime_dirs: dict[str, Path]) -> None:
    stage_name = Prompt.ask("Stage class name", default="NewStage")
    previous_stage = Prompt.ask("Previous Stage", default="None")
    start_condition = Prompt.ask("Start Condition", default="Previous stage has completed.")
    end_condition = Prompt.ask("End Condition", default="This stage appends its result to messages.")
    purpose = Prompt.ask("Purpose", default="Describe this stage briefly.")

    markdown = f"""# Stage: {stage_name}

## Header
- Stage Name: `{stage_name}`
- Stage Id: `{camel_to_snake(stage_name).replace('_stage', '')}`
- Previous Stage: `{previous_stage}`
- Start Condition: {start_condition}
- End Condition: {end_condition}

## Purpose
{purpose}

## Behavior
1. Describe the first step.
2. Describe the main processing.
3. Describe what is appended to `messages`.
4. Describe any cache artifact written under `self.cache_path`.
5. Return the updated `messages`.

## Artifacts
- none required

## Notes
- Follow the implementation style under `autostages/resources/stage_references`.
- Inherit from `AbsStage`.
- Keep `run_body` minimal and linear.
"""
    output_path = runtime_dirs["stages_dir"] / f"{stage_name}.md"
    output_path.write_text(markdown, encoding="utf-8")
    console.print(f"[green]Created[/green] {output_path}")


def build_stage_generation_prompt(stage_spec: str, stage_name: str) -> str:
    abs_stage_code = (Path(__file__).parent / "src/stages/abs_stage.py").read_text(encoding="utf-8")
    analyze_stage_code = (Path(__file__).parent / "src/stages/analyze_dir_stage.py").read_text(encoding="utf-8")
    old_stage_dir = Path(__file__).parent / "resources/stage_references"
    old_stage_references = []
    for old_stage_path in sorted(old_stage_dir.glob("*.py")):
        old_stage_code = old_stage_path.read_text(encoding="utf-8")
        old_stage_references.append(
            f"Reference: {old_stage_path.name}\n```python\n{old_stage_code}\n```"
        )
    old_stage_reference_text = "\n\n".join(old_stage_references)
    end_condition_requirement = (
        "- You MUST implement `evaluate_end_condition(self, runtime_dirs, messages) -> bool` for this stage.\n"
        "- The function must contain concrete deterministic checks in Python code "
        "(no placeholder text).\n"
    )
    return f"""Generate a runnable Python stage implementation from the stage spec below.

Requirements:
- Output only one Python code block.
- The code must define exactly one stage class named `{stage_name}`.
- The class must inherit from `AbsStage`.
- Match the implementation style used in the provided examples.
- The stage must implement `run_body(self, provider, messages)` and return the updated `messages`.
- If local artifacts are needed, write them under `self.cache_path`.
- Do not include explanations outside the code block.
{end_condition_requirement}

Reference: AbsStage
```python
{abs_stage_code}
```

Reference: AnalyzeDirStage
```python
{analyze_stage_code}
```

Reference: old stages
{old_stage_reference_text}

Reference rule:
- Follow the style of `autostages/resources/stage_references` for interaction flow, prompting style, and `messages` handling.
- Reuse existing patterns from the old stages whenever they fit the spec.

Stage spec:
```markdown
{stage_spec}
```
"""


def generate_stage_code_with_codex(
    prompt: str,
    model_name: str | None,
    workdir: Path,
    cache_dir: Path,
) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w+",
        suffix=".txt",
        dir=cache_dir,
        delete=False,
    ) as temp_output:
        output_path = Path(temp_output.name)

    try:
        cmd = [
            "codex",
            "exec",
            "-C",
            str(workdir),
            "--skip-git-repo-check",
            "--output-last-message",
            str(output_path),
            "-",
        ]
        if model_name:
            cmd[2:2] = ["-m", model_name]
        completed = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            detail = stderr if stderr else stdout
            raise RuntimeError(
                f"codex exec failed (exit={completed.returncode}). {detail}"
            )
        return output_path.read_text(encoding="utf-8")
    finally:
        output_path.unlink(missing_ok=True)


def generate_stage_code_with_claude_cli(
    prompt: str,
    model_name: str,
    workdir: Path,
) -> str:
    completed = subprocess.run(
        [
            "claude",
            "--print",
            "--output-format",
            "text",
            "--model",
            model_name,
        ],
        input=prompt,
        text=True,
        check=True,
        cwd=workdir,
        capture_output=True,
    )
    return completed.stdout


def generate_stage_code_with_provider(
    backend_name: str,
    prompt: str,
    model_name: str,
) -> str:
    if backend_name == "claude_api":
        import requests

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model_name,
                "max_tokens": 8192,
                "messages": [
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=300,
        )
        response.raise_for_status()
        payload = response.json()
        return "".join(
            block.get("text", "")
            for block in payload.get("content", [])
            if block.get("type") == "text"
        )
    provider = create_generation_provider(backend_name, model_name)
    return provider.chat([{"role": "user", "content": prompt}])


def generate_stage_script(
    backend_name: str,
    model_name: str,
    runtime_dirs: dict[str, Path],
) -> None:
    graph_path = regenerate_graph_from_markdown(runtime_dirs)
    if graph_path:
        console.print(f"[green]Generated graph[/green] {graph_path}")
    validate_stage_graph(runtime_dirs)
    markdown_files = sorted(runtime_dirs["stages_dir"].glob("*.md"))
    if not markdown_files:
        console.print("[yellow]No stage markdown files found under .autostages/stages[/yellow]")
        return

    for markdown_path in markdown_files:
        stage_spec = markdown_path.read_text(encoding="utf-8")
        stage_name = markdown_path.stem
        output_path = runtime_dirs["generated_stages_dir"] / f"{camel_to_snake(stage_name)}.py"
        if output_path.exists():
            console.print(f"[yellow]Skipped[/yellow] {output_path} (already exists)")
            continue

        prompt = build_stage_generation_prompt(stage_spec, stage_name)
        if backend_name == "codex_cli":
            response = generate_stage_code_with_codex(
                prompt,
                model_name,
                runtime_dirs["current_dir"],
                runtime_dirs["cache_dir"],
            )
        elif backend_name == "claude_cli":
            response = generate_stage_code_with_claude_cli(
                prompt,
                model_name,
                runtime_dirs["current_dir"],
            )
        else:
            response = generate_stage_code_with_provider(
                backend_name,
                prompt,
                model_name,
            )

        code_blocks = re.findall(r"```(?:python)?\n(.*?)```", response, re.DOTALL)
        if not code_blocks:
            raise ValueError(
                f"Model response for {markdown_path.name} did not contain a Python code block."
            )

        output_path.write_text(code_blocks[0].strip() + "\n", encoding="utf-8")
        console.print(f"[green]Generated[/green] {output_path}")


def load_stage_instance(stage_script_path: Path) -> AbsStage:
    module_name = f"autostages_user_stage_{stage_script_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, stage_script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {stage_script_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for _, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, AbsStage) and obj is not AbsStage and obj.__module__ == module.__name__:
            return obj()
    raise ValueError(f"No AbsStage subclass found in {stage_script_path}")


def save_run_state(run_state_path: Path, run_state: dict[str, Any]) -> None:
    run_state_path.write_text(
        json.dumps(run_state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_stage_worker(
    stage_script: Path,
    messages_in: Path,
    messages_out: Path,
    provider_name: str | None,
    model_name: str | None,
) -> int:
    stage = load_stage_instance(stage_script)
    messages = json.loads(messages_in.read_text(encoding="utf-8"))
    provider = create_provider(provider_name, model_name) if provider_name and model_name else None
    updated = stage.run(provider, messages)
    messages_out.write_text(
        json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


def find_start_stage_node(graph: dict[str, Any]) -> str | None:
    transitions = graph.get("transitions", {})
    candidates = []
    for stage_name in sorted(transitions.keys()):
        for edge in graph.get("normal_edges", []):
            if edge.get("to") == stage_name and edge.get("from") == START_NODE:
                candidates.append(stage_name)
                break
    if not candidates:
        return None
    return candidates[0]


def stage_name_to_script_path(runtime_dirs: dict[str, Path], stage_name: str) -> Path:
    return runtime_dirs["generated_stages_dir"] / f"{camel_to_snake(stage_name)}.py"


def execute_stage_flow(
    provider_name: str,
    model_name: str,
    runtime_dirs: dict[str, Path],
    session: dict[str, Any],
    app_config: dict[str, Any],
) -> None:
    graph = load_stage_graph(runtime_dirs)
    if not graph.get("nodes"):
        console.print("[yellow]No stage nodes found in .autostages/graph.json[/yellow]")
        return

    start_stage_name = find_start_stage_node(graph)
    if start_stage_name is None:
        console.print("[yellow]No start-connected stage node found in graph.json[/yellow]")
        return

    run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    run_state_path = runtime_dirs["cache_dir"] / f"run_{run_id}.json"

    messages = get_initial_messages(runtime_dirs)
    tmp_messages = tempfile.NamedTemporaryFile(
        mode="w+",
        suffix=".json",
        prefix=f"run_{run_id}_messages_",
        delete=False,
    )
    tmp_messages.close()
    messages_path = Path(tmp_messages.name)
    messages_path.write_text(
        json.dumps(messages, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    transient_files: list[Path] = [messages_path]

    run_state: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "current_stage": start_stage_name,
        "history": [],
    }
    save_run_state(run_state_path, run_state)

    current_stage = start_stage_name
    visited_count = 0
    orchestration = app_config.get("orchestration", {})
    executor_type = orchestration.get("executor_type", "local")
    poll_interval_sec = float(orchestration.get("poll_interval_sec", 0.5))
    max_stage_steps = int(orchestration.get("max_stage_steps", 100))
    slurm_config = orchestration.get("slurm", {})

    try:
        while current_stage and current_stage != END_NODE:
            visited_count += 1
            if visited_count > max_stage_steps:
                raise RuntimeError(
                    f"Stage flow exceeded max_stage_steps={max_stage_steps}; possible infinite loop."
                )

            script_path = stage_name_to_script_path(runtime_dirs, current_stage)
            if not script_path.exists():
                raise FileNotFoundError(
                    f"Stage script not found for node '{current_stage}': {script_path}"
                )

            session["stage_script"] = script_path.name
            save_session(runtime_dirs["session_path"], session)

            stage_run_key = uuid.uuid4().hex[:8]
            tmp_out = tempfile.NamedTemporaryFile(
                mode="w+",
                suffix=".json",
                prefix=f"run_{run_id}_{stage_run_key}_messages_out_",
                delete=False,
            )
            tmp_out.close()
            stage_messages_out = Path(tmp_out.name)
            transient_files.append(stage_messages_out)
            cmd = build_worker_command(
                cli_path=Path(__file__).resolve(),
                provider_name=provider_name,
                model_name=model_name,
                stage_script=script_path,
                messages_in=messages_path,
                messages_out=stage_messages_out,
            )
            job = submit_job(
                executor_type=executor_type,
                cmd=cmd,
                cwd=runtime_dirs["current_dir"],
                slurm_config=slurm_config,
            )
            run_state["current_stage"] = current_stage
            history_item = {
                "stage": current_stage,
                "script": str(script_path),
                "executor_type": executor_type,
                "status": "running",
                "submitted_at": time.time(),
            }
            if "pid" in job:
                history_item["pid"] = job["pid"]
            if "job_id" in job:
                history_item["job_id"] = job["job_id"]
            run_state["history"].append(history_item)
            save_run_state(run_state_path, run_state)

            while True:
                polled = poll_job(job)
                if not polled.get("done"):
                    run_state["history"][-1]["heartbeat_at"] = time.time()
                    save_run_state(run_state_path, run_state)
                    time.sleep(poll_interval_sec)
                    continue
                break

            latest = run_state["history"][-1]
            latest["finished_at"] = time.time()
            latest["poll_status"] = polled.get("status")
            if "return_code" in polled:
                latest["return_code"] = polled["return_code"]
            if "slurm_state" in polled:
                latest["slurm_state"] = polled["slurm_state"]

            if polled.get("status") != "succeeded":
                latest["status"] = "failed"
                run_state["status"] = "failed"
                save_run_state(run_state_path, run_state)
                raise RuntimeError(f"Stage failed: {current_stage} ({polled})")

            latest["status"] = "succeeded"
            if stage_messages_out.exists():
                messages_path = stage_messages_out
                messages = json.loads(messages_path.read_text(encoding="utf-8"))

            stage_for_condition = load_stage_instance(script_path)
            end_condition_satisfied = stage_for_condition.evaluate_end_condition(
                runtime_dirs=runtime_dirs,
                messages=messages,
            )
            latest["end_condition_satisfied"] = bool(end_condition_satisfied)
            save_run_state(run_state_path, run_state)
            console.print(f"[green]Executed[/green] {script_path.name}")

            transitions = graph.get("transitions", {})
            transition = transitions.get(current_stage, {})
            next_stage = transition.get("on_success")
            if stage_for_condition.__class__.evaluate_end_condition is AbsStage.evaluate_end_condition:
                raise RuntimeError(
                    f"Stage '{current_stage}' must implement evaluate_end_condition()."
                )
            loop_stage = transition.get("on_incomplete")
            if not next_stage:
                run_state["status"] = "completed"
                save_run_state(run_state_path, run_state)
                break
            if next_stage == END_NODE:
                run_state["status"] = "completed"
                save_run_state(run_state_path, run_state)
                console.print(f"[green]Flow completed[/green] at End node (state: {run_state_path})")
                break

            if loop_stage:
                if not end_condition_satisfied:
                    current_stage = loop_stage
                    continue

            current_stage = next_stage
    finally:
        for tmp_path in transient_files:
            tmp_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="autosearch stage workflow CLI")
    parser.add_argument(
        "--provider",
        default=None,
        help="Provider name (e.g., openai, gemini, codex, claude)",
    )
    parser.add_argument("--model", default=None, help="Model name")
    parser.add_argument("--run-stage-script", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--messages-in", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--messages-out", default=None, help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("init", help="Initialize .autosearch in current directory")
    args = parser.parse_args()

    if args.run_stage_script:
        run_stage_worker(
            Path(args.run_stage_script),
            Path(args.messages_in),
            Path(args.messages_out),
            args.provider,
            args.model,
        )
        return

    runtime_dirs = get_runtime_dirs()
    if args.command == "init":
        init_workspace(runtime_dirs)
        return

    session = load_session(runtime_dirs["session_path"])
    app_config = load_app_config(runtime_dirs["config_path"])
    provider_name = args.provider or auto_detect_provider() or DEFAULT_PROVIDER
    sys.path.insert(0, str(runtime_dirs["src_dir"]))
    AbsStage.set_cache_root(runtime_dirs["cache_dir"])
    AbsStage.set_store_root(runtime_dirs["store_dir"])

    clear_screen()
    action = choose_menu_action(session)
    session["menu_action"] = action
    save_session(runtime_dirs["session_path"], session)

    if action == "1":
        execution_model = resolve_execution_model(provider_name, args.model, app_config)
        execute_stage_flow(provider_name, execution_model, runtime_dirs, session, app_config)
        return
    if action == "2":
        backend_name = choose_generation_backend(session)
        session["generation_backend"] = backend_name
        save_session(runtime_dirs["session_path"], session)
        generation_model = resolve_generation_model(backend_name, args.model, app_config)
        generate_stage_script(backend_name, generation_model, runtime_dirs)
        return
    if action == "3":
        validate_stage_graph(runtime_dirs)
        return


if __name__ == "__main__":
    main()
