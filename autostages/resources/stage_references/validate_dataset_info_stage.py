# stages/define_dataset_stage.py
from pathlib import Path
from typing import List

import inquirer

from autostages.src.stages.abs_stage import AbsStage
from autostages.src.utils import load_resource
from autostages.src.utils import run_with_spinner


class ValidateDatasetInfoStage(AbsStage):
    def __init__(self):
        super().__init__(
            id="validate_dataset_info",
            description=(
                "Check if all required information for dataset generation is available.\n"
                "We’ll ask the AI to identify any missing details and resolve them iteratively."
            ),
            final_message="✅ All required information for dataset generation is confirmed."
        )

    def run_body(self, provider, messages: List[dict]) -> bool:
        # Prompt user for format choice
        questions = [
            inquirer.List(
                "format_choice",
                message="Select the dataset format you want to use:",
                choices=["Hugging Face DatasetDict", "Lhotse CutSet", "Other (manual)"],
            )
        ]
        answers = inquirer.prompt(questions)
        format_choice = answers["format_choice"]

        # For manual option, ask for reference script
        reference_script = None
        if format_choice == "Other (manual)":
            print(
                "Please enter the path to a reference script to guide the dataset creation code generation:"
            )
            reference_input = input("\n> ").strip()
            reference_script = Path(reference_input) if reference_input else None

        # Ask for code generation based on selected format
        if (
            format_choice == "Other (manual)"
            and reference_script
            and reference_script.exists()
        ):
            with open(reference_script, encoding="utf-8") as f:
                reference_code = f.read()
        elif format_choice == "Hugging Face DatasetDict":
            reference_code = load_resource("huggingface_crate_dataset.py")
        elif format_choice == "Lhotse CutSet":
            reference_code = load_resource("lhotse_crate_dataset.py")

        messages.append({
            "role": "user",
            "content": (
                "Based on the current conversation so far, I want to generate a `create_dataset.py` script.\n"
                "Please check if any important information is missing to generate it correctly.\n"
                "If anything is missing, list what needs to be clarified.\n"
                ""
                "If nothing is missing, reply only with: All required information is available."
                "\n"
                "**Reference code**\n"
                "```\n" + reference_code + "\n```"
            )
        })
        reply = run_with_spinner(
            provider.chat,
            (messages,),
            "Check if we need more information..."
        )

        while True:
            messages.append({"role": provider.assistant_name, "content": reply})
            if "All required information is available" in reply:
                return messages

            user_response = self.get_user_input(reply)
            messages.append({"role": "user", "content": user_response})

            messages.append({
                "role": "user",
                "content": (
                    "Based on the current conversation so far, I want to generate a `create_dataset.py` script.\n"
                    "Please check if any important information is missing to generate it correctly.\n"
                    "If anything is missing, list what needs to be clarified.\n"
                    "If nothing is missing, reply only with: All required information is available."
                )
            })
            reply = provider.chat(messages)
