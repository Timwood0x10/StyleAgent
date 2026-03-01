"""
Async Outfit Recommendation System Demo (No DB version)
Demonstrates the async agent architecture with real LLM
"""

import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.agents import AsyncLeaderAgent, AsyncOutfitAgentFactory
from src.protocol import reset_async_message_queue
from src.utils.llm import LocalLLM


async def main():
    """Main async function"""
    print("\n" + "=" * 60)
    print("Async Outfit Recommendation System - Demo (No DB)")
    print("=" * 60)

    # Reset async message queue
    await reset_async_message_queue()

    # 1. Create real async LLM
    print("\n[1] Creating async LLM...")
    llm = LocalLLM()
    print(f"   LocalLLM (available: {llm.available})")

    if not llm.available:
        print("   WARNING: LLM not available, demo may fail!")

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
    print(
        f"   Started {len(agents)} agents in {elapsed:.2f}s: {', '.join(agents.keys())}"
    )

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


if __name__ == "__main__":
    asyncio.run(main())
