import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from .base import BaseProvider

load_dotenv()

class GroqProvider(BaseProvider):
    def __init__(self, model: str = "llama-3.1-8b-instant"):
        self.llm = ChatGroq(
            model=model,
            api_key=os.getenv("GROQ_API_KEY")
        )

    def generate(self, prompt: str, tools: list = None) -> str:
        response = self.llm.invoke(prompt)
        return response.content