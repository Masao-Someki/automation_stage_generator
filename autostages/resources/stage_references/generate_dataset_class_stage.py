# stages/generate_dataset_code_stage.py
import re
from pathlib import Path
from typing import List

from autostages.src.stages.abs_stage import AbsStage
from autostages.src.utils import run_with_spinner
from autostages.src.utils import load_resource


class GenerateDatasetClassStage(AbsStage):
    def __init__(self):
        super().__init__(
            id="generate_dataset_code",
            description=(
                "In this final stage, we will generate the full dataset class.\n"
            ),
            final_message="✅ Dataset creation code successfully generated.",
        )

    def run_body(self, provider, messages: List[dict]) -> bool:
        save_path = Path("dataset/dataset.py")
        save_path.parent.mkdir(parents=True, exist_ok=True)

        user_input = self.get_user_input(
            "Do you want to change dataset class name from the default name? Default: Dataset)"
        )
        if user_input == "y":
            user_input = "Dataset"

        messages.append(
            {
                "role": "user",
                "content": (
                    "Based on the following reference script, generate a Python script of dataset.py.\n"
                    f"The class name should be {user_input}\n."
                    "Please wrap the entire code in a single Python code block using triple backticks (```python).\n"
                ),
            }
        )

        retry_count = 0
        while retry_count < 2:
            response = run_with_spinner(
                provider.chat,
                (messages,),
                "Generating dataset class..."
            )
            messages.append({"role": provider.assistant_name, "content": response})

            # Extract code block
            code_blocks = re.findall(r"```(?:python)?\n(.*?)```", response, re.DOTALL)
            if code_blocks:
                code = code_blocks[0].strip()
                print(f"\nSaving generated script to: {save_path}")
                save_path.write_text(code, encoding="utf-8")
                return messages
            else:
                print(
                    "\n⚠️  No code block found. Asking AI to regenerate with proper formatting..."
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Please regenerate the previous script, ensuring the entire code is wrapped in triple backticks like this:```python\n# code here\n```."
                        ),
                    }
                )
                retry_count += 1

        print(
            "\n❌ I'm sorry, failed to generate a properly formatted code block after multiple attempts. Consider changing the LLM."
        )
        return False
