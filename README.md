# Multi-Agent Outfit Recommendation System

A multi-Agent collaboration system based on AHP protocol, providing personalized outfit recommendations for users.

## Features

- **Leader Agent**: Parse user profile, decompose tasks, coordinate overall
- **Sub Agents**: 4 independent Agents (head/top/bottom/shoes), parallel processing
- **AHP Protocol**: HTTP-like Agent communication protocol, task dispatch and result collection
- **pgvector Storage**: User profile + Outfit recommendations → Vector database
- **Local LLM**: Support local models (e.g., gpt-oss-20b)

## Tech Stack

- Python 3.13
- LangChain (optional)
- PostgreSQL + pgvector (Docker)
- LM Studio / Ollama (local model)

## Quick Start

### 1. Environment Setup

```bash
# Activate conda environment
source /opt/anaconda3/etc/profile.d/conda.sh
conda activate token

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Edit `.env`:

```env
# PostgreSQL + pgvector (Docker)
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=iflow
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
  -e POSTGRES_DB=iflow \
  -p 5432:5432 \
  pgvector/pgvector:pg18
```

### 4. Start Local Model

Use LM Studio or Ollama to start the model service, ensure port configuration is correct.

### 5. Run Demo

```bash
python examples/demo.py
```

## Project Structure

```
multi-agent/
├── src/
│   ├── core/models.py       # Data models
│   ├── agents/
│   │   ├── leader_agent.py  # Main Agent
│   │   └── sub_agent.py     # Sub Agent
│   ├── protocol/ahp.py      # AHP communication protocol
│   ├── storage/postgres.py  # pgvector storage
│   └── utils/
│       ├── config.py        # Configuration management
│       └── llm.py          # LLM integration
├── examples/demo.py         # Demo example
├── docs/                    # Technical documentation
├── .env                     # Environment variables
└── requirements.txt
```

## AHP Protocol

Agent Hypertext Protocol, HTTP-like Agent communication protocol:

| Method        | Description                  |
| ------------- | ---------------------------- |
| `TASK`      | Leader → Sub: Dispatch task |
| `RESULT`    | Sub → Leader: Return result |
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

## License

MIT
