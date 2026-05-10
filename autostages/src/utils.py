from pathlib import Path
from typing import List


def load_resource(name: str) -> str:
    """
    Load a resource file from the local 'resources/' directory relative to this script.

    Args:
        name (str): The base filename or relative path inside 'resources/'.

    Returns:
        str: The content of the resource file.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    # Resolve the path to the resources directory relative to this file
    resources_dir = Path(__file__).parent.parent / "resources"
    resources_path = resources_dir / name
    return resources_path.read_text(encoding="utf-8")


from rich.console import Console
from rich.spinner import Spinner
from rich.live import Live
import time

console = Console()

def run_with_spinner(task_fn, args, message="Processing..."):
    """
    Runs a blocking function with a live spinner.

    Args:
        task_fn (callable): a no-arg function to run.
        message (str): description shown with spinner.

    Returns:
        any: result of task_fn()
    """
    spinner = Spinner("dots", text=message)
    with Live(spinner, refresh_per_second=10, console=console):
        result = task_fn(*args)
    return result