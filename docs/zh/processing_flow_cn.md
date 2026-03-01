# iFlow 多智能体穿搭推荐系统处理流程

## 1. 完整处理流程概述

### 1.1 主流程图

```
用户输入: "我是小明，男，25岁，程序员，给我推荐一套商务装"

┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Leader Agent 解析用户信息                                │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ parse_user_profile(user_input)
   │
   ├─→ LLM 调用 (提取信息)
   │   name=小明, gender=男, age=25, occupation=程序员
   │
   └─→ 返回 UserProfile 对象

┌─────────────────────────────────────────────────────────────────┐
│ Step 2: 加载用户上下文 (RAG)                                     │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ _enrich_user_context(profile)
   │
   ├─→ 向量数据库搜索相似历史
   │   - previous_recommendations: 历史推荐
   │   - preferred_colors: 喜好的颜色
   │   - rejected_items: 拒绝的单品
   │
   └─→ 增强 UserProfile

┌─────────────────────────────────────────────────────────────────┐
│ Step 3: 分析需要的任务类别                                       │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ _analyze_required_categories(profile)
   │
   ├─→ LLM 分析场合: "商务正装"
   │
   └─→ 确定类别: ["head", "top", "bottom", "shoes"]

┌─────────────────────────────────────────────────────────────────┐
│ Step 4: 创建任务 & 注册                                          │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ create_tasks(profile)
   │
   ├─→ 为每个类别创建 OutfitTask
   │
   └─→ TaskRegistry.register_task()
       - 写入数据库 (tasks 表)
       - 内存缓存

┌─────────────────────────────────────────────────────────────────┐
│ Step 5: 通过 AHP 协议分发任务 (并行)                             │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ _dispatch_tasks_via_ahp(tasks, profile)
   │
   ├─→ TokenController.create_compact_instruction()
   │   (压缩指令，控制 token 消耗)
   │
   ├─→ AHPMessage 发送到各 Agent 队列:
   │   ├─→ agent_head   (MessageQueue["agent_head"])
   │   ├─→ agent_top    (MessageQueue["agent_top"])
   │   ├─→ agent_bottom (MessageQueue["agent_bottom"])
   │   └─→ agent_shoes  (MessageQueue["agent_shoes"])
   │
   │  消息内容:
   │  {
   │    "method": "TASK",
   │    "user_info": {...},
   │    "category": "top",
   │    "compact_instruction": "...",
   │    "token_limit": 500
   │  }

┌─────────────────────────────────────────────────────────────────┐
│ Step 6: Sub Agent 处理任务 (独立线程并行)                         │
└─────────────────────────────────────────────────────────────────┘
   │
   │  Sub Agent 1 (agent_top) 为例:
   │
   ├─→ _run_loop() 监听消息队列
   │
   ├─→ receive() 获取 TASK 消息
   │
   ├─→ send_progress(10%) → Leader
   │
   ├─→ _recommend(profile, instruction)
   │   │
   │   ├─1. 获取 RAG 上下文
   │   │   search_similar(embedding) → 历史推荐
   │   │
   │   ├─2. 调用 Tools
   │   │   ├─ FashionSearchTool (mood/season/occupation)
   │   │   ├─ WeatherCheckTool
   │   │   └─ StyleRecommendTool
   │   │
   │   ├─3. 构建 Prompt
   │   │   - 工具结果 + RAG上下文 + 用户信息
   │   │
   │   ├─4. LLM 调用
   │   │   - Circuit Breaker 检查
   │   │   - Retry Handler 重试
   │   │
   │   └─5. 解析 LLM 响应
   │
   ├─→ send_progress(50%, 90%) → Leader
   │
   └─→ send_result() → Leader
       {
         "category": "top",
         "items": ["西装外套", "衬衫"],
         "colors": ["深蓝", "白色"],
         "styles": ["商务正装"],
         "reasons": ["符合商务场合", "搭配经典"],
         "price_range": "medium"
       }

┌─────────────────────────────────────────────────────────────────┐
│ Step 7: Leader 收集结果                                         │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ _collect_results(tasks, timeout=60s)
   │
   ├─→ 等待各 Agent 的 RESULT 消息
   │
   ├─→ 验证每个结果 (ResultValidator)
   │   - 字段完整性
   │   - 数据类型
   │   - 内容合理性
   │   - 自动修复
   │
   ├─→ 超时未收到的任务 → DLQ
   │
   └─→ 返回 Dict[category → OutfitRecommendation]

┌─────────────────────────────────────────────────────────────────┐
│ Step 8: 聚合结果 & 生成最终推荐                                  │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ aggregate_results(profile, results)
   │
   ├─→ LLM 调用生成:
   │   - overall_style: 整体风格
   │   - summary: 总结
   │
   ├─→ _save_for_rag(results)
   │   └─→ 保存到向量数据库
   │
   └─→ 返回 OutfitResult

┌─────────────────────────────────────────────────────────────────┐
│ Step 9: 存储到数据库                                            │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ save_user_profile() → user_profiles 表
   ├─→ save_outfit_recommendation() → outfit_recommendations 表
   ├─→ save_vector() → semantic_vectors 表 (RAG)
   └─→ update_session() → sessions 表

最终返回给用户完整的穿搭推荐方案
```

