from pathlib import Path
from typing import Any, List

from autoespnet3.src.stages.abs_stage import AbsStage


class LoopEndStage(AbsStage):
    def __init__(self):
        super().__init__(
            id="loop_end",
            description=(
                "Check whether this loop iteration produced at least one analyzed markdown."
            ),
            final_message="✅ Loop end check complete.",
        )

    def evaluate_end_condition(self, runtime_dirs: dict[str, Any], messages: List[dict]) -> bool:
        analyze_cache_dir = AbsStage.cache_root / "AnalyzeDirStage"
        if not analyze_cache_dir.exists() or not analyze_cache_dir.is_dir():
            return False
        return any(p.is_file() for p in analyze_cache_dir.glob("*.md"))

    def run_body(self, provider, messages: List[dict]) -> List[dict]:
        is_complete = self.evaluate_end_condition(runtime_dirs={}, messages=messages)
        if is_complete:
            status = (
                "LoopEndStage decision: complete. "
                "Found at least one markdown under .autoespnet3/cache/AnalyzeDirStage/."
            )
        else:
            status = (
                "LoopEndStage decision: incomplete. "
                "No markdown found under .autoespnet3/cache/AnalyzeDirStage/."
            )

        status_path = self.cache_path / "loop_end_status.txt"
        status_path.write_text(status + "\n", encoding="utf-8")

        messages.append({"role": "user", "content": status})
        return messages
