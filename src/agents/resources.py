"""
Sub Agent Private Resources - Tools, Data Sources, Private Context

Provides each Sub Agent with independent:
- Tools: Executable tools
- Data Sources: Data sources
- Private Context: Private context storage
- Storage: Private storage
"""

import json
import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ..utils.llm import LocalLLM


# ========== Tools ==========


class BaseTool:
    """Base tool"""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.llm: Optional[LocalLLM] = None

    def set_llm(self, llm: LocalLLM):
        """Set LLM instance for this tool"""
        self.llm = llm

    def execute(self, **kwargs) -> Any:
        raise NotImplementedError

    def __repr__(self):
        return f"<Tool: {self.name}>"


class FashionSearchTool(BaseTool):
    """Fashion search tool using LLM"""

    def __init__(self, llm: LocalLLM = None):
        super().__init__("fashion_search", "Search fashion information")
        self.llm = llm

    def execute(self, query: str = "", **kwargs) -> Dict[str, Any]:
        """Execute search using LLM or fallback to database"""
        if self.llm and self.llm.available:
            prompt = f"""Based on the following user context, provide fashion recommendations:

User Query: {query}
User Mood: {kwargs.get('mood', 'normal')}
User Occupation: {kwargs.get('occupation', 'general')}
Season: {kwargs.get('season', 'spring')}
User Age: {kwargs.get('age', 25)}

Please provide recommendations in JSON format:
{{
    "colors": ["color1", "color2"],
    "style_tips": ["tip1", "tip2"],
    "season_colors": ["color1", "color2"]
}}"""
            response = self.llm.invoke(prompt)
            try:
                import json
                start = response.find("{")
                end = response.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(response[start:end])
                    return data
            except:
                pass

        # Fallback to database
        return self._execute_fallback(**kwargs)

    def _execute_fallback(self, **kwargs) -> Dict[str, Any]:
        """Fallback to database when LLM unavailable"""
        database = {
            "colors_for_mood": {
                "happy": ["yellow", "orange", "pink", "bright blue"],
                "sad": ["blue", "gray", "dark green", "black"],
                "angry": ["red", "black", "white"],
                "depressed": ["light blue", "cyan", "white", "orange", "yellow"],
                "calm": ["green", "blue", "beige", "lavender"],
            },
            "styles_for_occupation": {
                "chef": ["breathable", "waterproof", "lightweight", "easy-clean"],
                "programmer": ["simple", "comfortable", "casual"],
                "teacher": ["formal", "comfortable", "professional"],
                "sales": ["professional", "formal", "sharp"],
            },
            "colors_season": {
                "spring": ["pink", "light green", "light yellow", "white"],
                "summer": ["light blue", "white", "yellow", "orange"],
                "autumn": ["brown", "orange", "dark green", "burgundy"],
                "winter": ["black", "navy", "gray", "white"],
            },
        }

        results = {}
        if "mood" in kwargs:
            results["colors"] = database["colors_for_mood"].get(kwargs["mood"], [])
        if "occupation" in kwargs:
            results["style_tips"] = database["styles_for_occupation"].get(kwargs["occupation"], [])
        if "season" in kwargs:
            results["season_colors"] = database["colors_season"].get(kwargs["season"], [])

        return results


class WeatherCheckTool(BaseTool):
    """Weather check tool using LLM"""

    def __init__(self, llm: LocalLLM = None):
        super().__init__("weather_check", "Check weather information")
        self.llm = llm

    def execute(self, location: str = "Beijing", **kwargs) -> Dict[str, Any]:
        """Check weather using LLM or fallback"""
        season = kwargs.get("season", "spring")
        mood = kwargs.get("mood", "normal")

        if self.llm and self.llm.available:
            prompt = f"""Provide weather information for {location} in {season} season and give clothing suggestions based on mood: {mood}

Provide in JSON format:
{{
    "location": "{location}",
    "temperature": "temperature range",
    "weather": "weather condition",
    "humidity": "humidity level",
    "clothing_suggestion": "what to wear"
}}"""
            response = self.llm.invoke(prompt)
            try:
                import json
                start = response.find("{")
                end = response.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(response[start:end])
                    data["suggestion"] = data.get("clothing_suggestion", "")
                    return data
            except:
                pass

        # Fallback
        season_temp = {
            "spring": "15-25°C",
            "summer": "25-35°C",
            "autumn": "10-20°C",
            "winter": "-5-10°C"
        }
        return {
            "location": location,
            "temperature": season_temp.get(season, "20°C"),
            "weather": "sunny" if season in ["spring", "summer"] else "cloudy",
            "humidity": "50-70%",
            "suggestion": "Suitable for lightweight clothing",
        }


class StyleRecommendTool(BaseTool):
    """Style recommendation tool using LLM"""

    def __init__(self, llm: LocalLLM = None):
        super().__init__("style_recommend", "Recommend fashion style")
        self.llm = llm

    def execute(self, style: str = "casual", **kwargs) -> Dict[str, Any]:
        """Recommend style using LLM or fallback"""
        age = kwargs.get("age", 25)
        occupation = kwargs.get("occupation", "general")
        mood = kwargs.get("mood", "normal")
        budget = kwargs.get("budget", "medium")

        if self.llm and self.llm.available:
            prompt = f"""Recommend {style} style outfit items for:
- Age: {age}
- Occupation: {occupation}
- Mood: {mood}
- Budget: {budget}

Provide in JSON format:
{{
    "style": "{style}",
    "items": ["item1", "item2", "item3", "item4"],
    "tips": ["tip1", "tip2"]
}}"""
            response = self.llm.invoke(prompt)
            try:
                import json
                start = response.find("{")
                end = response.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(response[start:end])
                    return data
            except:
                pass

        # Fallback
        style_db = {
            "casual": ["T-shirt", "jeans", "sneakers", "casual pants"],
            "formal": ["suit", "shirt", "dress shoes", "tie"],
            "sporty": ["sportswear", "sneakers", "sports pants", "hoodie"],
            "street": ["streetwear", "oversized", "sneakers", "accessories"],
            "minimalist": ["solid color", "minimalist", "basic", "black white gray"],
        }
        return {
            "style": style,
            "items": style_db.get(style, []),
            "tips": [f"Recommend {style} style outfit"],
        }


