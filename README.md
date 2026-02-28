# 穿搭推荐多Agent系统

基于 AHP 协议的多Agent协作系统，为用户提供个性化穿搭推荐。

## 特性

- **Leader Agent**: 解析用户画像，拆分任务，统筹协调
- **Sub Agents**: 4个独立Agent（头部/上衣/裤子/鞋子），并行处理
- **AHP 协议**: 类似HTTP的Agent通信协议，任务分发与结果收集
- **pgvector存储**: 用户画像 + 穿搭推荐 → 向量数据库
- **本地LLM**: 支持接入本地模型（如 gpt-oss-20b）

## 技术栈

- Python 3.13
- LangChain (可选)
- PostgreSQL + pgvector (Docker)
- LM Studio / Ollama (本地模型)

## 快速开始

### 1. 环境配置

```bash
# 激活 conda 环境
source /opt/anaconda3/etc/profile.d/conda.sh
conda activate token

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

编辑 `.env`:

```env
# PostgreSQL + pgvector (Docker)
PG_HOST=localhost
PG_PORT=5432
PG_DATABASE=iflow
PG_USER=postgres
PG_PASSWORD=your_password

# 本地模型 (LM Studio / Ollama)
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=not-needed
LLM_MODEL=gpt-oss:20b
```

### 3. 启动 pgvector

```bash
docker run -d --name pgvector \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_DB=iflow \
  -p 5432:5432 \
  pgvector/pgvector:pg18
```

### 4. 启动本地模型

使用 LM Studio 或 Ollama 启动模型服务，确保端口配置正确。

### 5. 运行 Demo

```bash
python examples/demo.py
```

## 项目结构

```
multi-agent/
├── src/
│   ├── core/models.py       # 数据模型
│   ├── agents/
│   │   ├── leader_agent.py  # 主Agent
│   │   └── sub_agent.py     # 子Agent
│   ├── protocol/ahp.py      # AHP通信协议
│   ├── storage/postgres.py  # pgvector存储
│   └── utils/
│       ├── config.py        # 配置管理
│       └── llm.py          # LLM接入
├── examples/demo.py         # Demo示例
├── docs/                    # 技术文档
├── .env                     # 环境变量
└── requirements.txt
```

## AHP 协议

Agent Hypertext Protocol，类HTTP的Agent通信协议：

| 方法 | 说明 |
|------|------|
| `TASK` | Leader → Sub: 分发任务 |
| `RESULT` | Sub → Leader: 返回结果 |
| `HEARTBEAT` | 心跳检测 |

## 运行效果

```
📝 用户输入: 小明，性别男，22岁，厨师，爱好旅游，今天性情比较压抑

【head】亮橙色运动帽 + 复古圆形太阳镜
【top】浅青色旅行主题T恤 + 灰色风衣
【bottom】深靛蓝牛仔裤 + 卡其色长裤
【shoes】Nike Air Force 1 + Adidas UltraBoost

🎯 整体风格: 轻盈运动休闲 + 蓝绿/橙色温暖色调
```

## License

MIT
