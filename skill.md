# Multi-Agent Outfit Recommendation System

## System Capabilities

An intelligent outfit recommendation system based on a multi-agent collaboration architecture, providing users with personalized clothing coordination suggestions.

---

## Agent Capabilities

### Leader Agent
- **User Profile Analysis**: Extract user characteristics from natural language input (gender, age, occupation, mood, budget, etc.)
- **Task Orchestration**: Intelligently analyze user requirements to determine recommended categories (head/top/bottom/shoes)
- **Style Coordination**: Ensure unified coordination style through two-stage distribution
- **Result Aggregation**: Integrate recommendations from Sub Agents to generate final outfit solutions

### Sub Agent (agent_head / agent_top / agent_bottom / agent_shoes)
- **Outfit Recommendation**: Recommend corresponding category clothing based on user profile
- **Tool Invocation**: Integrate fashion databases, weather queries, style recommendations, and other tools
- **RAG Retrieval**: Retrieve similar cases from historical recommendations as references

---

## Input Format

### User Input Example
```
"Xiao Ming, male, 22 years old, chef, likes traveling, feeling depressed today"
```

### Extracted User Profile
```json
{
  "name": "Xiao Ming",
  "gender": "male",
  "age": 22,
  "occupation": "chef",
  "hobbies": ["traveling"],
  "mood": "depressed",
  "budget": "medium",
  "season": "spring",
  "occasion": "daily"
}
```

---

## Output Format

### Recommendation Result
```json
{
  "head": {
    "items": ["baseball cap", "minimalist sunglasses"],
    "colors": ["navy blue", "white"],
    "styles": ["casual", "sporty"],
    "reasons": ["Enhances vitality", "Suitable for chef work"],
    "price_range": "¥100-300"
  },
  "top": {
    "items": ["light breathable shirt", "casual jacket"],
    "colors": ["light blue", "white"],
    "styles": ["casual", "professional"],
    "reasons": ["Breathable and comfortable", "Suitable for work scenarios"],
    "price_range": "¥200-500"
  },
  "bottom": {...},
  "shoes": {...},
  "overall_style": "Lightweight and practical daily outfit",
  "summary": "The overall style is simple and elegant, considering the user's mood and occupational needs"
}
```

---

## Tools

### FashionSearchTool
- Recommend colors and styles based on user mood, occupation, and season

### WeatherCheckTool
- Query weather conditions and provide clothing suggestions

### StyleRecommendTool
- Recommend specific items based on style type

---

## Internal Protocol

### AHP (Agent Hierarchical Protocol)

Communication protocol between agents, supporting the following message types:

| Method | Direction | Description |
|--------|-----------|-------------|
| TASK | Leader → Sub | Task distribution |
| RESULT | Sub → Leader | Return results |
| PROGRESS | Sub → Leader | Progress reporting |
| ACK | Bidirectional | Message acknowledgment |
| HEARTBEAT | Bidirectional | Liveness detection |

---

## Tech Stack

- **LLM**: Local model (gpt-oss:20b) / OpenAI
- **Storage**: PostgreSQL + pgvector (vector search)
- **Protocol**: Self-developed AHP Protocol
- **Python**: 3.13, asyncio, threading
