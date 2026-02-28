"""
Local Model Integration - gpt-oss-20b
"""

import requests
from .config import config


class LocalLLM:
    """Local LLM wrapper - direct HTTP usage"""

    def __init__(
        self,
        model_name: str = None,
        base_url: str = None,
        api_key: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        self.model_name = model_name or config.LLM_MODEL
        self.base_url = base_url or config.LLM_BASE_URL
        self.api_key = api_key or config.LLM_API_KEY
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.available = self._check_connection()

    def _check_connection(self) -> bool:
        """Check if model service is available"""
        try:
            resp = requests.get(f"{self.base_url}/models", timeout=5)
            if resp.status_code == 200:
                models = resp.json()
                for m in models.get("data", []):
                    if self.model_name in m.get("id", ""):
                        return True
            return False
        except:
            return False

    def invoke(self, prompt: str, system_prompt: str = "") -> str:
        """Invoke model"""
        if not self.available:
            return "Local model not connected"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                },
                timeout=60,
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Invocation failed: {e}"

    def __repr__(self):
        status = "connected" if self.available else "not connected"
        return f"LocalLLM({self.model_name}, {status})"


class MockLLM:
    """Mock LLM - for testing"""

    def __init__(self, response: str = "This is a mock response"):
        self.response = response
        self.available = True

    def invoke(self, prompt: str, system_prompt: str = "") -> str:
        return self.response


def create_llm(provider: str = "local", **kwargs) -> LocalLLM:
    """Create LLM instance"""
    if provider == "local":
        return LocalLLM(**kwargs)
    elif provider == "mock":
        return MockLLM(kwargs.get("response", ""))
    else:
        raise ValueError(f"Unknown provider: {provider}")
