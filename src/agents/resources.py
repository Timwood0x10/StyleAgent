"""
Sub Agent Private Resources - Tools, Data Sources, Private Context

Provides each Sub Agent with independent:
- Tools: Executable tools
- Data Sources: Data sources
- Private Context: Private context storage
- Storage: Private storage
"""

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


# ========== Tools ==========


class BaseTool:
    """Base tool"""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description

    def execute(self, **kwargs) -> Any:
        raise NotImplementedError

    def __repr__(self):
        return f"<Tool: {self.name}>"


class FashionSearchTool(BaseTool):
    """Fashion search tool"""

    def __init__(self):
        super().__init__("fashion_search", "Search fashion information")
        # Sample data source
        self._database = {
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

    def execute(self, query: str = "", **kwargs) -> Dict[str, Any]:
        """Execute search"""
        results = {}

        # Mood colors
        if "mood" in kwargs:
            mood = kwargs["mood"]
            results["colors"] = self._database["colors_for_mood"].get(mood, [])

        # Occupation recommendations
        if "occupation" in kwargs:
            occ = kwargs["occupation"]
            results["style_tips"] = self._database["styles_for_occupation"].get(occ, [])

        # Season colors
        if "season" in kwargs:
            season = kwargs["season"]
            results["season_colors"] = self._database["colors_season"].get(season, [])

        return results


class WeatherCheckTool(BaseTool):
    """Weather check tool"""

    def __init__(self):
        super().__init__("weather_check", "Check weather information")

    def execute(self, location: str = "Beijing", **kwargs) -> Dict[str, Any]:
        """Simulate weather check"""
        # Could integrate real weather API in production
        return {
            "location": location,
            "temperature": "20°C",
            "weather": "sunny",
            "humidity": "50%",
            "suggestion": "Suitable for lightweight clothing",
        }


class StyleRecommendTool(BaseTool):
    """Style recommendation tool"""

    def __init__(self):
        super().__init__("style_recommend", "Recommend fashion style")
        self._style_db = {
            "casual": ["T-shirt", "jeans", "sneakers", "casual pants"],
            "formal": ["suit", "shirt", "dress shoes", "tie"],
            "sporty": ["sportswear", "sneakers", "sports pants", "hoodie"],
            "street": ["streetwear", "oversized", "sneakers", "accessories"],
            "minimalist": ["solid color", "minimalist", "basic", "black white gray"],
        }

    def execute(self, style: str = "casual", **kwargs) -> Dict[str, Any]:
        return {
            "style": style,
            "items": self._style_db.get(style, []),
            "tips": f"Recommend {style} style outfit",
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
    def create_for_category(category: str, storage=None) -> AgentResources:
        """Create resources for specific category"""
        resources = AgentResources(agent_id=f"agent_{category}")

        # Add common tools
        resources.add_tool(FashionSearchTool())
        resources.add_tool(WeatherCheckTool())
        resources.add_tool(StyleRecommendTool())

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
