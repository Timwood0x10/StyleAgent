# iFlow Multi-Agent Outfit Recommendation System Processing Flow

## 1. Complete Processing Flow Overview

### 1.1 Main Flow Diagram

```
User Input: "I'm Xiaoming, male, 25 years old, programmer, recommend business attire"

┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Leader Agent Parses User Information                   │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ parse_user_profile(user_input)
   │
   ├─→ LLM call (extract info)
   │   name=Xiaoming, gender=male, age=25, occupation=programmer
   │
   └─→ Return UserProfile object

┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Load User Context (RAG)                                │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ _enrich_user_context(profile)
   │
   ├─→ Vector DB search for similar history
   │   - previous_recommendations: historical recommendations
   │   - preferred_colors: preferred colors
   │   - rejected_items: rejected items
   │
   └─→ Enhanced UserProfile

┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Analyze Required Task Categories                        │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ _analyze_required_categories(profile)
   │
   ├─→ LLM analyzes occasion: "business formal"
   │
   └─→ Determine categories: ["head", "top", "bottom", "shoes"]

┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Create Tasks & Register                                │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ create_tasks(profile)
   │
   ├─→ Create OutfitTask for each category
   │
   └─→ TaskRegistry.register_task()
       - Write to database (tasks table)
       - Memory cache

┌─────────────────────────────────────────────────────────────────┐
│ Step 5: Dispatch Tasks via AHP Protocol (Parallel)              │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ _dispatch_tasks_via_ahp(tasks, profile)
   │
   ├─→ TokenController.create_compact_instruction()
   │   (compress instructions, control token consumption)
   │
   ├─→ AHPMessage sent to each Agent queue:
   │   ├─→ agent_head   (MessageQueue["agent_head"])
   │   ├─→ agent_top    (MessageQueue["agent_top"])
   │   ├─→ agent_bottom (MessageQueue["agent_bottom"])
   │   └─→ agent_shoes  (MessageQueue["agent_shoes"])
   │
   │  Message content:
   │  {
   │    "method": "TASK",
   │    "user_info": {...},
   │    "category": "top",
   │    "compact_instruction": "...",
   │    "token_limit": 500
   │  }

┌─────────────────────────────────────────────────────────────────┐
│ Step 6: Sub Agent Processes Task (Independent Thread, Parallel) │
└─────────────────────────────────────────────────────────────────┘
   │
   │  Sub Agent 1 (agent_top) as example:
   │
   ├─→ _run_loop() listens to message queue
   │
   ├─→ receive() gets TASK message
   │
   ├─→ send_progress(10%) → Leader
   │
   ├─→ _recommend(profile, instruction)
   │   │
   │   ├─1. Get RAG context
   │   │   search_similar(embedding) → historical recommendations
   │   │
   │   ├─2. Call Tools
   │   │   ├─ FashionSearchTool (mood/season/occupation)
   │   │   ├─ WeatherCheckTool
   │   │   └─ StyleRecommendTool
   │   │
   │   ├─3. Build Prompt
   │   │   - Tool results + RAG context + user info
   │   │
   │   ├─4. LLM call
   │   │   - Circuit Breaker check
   │   │   - Retry Handler retry
   │   │
   │   └─5. Parse LLM response
   │
   ├─→ send_progress(50%, 90%) → Leader
   │
   └─→ send_result() → Leader
       {
         "category": "top",
         "items": ["suit jacket", "shirt"],
         "colors": ["navy blue", "white"],
         "styles": ["business formal"],
         "reasons": ["suitable for business", "classic pairing"],
         "price_range": "medium"
       }

┌─────────────────────────────────────────────────────────────────┐
│ Step 7: Leader Collects Results                                 │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ _collect_results(tasks, timeout=60s)
   │
   ├─→ Wait for RESULT messages from each Agent
   │
   ├─→ Validate each result (ResultValidator)
   │   - Field completeness
   │   - Data types
   │   - Content reasonableness
   │   - Auto-fix
   │
   ├─→ Timeout → DLQ
   │
   └─→ Return Dict[category → OutfitRecommendation]

┌─────────────────────────────────────────────────────────────────┐
│ Step 8: Aggregate Results & Generate Final Recommendation      │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ aggregate_results(profile, results)
   │
   ├─→ LLM call generates:
   │   - overall_style: overall style
   │   - summary: summary
   │
   ├─→ _save_for_rag(results)
   │   └─→ Save to vector database
   │
   └─→ Return OutfitResult

┌─────────────────────────────────────────────────────────────────┐
│ Step 9: Store to Database                                      │
└─────────────────────────────────────────────────────────────────┘
   │
   ├─→ save_user_profile() → user_profiles table
   ├─→ save_outfit_recommendation() → outfit_recommendations table
   ├─→ save_vector() → semantic_vectors table (RAG)
   └─→ update_session() → sessions table

Return complete outfit recommendation to user
```

