import os

import google.generativeai as genai


class GeminiProvider:
    def __init__(self, model="gemini-pro"):
        self.model_name = model
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])
        self.model = genai.GenerativeModel(model_name=self.model_name)
        self.chat_session = self.model.start_chat(history=[])
        self.assistant_name = "model"

    def chat(self, messages):
        for msg in messages[:-1]:
            role = msg["role"]
            content = msg["content"]
            self.chat_session.history.append({"role": role, "parts": [content]})

        user_message = messages[-1]["content"]
        response = self.chat_session.send_message(user_message)
        return response.text