# ========== Data Sources ==========


class BaseDataSource:
    """Base data source"""

    def __init__(self, name: str):
        self.name = name

    def query(self, **kwargs) -> Any:
        raise NotImplementedError


class FashionDatabase(BaseDataSource):
    """Fashion database"""

    def __init__(self):
        super().__init__("fashion_db")
        self._data = {
            "trending_colors": ["light blue", "cyan", "orange", "beige"],
            "popular_styles": ["casual", "sporty", "minimalist", "street"],
            "age_groups": {
                "18-25": ["trendy", "personal", "sporty"],
                "26-35": ["professional", "casual", "minimalist"],
                "36-45": ["mature", "professional", "comfortable"],
                "46+": ["elegant", "comfortable", "quality"],
            },
        }

    def query(self, key: str = None, **kwargs) -> Any:
        if key:
            return self._data.get(key)
        return self._data


class UserHistoryDB(BaseDataSource):
    """User history data source"""

    def __init__(self):
        super().__init__("user_history")
        self._history: Dict[str, List[Dict]] = {}

    def query(self, session_id: str = None, **kwargs) -> List[Dict]:
        if session_id:
            return self._history.get(session_id, [])
        return []

    def add_record(self, session_id: str, record: Dict):
        if session_id not in self._history:
            self._history[session_id] = []
        self._history[session_id].append(record)


# ========== Private Context ==========


class PrivateContext:
    """
    Private context - independent context storage for each Sub Agent
    """

    def __init__(self, agent_id: str, storage=None):
        self.agent_id = agent_id
        self._storage = storage
        self._memory: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def set(self, key: str, value: Any):
        """Set context"""
        with self._lock:
            self._memory[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get context"""
        with self._lock:
            return self._memory.get(key, default)

    def update(self, data: Dict):
        """Batch update"""
        with self._lock:
            self._memory.update(data)

    def get_all(self) -> Dict[str, Any]:
        """Get all context"""
        with self._lock:
            return self._memory.copy()

    def clear(self):
        """Clear context"""
        with self._lock:
            self._memory.clear()

    def save_to_storage(self, session_id: str):
        """Persist to storage"""
        if self._storage:
            try:
                self._storage.save_agent_context(
                    session_id, self.agent_id, self._memory
                )
            except Exception as e:
                print(f"WARNING: Context save failed: {e}")

    def load_from_storage(self, session_id: str):
        """Load from storage"""
        if self._storage:
            try:
                ctx = self._storage.get_agent_context(session_id, self.agent_id)
                if ctx and ctx.get("context_data"):
                    with self._lock:
                        self._memory.update(ctx["context_data"])
            except Exception as e:
                print(f"WARNING: Context load failed: {e}")


# ========== Agent Resources ==========


@dataclass
class AgentResources:
    """Agent resources container"""

    agent_id: str
    tools: List[BaseTool] = field(default_factory=list)
    data_sources: List[BaseDataSource] = field(default_factory=list)
    private_context: Optional[PrivateContext] = None
    storage: Any = None

    def add_tool(self, tool: BaseTool):
        """Add tool"""
        self.tools.append(tool)

    def add_data_source(self, ds: BaseDataSource):
        """Add data source"""
        self.data_sources.append(ds)

    def use_tool(self, tool_name: str, **kwargs) -> Any:
        """Use tool"""
        for tool in self.tools:
            if tool.name == tool_name:
                return tool.execute(**kwargs)
        raise ValueError(f"Tool not found: {tool_name}")

    def query_data(self, source_name: str, **kwargs) -> Any:
        """Query data source"""
        for ds in self.data_sources:
            if ds.name == source_name:
                return ds.query(**kwargs)
        return None


# ========== Resource Factory ==========


class AgentResourceFactory:
    """Agent resource factory"""

    @staticmethod
    def create_for_category(category: str, storage=None, llm: LocalLLM = None) -> AgentResources:
        """Create resources for specific category"""
        resources = AgentResources(agent_id=f"agent_{category}")

        # Add common tools (with LLM)
        fashion_tool = FashionSearchTool(llm)
        weather_tool = WeatherCheckTool(llm)
        style_tool = StyleRecommendTool(llm)
        
        resources.add_tool(fashion_tool)
        resources.add_tool(weather_tool)
        resources.add_tool(style_tool)

        # Add data sources
        resources.add_data_source(FashionDatabase())
        resources.add_data_source(UserHistoryDB())

        # Create private context
        resources.private_context = PrivateContext(resources.agent_id, storage)

        return resources


# ========== Error Handling ==========


class AgentError(Exception):
    """Agent error base class"""

    pass


class ToolExecutionError(AgentError):
    """Tool execution error"""

    pass


class DataSourceError(AgentError):
    """Data source error"""

    pass


class ContextError(AgentError):
    """Context error"""

    pass
