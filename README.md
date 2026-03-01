# Multi-Agent Outfit Recommendation System

A multi-Agent collaboration system based on AHP protocol, providing personalized outfit recommendations for users.

## Features

- **Leader Agent**: Parse user profile, decompose tasks, coordinate overall
- **Sub Agents**: 4 independent Agents (head/top/bottom/shoes), parallel processing
- **AHP Protocol**: HTTP-like Agent communication protocol, task dispatch and result collection
- **pgvector Storage**: User profile + Outfit recommendations → Vector database
- **Local LLM**: Support local models (e.g., gpt-oss-20b)
- **Circuit Breaker & Retry**: Fault tolerance with exponential backoff
- **RAG Support**: Vector similarity search for outfit recommendations

## Tech Stack

- Python 3.13
- PostgreSQL + pgvector (Docker)
- LM Studio / Ollama (local model)
- pytest (testing)

## Quick Start

### 1. Environment Setup

```bash
# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy and edit `.env.example`:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# PostgreSQL + pgvector (Docker)
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=style
PG_USER=postgres
PG_PASSWORD=your_password

# Local model (LM Studio / Ollama)
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=not-needed
LLM_MODEL=gpt-oss:20b
```

### 3. Start pgvector

```bash
docker run -d --name pgvector \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_DB=style \
  -p 5432:5432 \
  pgvector/pgvector:pg18
```

### 4. Start Local Model

Use LM Studio or Ollama to start the model service, ensure port configuration is correct.

### 5. Run Demo

```bash
# demo
python examples/demo.py

# Interactive 
python examples/demo_interactive.py

```

### 6. Run Tests

```bash
python -m pytest tests/ -v
```

## Project Structure

```
multi-agent/
├── src/
│   ├── core/
│   │   ├── models.py       # Data models (UserProfile, OutfitTask, etc.)
│   │   ├── errors.py       # Error handling (RetryHandler, CircuitBreaker)
│   │   ├── registry.py     # Task registry
│   │   └── validator.py    # Result validation
│   ├── agents/
│   │   ├── leader_agent.py # Main Agent (LeaderAgent, AsyncLeaderAgent)
│   │   ├── sub_agent.py    # Sub Agent
│   │   └── resources.py    # Agent resources & tools
│   ├── protocol/
│   │   └── ahp.py          # AHP communication protocol
│   ├── storage/
│   │   └── postgres.py     # pgvector storage
│   └── utils/
│       ├── config.py       # Configuration management
│       ├── llm.py          # LLM integration
│       └── logger.py       # Logging utility
├── examples/
│   ├── demo.py             # Interactive demo
│   ├── demo_simple.py      # Simple demo
│   └── demo_async.py       # Async demo
├── tests/                   # Unit tests
├── docs/                    # Technical documentation
├── .env.example            # Environment variables template
└── requirements.txt
```

## AHP Protocol

Agent Hypertext Protocol, HTTP-like Agent communication protocol:

| Method        | Description                  |
| ------------- | ---------------------------- |
| `TASK`      | Leader → Sub: Dispatch task |
| `RESULT`    | Sub → Leader: Return result |
| `PROGRESS`  | Progress updates             |
| `HEARTBEAT` | Heartbeat detection          |

## Example Output

```
User Input: Xiao Ming, male, 22 years old, chef, likes traveling, feeling depressed today

【head】Bright orange sports cap + Vintage round sunglasses
【top】Light cyan travel-themed T-shirt + Gray windbreaker
【bottom】Deep indigo jeans + Khaki long pants
【shoes】Nike Air Force 1 + Adidas UltraBoost

Overall Style: Light sports casual + Blue-green/orange warm tones
```

## Configuration

Key configuration options in `config.yaml` or environment variables:

- `SUB_AGENT_CATEGORIES`: Categories for sub-agents (default: head, top, bottom, shoes)
- `SUB_AGENT_PREFIX`: Prefix for agent IDs (default: agent_)
- `LLM_*`: LLM provider settings
- `PG_*`: PostgreSQL connection settings

## License

MIT
