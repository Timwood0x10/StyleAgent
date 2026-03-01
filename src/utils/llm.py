"""
Local Model Integration - gpt-oss-20b
"""

import os
import requests
import httpx
import asyncio
from typing import Optional, Union, List
from .config import config


class LocalLLM:
    """Local LLM wrapper - direct HTTP usage"""

    def __init__(
        self,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ):
        self.model_name = model_name or config.LLM_MODEL
        self.base_url = base_url or config.LLM_BASE_URL
        self.api_key = api_key or config.LLM_API_KEY
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.available = self._check_connection()

        # Embedding configuration
        self.embedding_model = config.EMBEDDING_MODEL
        self.embedding_url = config.EMBEDDING_BASE_URL or self.base_url
        self.embedding_dim = config.EMBEDDING_DIM

    def _check_connection(self) -> bool:
        """Check if model service is available"""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json()
                for m in models.get("models", []):
                    if self.model_name in m.get("name", ""):
                        return True
            return False
        except:
            return False

    def invoke(self, prompt: str, system_prompt: str = "") -> str:
        """Invoke model (sync)"""
        if not self.available:
            raise ConnectionError("Local model not connected")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "stream": False,
                },
                timeout=60,
            )
            data = resp.json()
            return data["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"LLM invocation failed: {e}")

    async def ainvoke(self, prompt: str, system_prompt: str = "") -> str:
        """Invoke model (async) - using thread pool to avoid httpx issues"""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.invoke, prompt, system_prompt)

    async def acheck_connection(self) -> bool:
        """Check if model service is available (async)"""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
                if resp.status_code == 200:
                    models = resp.json()
                    for m in models.get("models", []):
                        if self.model_name in m.get("name", ""):
                            return True
                return False
        except:
            return False

    def embed(self, text: str) -> List[float]:
        """
        Generate embedding vector for text using local model or OpenAI
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        # Check if using OpenAI API for embeddings
        if "openai" in self.embedding_url.lower() or os.getenv("OPENAI_API_KEY"):
            return self._embed_openai(text)
        else:
            return self._embed_local(text)

    def _embed_openai(self, text: str) -> List[float]:
        """Generate embedding using OpenAI API"""
        try:
            import openai
            openai.api_key = os.getenv("OPENAI_API_KEY", self.api_key)
            openai.base_url = os.getenv("OPENAI_BASE_URL", self.embedding_url)
            
            resp = openai.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            return resp.data[0].embedding
        except Exception as e:
            # Fallback to local embedding
            return self._embed_local(text)

    def _embed_local(self, text: str) -> List[float]:
        """Generate embedding using local model (ollama)"""
        try:
            resp = requests.post(
                f"{self.embedding_url}/api/embeddings",
                json={"model": self.embedding_model, "prompt": text},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("embedding", [])
            # If local model doesn't support embeddings, return dummy vector
            return self._dummy_embedding(len(text))
        except Exception:
            # Return dummy embedding on failure
            return self._dummy_embedding(len(text))

    def _dummy_embedding(self, seed: int = 0) -> List[float]:
        """Generate a deterministic dummy embedding for fallback"""
        import math
        # Generate a simple hash-based pseudo-random vector
        vec = []
        for i in range(self.embedding_dim):
            val = math.sin(seed * (i + 1) * 12.9898) * 43758.5453
            vec.append(val - math.floor(val))
        return vec

    async def aembed(self, text: str) -> List[float]:
        """Async version of embed"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed, text)

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

    async def ainvoke(self, prompt: str, system_prompt: str = "") -> str:
        """Mock async invoke"""
        await asyncio.sleep(0.1)  # Simulate async delay
        return self.response

    def embed(self, text: str) -> List[float]:
        """Mock embed - return dummy vector"""
        import math
        # Return consistent dummy vector based on text length
        dim = 1536
        vec = []
        for i in range(dim):
            val = math.sin(len(text) * (i + 1) * 12.9898) * 43758.5453
            vec.append(val - math.floor(val))
        return vec

    async def aembed(self, text: str) -> List[float]:
        """Mock async embed"""
        await asyncio.sleep(0.05)
        return self.embed(text)


def create_llm(provider: str = "local", **kwargs) -> Union[LocalLLM, MockLLM]:
    """Create LLM instance"""
    if provider == "local":
        return LocalLLM(**kwargs)
    elif provider == "mock":
        return MockLLM(kwargs.get("response", ""))
    else:
        raise ValueError(f"Unknown provider: {provider}")
