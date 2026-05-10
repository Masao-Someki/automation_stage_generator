import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, List

from autoespnet3.src.stages.abs_stage import AbsStage


class LoopStartStage(AbsStage):
    LOOP_TAG = "[LOOP_CONTROL]"

    def __init__(self):
        super().__init__(
            id="loop_start",
            description=(
                "Select the next design target for this loop iteration based on the current analysis context."
            ),
            final_message="✅ Loop target selected.",
        )

    def _extract_python_targets(self, text: str) -> List[str]:
        matches = re.findall(r"\b(?:[\w\-]+/)*[\w\-]+\.py\b", text)
        normalized = [Path(m).as_posix() for m in matches]
        return normalized

    def _extract_handled_targets(self, messages: List[dict]) -> set[str]:
        handled = set()
        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = str(msg.get("content", ""))
            if self.LOOP_TAG not in content:
                continue
            target_match = re.search(r"target:\s*(.+)", content, flags=re.IGNORECASE)
            if target_match:
                handled.add(target_match.group(1).strip())
        return handled

    def run_body(self, provider, messages: List[dict]) -> List[dict]:
        context_text = "\n".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))
        candidates = self._extract_python_targets(context_text)
        handled = self._extract_handled_targets(messages)

        if candidates:
            counts = Counter(candidates)
            unhandled_ranked = [(name, cnt) for name, cnt in counts.most_common() if name not in handled]
            if unhandled_ranked:
                target, count = unhandled_ranked[0]
                reason = (
                    f"Selected the highest-frequency unhandled Python file from analysis context "
                    f"(mentioned {count} times)."
                )
            else:
                target, count = counts.most_common(1)[0]
                reason = (
                    f"All discovered targets were previously handled; selected the most frequently referenced "
                    f"target again for iterative refinement (mentioned {count} times)."
                )
        else:
            target = "analysis_summary"
            reason = "No explicit Python file target found in context; selected summary-level refinement."

        loop_message = (
            f"{self.LOOP_TAG}\n"
            f"target: {target}\n"
            f"reason: {reason}"
        )
        messages.append({"role": "user", "content": loop_message})

        artifact = {
            "target": target,
            "reason": reason,
            "message_index": len(messages) - 1,
        }
        (self.cache_path / "loop_target.json").write_text(
            json.dumps(artifact, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        return messages

    def evaluate_end_condition(self, runtime_dirs: dict[str, Any], messages: List[dict]) -> bool:
        if not messages:
            return False
        last = messages[-1]
        if not isinstance(last, dict) or last.get("role") != "user":
            return False
        content = str(last.get("content", ""))
        if self.LOOP_TAG not in content:
            return False
        if re.search(r"target:\s*\S+", content, flags=re.IGNORECASE) is None:
            return False
        if re.search(r"reason:\s*\S+", content, flags=re.IGNORECASE) is None:
            return False
        return True
