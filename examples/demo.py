"""
Outfit Recommendation System Demo
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.agents import LeaderAgent, OutfitAgentFactory, create_llm
from src.storage import get_storage


def main():
    """Main function"""
    print("\n" + "=" * 60)
    print("Outfit Recommendation System - AHP Protocol + pgvector Storage")
    print("=" * 60)
    
    # 1. Initialize storage
    print("\n[1] Initializing storage layer (pgvector)...")
    storage = get_storage()
    print("   OK Storage layer ready")
    
    # 2. Create LLM
    print("\n[2] Initializing LLM...")
    llm = create_llm(provider="local")
    print(f"   {llm}")
    
    if not llm.available:
        print("   FAIL Local model not connected, please start gpt-oss-20b service")
        return
    
    # 3. Reset message queue
    from src.protocol import get_message_queue
    mq = get_message_queue()
    
    # 4. Create Leader Agent
    print("\n[3] Initializing Leader Agent...")
    leader = LeaderAgent(llm)
    
    # 5. User input
    user_input = "Xiao Ming, male, 22 years old, chef, likes traveling, feeling depressed today"
    print(f"\nUser Input: {user_input}")
    
    # 6. Create and start Sub Agents
    print("\n[4] Starting Sub Agents (AHP Protocol)...")
    agents = OutfitAgentFactory.create_agents(llm)
    for agent in agents.values():
        agent.start()
    
    time.sleep(0.5)
    
    # 7. Process request (full workflow: parse -> dispatch -> collect -> aggregate -> store)
    print("\n[5] Starting processing...")
    result = leader.process(user_input)
    
    # 8. Stop Agents
    for agent in agents.values():
        agent.stop()
    
    # 9. Store results to pgvector
    print("\n[6] Storing to database...")
    session_id = result.session_id
    
    # Store user profile
    storage.save_user_profile(session_id, {
        "name": result.user_profile.name,
        "gender": result.user_profile.gender.value,
        "age": result.user_profile.age,
        "occupation": result.user_profile.occupation,
        "hobbies": result.user_profile.hobbies,
        "mood": result.user_profile.mood,
        "budget": result.user_profile.budget,
        "season": result.user_profile.season,
        "occasion": result.user_profile.occasion
    })
    
    # Store outfit recommendations
    for part in [result.head, result.top, result.bottom, result.shoes]:
        if part:
            storage.save_outfit_recommendation(
                session_id, part.category, part.items, part.colors,
                part.styles, part.reasons, part.price_range
            )
    
    print("   OK Results stored")
    
    # 10. Display results
    print("\n" + result.to_display())
    
    # 11. Verify storage
    print("\n[7] Verifying storage...")
    saved_profile = storage.get_user_profile(session_id)
    saved_outfits = storage.get_outfit_recommendations(session_id)
    print(f"   OK Saved user profile: {saved_profile['name']}")
    print(f"   OK Saved outfit recommendations: {len(saved_outfits)} items")
    
    storage.close()
    
    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)


if __name__ == "__main__":
    main()