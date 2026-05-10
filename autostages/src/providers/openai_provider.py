import openai


class OpenAIProvider:
    def __init__(self, model="gpt-4o"):
        self.model = model
        # virtual env OPENAI_API_KEY is required
        self.client = openai.OpenAI()
        self.assistant_name = "assistant"

    def chat(self, messages):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        return response.choices[0].message.content