---

## 2. AHP Protocol Message Flow

### 2.1 Message Types

| Message Type | Direction | Description |
|--------------|-----------|-------------|
| TASK | Leader → Sub | Dispatch task |
| RESULT | Sub → Leader | Return result |
| PROGRESS | Sub → Leader | Progress report |
| ACK | Bidirectional | Message acknowledgment |
| HEARTBEAT | Bidirectional | Heartbeat check |

### 2.2 Message Exchange

```
Leader                                    Sub Agents
  │                                          │
  │───────── TASK (agent_top) ──────────────→│
  │←──────── ACK ────────────────────────────│
  │                                          │
  │         (Processing...)                   │
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

## 3. Token Control Flow

### 3.1 Compact Instruction Generation

```
Original task description:
"Recommend business formal attire, considering user is a programmer, 
age 25, male gender"

TokenController.create_compact_instruction()

Compressed (Token Limit: 500):
─────────────────────────────────────────
Task: top
Target: Xiaoming
User Info: Gender:male; Age:25; Occupation:programmer; Mood:normal
Requirement: Recommend business formal
Context: {RAG history summary}
─────────────────────────────────────────
```

### 3.2 Token Savings

| Item | Original | Compressed | Savings |
|------|----------|------------|---------|
| Instruction length | ~500 tokens | ~150 tokens | 70% |
| Total Token consumption | ~2000 | ~1200 | 40% |

---

## 4. Error Handling Flow

### 4.1 Retry Flow

```
LLM call fails
     │
     ▼
RetryHandler.should_retry(error)
     │
     ├─→ Check error type (TIMEOUT/NETWORK/LLM_FAILED)
     │
     ├─→ Check retry count < max_retries (3)
     │
     ├─→ Calculate delay (exponential backoff)
     │   attempt=1: 1s
     │   attempt=2: 2s
     │   attempt=3: 4s
     │
     ├─→ sleep(delay)
     │
     └─→ Retry LLM call
         │
         ├─→ Success → Return result
         │
         └─→ Failure → Repeat or enter circuit breaker
```

### 4.2 Circuit Breaker Flow

```
Circuit Breaker State Transition:

Closed (Normal) ─────────────────────────────────────┐
  │                                              │
  │  5 consecutive failures                      │
  ▼                                              │
Open (Tripped)                                    │
  │                                              │
  │  60 seconds timeout                          │
  ▼                                              │
Half-Open (Testing)                               │
  │                                              │
  │  Test call succeeds                          │
  ▼                                              │
Closed (Recovered) ────────────────────────────────┘
```

### 4.3 Dead Letter Queue Flow

```
Task processing fails
     │
     ▼
MessageQueue.to_dlq(agent_id, message, error)
     │
     ▼
DLQ storage:
{
  "message": {...},
  "error": "error details",
  "timestamp": "...",
  "retry_count": 3
}
     │
     ▼
Can query failed messages, analyze reasons, manually retry
```

---

## 5. Multi-turn Conversation Flow

### 5.1 User Feedback Processing

```
User: "Too expensive"
     │
     ▼
InteractiveDemo.parse_feedback()
     │
     ├─→ Identify feedback type: TOO_EXPENSIVE
     │
     ├─→ Extract keyword: "expensive" → budget=low
     │
     └─→ Build refined_prompt

User: "Don't like this color"
     │
     ▼
Identify feedback type: DONT_LIKE_COLOR
     │
     ├─→ Extract color: "blue"
     │
     └─→ Add to rejected_items