---

## 2. AHP 协议消息流程

### 2.1 消息类型

| 消息类型 | 方向 | 说明 |
|----------|------|------|
| TASK | Leader → Sub | 分发任务 |
| RESULT | Sub → Leader | 返回结果 |
| PROGRESS | Sub → Leader | 进度报告 |
| ACK | Bidirectional | 消息确认 |
| HEARTBEAT | Bidirectional | 心跳检测 |

### 2.2 消息流转

```
Leader                                    Sub Agents
  │                                          │
  │───────── TASK (agent_top) ──────────────→│
  │←──────── ACK ────────────────────────────│
  │                                          │
  │         (处理中...)                       │
  │                                          │
  │←────── PROGRESS 10% ─────────────────────│
  │←────── PROGRESS 50% ─────────────────────│
  │←────── PROGRESS 90% ─────────────────────│
  │                                          │
  │←──────── RESULT ──────────────────────────│
  │───────── ACK ────────────────────────────→│
  │                                          │
```

---

## 3. Token 控制流程

### 3.1 压缩指令生成

```
原始任务描述:
"推荐商务正装，需要考虑用户的职业是程序员，年龄25岁，性别男"

TokenController.create_compact_instruction()

压缩后 (Token Limit: 500):
─────────────────────────────────────────
Task: top
Target: 小明
User Info: Gender:男; Age:25; Occupation:程序员; Mood:normal
Requirement: 推荐商务正装
Context: {RAG历史摘要}
─────────────────────────────────────────
```

### 3.2 Token 节省效果

| 项目 | 原始 | 压缩后 | 节省 |
|------|------|--------|------|
| 指令长度 | ~500 tokens | ~150 tokens | 70% |
| 总 Token 消耗 | ~2000 | ~1200 | 40% |

---

## 4. 错误处理流程

### 4.1 重试流程

```
LLM 调用失败
     │
     ▼
RetryHandler.should_retry(error)
     │
     ├─→ 检查错误类型 (TIMEOUT/NETWORK/LLM_FAILED)
     │
     ├─→ 检查重试次数 < max_retries (3)
     │
     ├─→ 计算延迟 (指数退避)
     │   attempt=1: 1s
     │   attempt=2: 2s
     │   attempt=3: 4s
     │
     ├─→ sleep(delay)
     │
     └─→ 重新执行 LLM 调用
         │
         ├─→ 成功 → 返回结果
         │
         └─→ 失败 → 重复或进入断路器
```

### 4.2 断路器流程

```
Circuit Breaker 状态转换:

Closed (正常) ─────────────────────────────────────┐
  │                                              │
  │  连续失败 5 次                               │
  ▼                                              │
Open (熔断)                                      │
  │                                              │
  │  60 秒后                                    │
  ▼                                              │
Half-Open (测试)                                 │
  │                                              │
  │  测试调用成功                                │
  ▼                                              │
Closed (恢复) ───────────────────────────────────┘
```

### 4.3 死信队列流程

```
任务处理失败
     │
     ▼
MessageQueue.to_dlq(agent_id, message, error)
     │
     ▼
DLQ 存储:
{
  "message": {...},
  "error": "error details",
  "timestamp": "...",
  "retry_count": 3
}
     │
     ▼
可查询失败消息，分析原因，手动重试
```

---

## 5. 多轮对话流程

### 5.1 用户反馈处理

```
用户: "太贵了"
     │
     ▼
InteractiveDemo.parse_feedback()
     │
     ├─→ 识别反馈类型: TOO_EXPENSIVE
     │
     ├─→ 提取关键词: "贵" → budget=low
     │
     └─→ 构建 refined_prompt

用户: "不喜欢这个颜色"
     │
     ▼
识别反馈类型: DONT_LIKE_COLOR
     │
     ├─→ 提取颜色: "蓝色"
     │
     └─→ 添加到 rejected_items
```

### 5.2 反馈后的重推荐流程

```
反馈: "太贵了"
     │
     ▼
更新 UserProfile
├─ budget: "medium" → "low"
└─ rejected_items: [当前推荐的单品]

     │
     ▼
LeaderAgent.process( refined_input )
     │
     ├─→ parse_user_profile() (已有信息)
     │
     ├─→ _enrich_user_context() 
     │   (包含被拒绝的单品)
     │
     ├─→ create_tasks()
     │
     ├─→ 分发任务 (含反馈上下文)
     │
     └─→ 返回调整后的推荐
```

---

## 6. RAG 上下文增强流程

### 6.1 历史推荐检索

