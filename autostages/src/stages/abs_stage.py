# stages/abs_stage.py
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, List
import os
import shlex
import shutil
import tempfile
import subprocess

def comment_lines(text: str) -> str:
        return "\n".join(f"# {line}" if not line.strip().startswith("#") else line for line in text.splitlines())


def open_temp_file(editor_cmd: str, file_path: str) -> bool:
    cmd = shlex.split(editor_cmd)
    if not cmd:
        return False
    if shutil.which(cmd[0]) is None:
        return False
    subprocess.call([*cmd, file_path])
    return True


def should_offer_vscode_editor() -> bool:
    # On remote SSH servers, `code` often points to the VS Code server CLI and
    # cannot open a local editor window reliably.
    if any(os.environ.get(name) for name in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY")):
        return False
    return shutil.which("code") is not None

class AbsStage(ABC):
    cache_root = Path(".autostages/cache")

    @classmethod
    def set_cache_root(cls, cache_root: Path) -> None:
        cls.cache_root = Path(cache_root)
        cls.cache_root.mkdir(parents=True, exist_ok=True)

    def __init__(self, id: str, description: str = "", final_message: str = ""):
        self.id = id
        self.description = description
        self.final_message = final_message
        self.cache_path = self.cache_root / self.__class__.__name__
        self.cache_path.mkdir(parents=True, exist_ok=True)

    def display_intro(self):
        if self.description:
            print(f"=== Stage: {self.id} ===\n{self.description}\n")

    def display_outro(self):
        if self.final_message:
            print(f"\n{self.final_message}\n")

    def get_user_input(self, initial_text: str) -> str:
        """
        Prompt user for input. Options:
        - 'y': accept default text as-is
        - 'e': open editor to modify text
        - Enter: prompt again

        Returns:
            str: the edited text with comment lines stripped
        """
        print(initial_text)
        print("\nEdit options:")
        print("  [y] Accept default text")
        print("  [e] Edit using your default editor")
        show_vscode_option = should_offer_vscode_editor()
        if show_vscode_option:
            print("  [v] Edit using VS Code")
        print("  [Enter] Prompt again")
        while True:
            prompt = "Your choice (y/e"
            if show_vscode_option:
                prompt += "/v"
            prompt += "/any text): "
            user_choice = input(prompt).strip()

            if user_choice == "y":
                return "y"
            elif user_choice == "":
                continue
            elif user_choice in {"e", "v"}:
                if user_choice == "v" and not show_vscode_option:
                    print("VS Code editor is not available in this environment.")
                    continue
                editor = os.environ.get("EDITOR", "vi")
                editor_cmd = editor if user_choice == "e" else "code --wait"
                with tempfile.NamedTemporaryFile(suffix=".tmp", mode="w+", delete=False) as tf:
                    tf.write(comment_lines(initial_text))
                    tf.flush()
                    tf_path = tf.name

                if not open_temp_file(editor_cmd, tf_path):
                    os.unlink(tf_path)
                    print(f"Editor command not found: {editor_cmd}")
                    continue

                with open(tf_path, "r", encoding="utf-8") as tf:
                    edited_text = tf.read()

                os.unlink(tf_path)
                filtered_text = "\n".join(
                    line for line in edited_text.splitlines()
                    if not line.strip().startswith("#")
                )
                return filtered_text.strip()

            else:
                return user_choice

    @abstractmethod
    def run_body(self, provider, messages: List[dict]) -> bool:
        """
        Execute the core logic of the stage.

        Returns:
            bool: True if the tool should proceed to the next stage, False otherwise.
        """
        pass

    def evaluate_end_condition(self, runtime_dirs: dict[str, Any], messages: List[dict]) -> bool:
        """
        Return True when the stage-specific end condition is satisfied.
        Stages with loop behavior should override this method.
        """
        return True

    def run(self, provider, messages: List[dict]) -> bool:
        """
        Run the full stage including intro, body, and outro.

        Returns:
            bool: Whether to proceed to the next stage.
        """
        self.display_intro()
        should_continue = self.run_body(provider, messages)
        self.display_outro()
        return should_continue
