from datetime import datetime
from pathlib import Path
from typing import List

from autostages.src.analyze_dir import get_markdown
from autostages.src.stages.abs_stage import AbsStage
from autostages.src.utils import run_with_spinner


class AnalyzeDirStage(AbsStage):
    def __init__(self):
        super().__init__(
            id="analyze_dir",
            description="Analyze a Python source directory.",
            final_message="✅ Directory analysis complete.",
        )

    def run_body(self, provider, messages: List[dict]) -> bool:
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

        messages.append({"role": "user", "content": summary})
        return messages
