# stages/define_datasetdict_stage.py
from pathlib import Path
from typing import List

from autostages.src.stages.abs_stage import AbsStage
from autostages.src.utils import run_with_spinner


class DefineDatasetDictStage(AbsStage):
    def __init__(self):
        super().__init__(
            id="define_datasetdict",
            description=(
                "In this stage, we will define how to construct and save the overall DatasetDict.\n"
                "You will choose the output directory (default: ./data) and discuss how to split the dataset\n"
                "(e.g., by folder, metadata, train/dev/test, etc.)."
            ),
            final_message="✅ DatasetDict configuration complete and ready for saving.",
        )

    def run_body(self, provider, messages: List[dict]) -> bool:
        # Ask where to save the DatasetDict
        user_input = self.get_user_input(
            "Where should the processed DatasetDict be saved? (press Enter for default './data')"
        )
        save_dir = Path(user_input) if user_input else Path("./data")

        # Append instruction for AI to propose splits
        messages.append(
            {
                "role": "user",
                "content": (
                    f"We will save the final DatasetDict to `{save_dir}`.\n"
                    "Please suggest how the DatasetDict should be split (e.g., train/dev/test)."
                ),
            }
        )

        # Let the provider respond
        response = run_with_spinner(
            provider.chat,
            (messages,),
            "Analyzing dataset dict by LLM..."
        )
        print(response)
        messages.append({"role": provider.assistant_name, "content": response})

        # Confirm or revise
        while True:
            confirm = self.get_user_input(
                response + "\n\n" +
                "Do you approve this split definition? (y to accept, anything else to revise)"
            )
            if confirm == "y":
                return messages
            else:
                messages.append(
                    {
                        "role": "user",
                        "content": f"""Please revise the previous proposal based on my
feedback and regenerate the table and example.

{confirm}
""",
                    }
                )
                response = provider.chat(messages)
                messages.append({"role": provider.assistant_name, "content": response})
