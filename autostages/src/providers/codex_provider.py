import subprocess
import tempfile
from pathlib import Path


class CodexProvider:
    def __init__(self, model="gpt-5.4"):
        self.model = model
        self.assistant_name = "assistant"

    @staticmethod
    def _messages_to_prompt(messages) -> str:
        lines: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            lines.append(f"[{role}]")
            lines.append(content)
            lines.append("")
        lines.append("Respond as assistant.")
        return "\n".join(lines)

    def chat(self, messages):
        prompt = self._messages_to_prompt(messages)
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".txt", delete=False) as tmp:
            output_path = Path(tmp.name)

        try:
            cmd = [
                "codex",
                "exec",
                "--output-last-message",
                str(output_path),
                "-",
            ]
            if self.model:
                cmd[2:2] = ["-m", self.model]
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
