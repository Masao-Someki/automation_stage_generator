from datetime import datetime
from pathlib import Path
from typing import Any, List

from autoespnet3.src.analyze_dir import get_markdown
from autoespnet3.src.stages.abs_stage import AbsStage
from autoespnet3.src.utils import run_with_spinner


class AnalyzeDirStage(AbsStage):
    def __init__(self):
        super().__init__(
            id="analyze_dir",
            description="Analyze a Python source directory.",
            final_message="✅ Directory analysis complete.",
        )
        self._last_output_path: Path | None = None

    def run_body(self, provider, messages: List[dict]) -> List[dict]:
        while True:
            user_input = self.get_user_input("Directory path to analyze:")
            target_dir = Path(user_input).expanduser()
            if target_dir.exists() and target_dir.is_dir():
                break
            print(f"\n❌ '{target_dir}' is not a valid directory.\n")

        summary = run_with_spinner(
            get_markdown,
            (target_dir, "python-overview"),
            "Analyzing directory..."
        )

        date_suffix = datetime.now().strftime("%Y%m%d")
        output_path = self.cache_path / f"{target_dir.name}_{date_suffix}.md"
        output_path.write_text(summary, encoding="utf-8")
        self._last_output_path = output_path

        messages.append({"role": "user", "content": summary})
        return messages

    def evaluate_end_condition(self, runtime_dirs: dict[str, Any], messages: List[dict]) -> bool:
        if self._last_output_path is None:
            return False
        if not self._last_output_path.exists() or not self._last_output_path.is_file():
            return False

        saved_summary = self._last_output_path.read_text(encoding="utf-8")
        if not saved_summary.strip():
            return False

        return any(msg.get("content") == saved_summary for msg in messages if isinstance(msg, dict))
