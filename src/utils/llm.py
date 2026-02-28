"""
本地模型接入 - gpt-oss-20b
"""
import requests
from .config import config


class LocalLLM:
    """本地 LLM 封装 - 直接使用 HTTP"""
    
    def __init__(
        self,
        model_name: str = None,
        base_url: str = None,
        api_key: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ):
        self.model_name = model_name or config.LLM_MODEL
        self.base_url = base_url or config.LLM_BASE_URL
        self.api_key = api_key or config.LLM_API_KEY
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        self.available = self._check_connection()
    
    def _check_connection(self) -> bool:
        """检查模型服务是否可用"""
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
        """调用模型"""
        if not self.available:
            return "本地模型未连接"
        
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
                    "max_tokens": self.max_tokens
                },
                timeout=60
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"调用失败: {e}"
    
    def __repr__(self):
        status = "已连接" if self.available else "未连接"
        return f"LocalLLM({self.model_name}, {status})"


class MockLLM:
    """模拟 LLM - 用于测试"""
    
    def __init__(self, response: str = "这是模拟响应"):
        self.response = response
        self.available = True
    
    def invoke(self, prompt: str, system_prompt: str = "") -> str:
        return self.response


def create_llm(
    provider: str = "local",
    **kwargs
) -> LocalLLM:
    """创建 LLM 实例"""
    if provider == "local":
        return LocalLLM(**kwargs)
    elif provider == "mock":
        return MockLLM(kwargs.get("response", ""))
    else:
        raise ValueError(f"Unknown provider: {provider}")