```

### 5.2 Re-recommendation Flow After Feedback

```
Feedback: "Too expensive"
     │
     ▼
Update UserProfile
├─ budget: "medium" → "low"
└─ rejected_items: [current recommended items]

     │
     ▼
LeaderAgent.process( refined_input )
     │
     ├─→ parse_user_profile() (existing info)
     │
     ├─→ _enrich_user_context()
     │   (includes rejected items)
     │
     ├─→ create_tasks()
     │
     ├─→ Dispatch tasks (with feedback context)
     │
     └─→ Return adjusted recommendations
```

---

## 6. RAG Context Enhancement Flow

### 6.1 Historical Recommendation Retrieval

```
Current user: {mood: normal, season: spring, occupation: programmer}

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
     ├─→ Result1: "items: plaid shirt, colors: light blue..."
     │    metadata: {mood: normal, season: spring}
     │
     ├─→ Result2: "items: casual suit, colors: gray..."
     │    metadata: {mood: happy, season: autumn}
     │
     └─→ Result3: ...

     │
     ▼
Format context:
[Historical Similar Recommendations]:
- Similar 1: items: plaid shirt, colors: light blue (mood: normal, season: spring)
- Similar 2: items: casual suit, colors: gray (mood: happy, season: autumn)
```

### 6.2 Context Injection

```
Final Prompt Structure:

[Compact Instruction]
Task: top | Target: Xiaoming | ...

[Historical Similar Recommendations]
- Similar 1: items: plaid shirt...
- Similar 2: items: casual suit...

[User Info]
- Name: Xiaoming
- Gender: male
- Age: 25
- Occupation: programmer
- ...

[Tool Results]
- Fashion: colors for mood: [blue, white]
- Weather: 15-25°C, sunny
- Style: items: [T-shirt, jeans]

Please recommend based on above...
```

---

## 7. Session Management Flow

### 7.1 Session Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                      Session Start                          │
│  session_id = uuid.generate()                              │
│  StorageLayer.save_session() → sessions table             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Input → Process → Output                  │
│                   (Multiple loops)                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Session End                            │
│  StorageLayer.update_session(                              │
│    status="completed",                                    │
│    final_output=result,                                   │
│    summary=summary                                        │
│  )                                                        │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 History Query

```
User: "What did you recommend before?"
     │
     ▼
InteractiveDemo.show_history()
     │
     ├─→ session_history: current session history
     │
     └─→ StorageLayer.get_session_history()
         └─→ Query sessions table

Display:
- 2024-01-15: Recommended business formal
- 2024-01-20: Recommended casual
- 2024-01-25: Recommended date outfit
```

---

## 8. Validation Flow

### 8.1 Result Validation Steps

```
Received RESULT from Sub Agent:
{
  "category": "top",
  "items": ["suit jacket"],
  "colors": ["navy blue"],
  "styles": ["business"],
  "reasons": ["suitable for formal occasion"]
}

     │
     ▼
ResultValidator.validate(result, "outfit", "top")
     │
     ├─→ 1. Check required fields
     │   items ✓, colors ✓, styles ✓, reasons ✓
     │
     ├─→ 2. Check data types
     │   items: list ✓, colors: list ✓
     │
     ├─→ 3. Check content reasonableness
     │   items length ≥ 1 ✓
     │   colors not empty ✓
     │
     └─→ Return ValidationResult
         is_valid: true
         errors: []
         warnings: []

     │
     ├─→ Validation failed?
     │   ├─→ Auto-fix (auto_fix)
     │   └─→ Record warnings
     │
     └─→ Validation success → Aggregate
```

### 8.2 Validation Levels

| Level | Description |
|-------|-------------|
| STRICT | Strict mode, must match format exactly |
| NORMAL | Normal mode, key fields must exist |
| LENIENT | Lenient mode, basic checks only |

---

## 9. Complete Data Flow Summary

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  User   │───→│  Leader  │───→│  AHP     │───→│  Sub     │
│  Input  │    │  Agent   │    │  Queue   │    │  Agents  │
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
              │ Return   │                     
              │ Result   │                     
              │ to User  │                     
              └──────────┘
```