```
当前用户: {mood: normal, season: spring, occupation: programmer}

_build_rag_query(profile)
→ "Recommend top for user who is male, age 25, 
   occupation programmer, mood normal, season spring,
   occasion daily, budget medium"

     │
     ▼
LLM.embed(query)
→ embedding: [0.12, -0.34, 0.56, ...]

     │
     ▼
StorageLayer.search_similar(embedding, limit=3)
     │
     ├─→ 结果1: "items: 格子衬衫, colors: 浅蓝..."
     │    metadata: {mood: normal, season: spring}
     │
     ├─→ 结果2: "items: 休闲西装, colors: 灰色..."
     │    metadata: {mood: happy, season: autumn}
     │
     └─→ 结果3: ...

     │
     ▼
格式化上下文:
[Historical Similar Recommendations]:
- Similar 1: items: 格子衬衫, colors: 浅蓝 (mood: normal, season: spring)
- Similar 2: items: 休闲西装, colors: 灰色 (mood: happy, season: autumn)
```

### 6.2 上下文注入

```
最终 Prompt 结构:

[Compact Instruction]
Task: top | Target: 小明 | ...

[Historical Similar Recommendations]
- Similar 1: items: 格子衬衫...
- Similar 2: items: 休闲西装...

[User Info]
- Name: 小明
- Gender: 男
- Age: 25
- Occupation: 程序员
- ...

[Tool Results]
- Fashion: colors for mood: [蓝色, 白色]
- Weather: 15-25°C, sunny
- Style: items: [T恤, 牛仔裤]

请根据以上信息推荐...
```

---

## 7. 会话管理流程

### 7.1 会话生命周期

```
┌─────────────────────────────────────────────────────────────┐
│                        会话开始                               │
│  session_id = uuid.generate()                               │
│  StorageLayer.save_session() → sessions 表                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     用户输入 → 处理 → 输出                    │
│  (多次循环)                                                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       会话结束                                │
│  StorageLayer.update_session(                               │
│    status="completed",                                      │
│    final_output=result,                                     │
│    summary=摘要                                              │
│  )                                                          │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 历史记录查询

```
用户: "之前给我推荐过什么？"
     │
     ▼
InteractiveDemo.show_history()
     │
     ├─→ session_history: 当前会话历史
     │
     └─→ StorageLayer.get_session_history()
         └─→ 查询 sessions 表

显示:
- 2024-01-15: 推荐商务正装
- 2024-01-20: 推荐休闲装
- 2024-01-25: 推荐约会装
```

---

## 8. 验证流程

### 8.1 结果验证步骤

```
收到 Sub Agent 的 RESULT:
{
  "category": "top",
  "items": ["西装外套"],
  "colors": ["深蓝"],
  "styles": ["商务"],
  "reasons": ["适合正式场合"]
}

     │
     ▼
ResultValidator.validate(result, "outfit", "top")
     │
     ├─→ 1. 检查必需字段
     │   items ✓, colors ✓, styles ✓, reasons ✓
     │
     ├─→ 2. 检查数据类型
     │   items: list ✓, colors: list ✓
     │
     ├─→ 3. 检查内容合理性
     │   items 长度 ≥ 1 ✓
     │   colors 非空 ✓
     │
     └─→ 返回 ValidationResult
         is_valid: true
         errors: []
         warnings: []

     │
     ├─→ 验证失败?
     │   ├─→ 自动修复 (auto_fix)
     │   └─→ 记录警告
     │
     └─→ 验证成功 → 聚合
```

### 8.2 验证级别

| 级别 | 说明 |
|------|------|
| STRICT | 严格模式，必须完全符合格式 |
| NORMAL | 正常模式，关键字段必须存在 |
| LENIENT | 宽松模式，仅基础检查 |

---

## 9. 完整数据流总结

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 用户输入  │───→│  Leader  │───→│  AHP     │───→│  Sub     │
│          │    │  Agent   │    │  Queue   │    │  Agents  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
                    │                                   │
                    │                                   ▼
                    │                           ┌──────────────┐
                    │                           │   Tools      │
                    │                           │   + RAG      │
                    │                           │   + LLM      │
                    │                           └──────────────┘
                    │                                   │
                    ▼                                   ▼
              ┌──────────┐                      ┌──────────┐
              │ Result   │                      │  Result  │
              │Validator │◄─────────────────────│  Queue   │
              └──────────┘                      └──────────┘
                    │                                 
                    ▼                                 
              ┌──────────┐                     
              │ Aggregate│                     
              │  + RAG   │                     
              └──────────┘                     
                    │                                 
                    ▼                                 
              ┌──────────┐                     
              │ Storage  │                     
              │  Layer   │                     
              └──────────┘                     
                    │                                 
                    ▼                                 
              ┌──────────┐                     
              │ 返回结果 │                     
              │   给用户 │                     
              └──────────┘
```
