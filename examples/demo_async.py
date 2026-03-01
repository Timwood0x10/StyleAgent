"""
Async Outfit Recommendation System Demo (No DB version)
Demonstrates the async agent architecture with mock LLM
"""

import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.agents import AsyncLeaderAgent, AsyncOutfitAgentFactory, create_llm
from src.protocol import reset_async_message_queue


# Custom mock response for testing
class MockAsyncLLM:
    """Mock async LLM for testing"""

    def __init__(self):
        self.available = True
        self.call_count = 0

    async def ainvoke(self, prompt: str, system_prompt: str = "") -> str:
        """Mock async invoke"""
        self.call_count += 1
        await asyncio.sleep(0.2)  # Simulate LLM delay

        if "user profile" in prompt.lower():
            return json.dumps({
                "name": "Xiao Hong",
                "gender": "female",
                "age": 28,
                "occupation": "designer",
                "hobbies": ["reading"],
                "mood": "happy",
                "season": "spring",
                "occasion": "daily",
                "budget": "medium"
            })
        elif "overall style" in prompt.lower():
            return json.dumps({
                "overall_style": "Elegant casual with a touch of creativity",
                "summary": "A happy, professional look that balances creativity and sophistication"
            })
        else:
            # Category recommendation
            category = "item"
            if "head" in prompt.lower():
                category = "head"
            elif "top" in prompt.lower():
                category = "top"
            elif "bottom" in prompt.lower():
                category = "bottom"
            elif "shoes" in prompt.lower():
                category = "shoes"

            return json.dumps({
                "category": category,
                "items": [f"{category.title()} Item {self.call_count}"],
                "colors": ["blue", "white"],
                "styles": ["casual", "elegant"],
                "reasons": ["Matches user's happy mood and profession"],
                "price_range": "medium"
            })

    def invoke(self, prompt: str, system_prompt: str = "") -> str:
        """Sync invoke (fallback)"""
        return json.dumps({
            "overall_style": "Test",
            "summary": "Test"
        })


async def main():
    """Main async function"""
    print("\n" + "=" * 60)
    print("Async Outfit Recommendation System - Demo (No DB)")
    print("=" * 60)

    # Reset async message queue
    await reset_async_message_queue()

    # 1. Create mock async LLM
    print("\n[1] Creating mock async LLM...")
    llm = MockAsyncLLM()
    print(f"   MockAsyncLLM (available: {llm.available})")

    # 2. Create async Leader Agent
    print("\n[2] Creating async Leader Agent...")
    leader = AsyncLeaderAgent(llm)

    # 3. User input
    user_input = (
        "Xiao Hong, female, 28 years old, designer, likes reading, feeling happy today"
    )
    print(f"\nUser Input: {user_input}")

    # 4. Create and start async Sub Agents
    print("\n[3] Starting async Sub Agents...")
    import time
    start = time.time()
    agents = await AsyncOutfitAgentFactory.create_agents(llm)
    elapsed = time.time() - start
    print(f"   Started {len(agents)} agents in {elapsed:.2f}s: {', '.join(agents.keys())}")

    # 5. Process request
    print("\n[4] Processing request (async)...")
    start = time.time()
    result = await leader.process(user_input)
    elapsed = time.time() - start
    print(f"   Completed in {elapsed:.2f}s")

    # 6. Stop agents
    print("\n[5] Stopping agents...")
    await AsyncOutfitAgentFactory.stop_agents(agents)
    print("   All agents stopped")

    # 7. Display results
    print("\n" + result.to_display())

    print("\n" + "=" * 60)
    print("ASYNC DEMO DONE!")
    print("=" * 60)
    print(f"\nTotal LLM calls: {llm.call_count}")


if __name__ == "__main__":
    asyncio.run(main())