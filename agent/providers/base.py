from abc import ABC, abstractmethod

class BaseProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, tools: list = None) -> str:
        """Send a prompt to the LLM and return its text response."""
        pass