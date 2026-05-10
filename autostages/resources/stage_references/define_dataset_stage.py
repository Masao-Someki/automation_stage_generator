# stages/define_dataset_stage.py
from typing import List

from autostages.src.stages.abs_stage import AbsStage
from autostages.src.utils import run_with_spinner


class DefineDatasetStage(AbsStage):
    def __init__(self):
        super().__init__(
            id="define_dataset",
            description=(
                "In this stage, we will define the desired contents of your dataset.\n"
                "For each sample, we’ll determine which fields (e.g., audio, text, "
                "language) should be included,\n"
                "and which files or directories those fields should be sourced from."
            ),
            final_message="✅ Dataset field and source definition complete!",
        )

    def run_body(self, provider, messages: List[dict]) -> bool:
        # Step 0: Ask AI to propose possible sample structure first
        messages.append(
            {
                "role": "user",
                "content": (
                    "Based on the directory structure I provided earlier, please suggest"
                    "a table explaining each field and where it comes from.\n"
                    "Please only generate the table."
                ),
            }
        )

        response = run_with_spinner(
            provider.chat,
            (messages,),
            "Analyzing dataset directory by LLM..."
        )
        messages.append({"role": provider.assistant_name, "content": response})
        while True:
            confirm = self.get_user_input(
                response + "\n\n"
                "Do you approve this definition? (y to accept, anything else to revise)"
            )

            if confirm == "y":
                messages.append(
                    {
                        "role": "user",
                        "content": "Please now write json sample that describes a example "
                        "following the definition.",
                    }
                )
                final_response = provider.chat(messages)
                print("\n[Generated Dataset Sample]\n")
                print(final_response)
                messages.append({"role": provider.assistant_name, "content": final_response})
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
