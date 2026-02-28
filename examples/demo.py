"""
穿搭推荐系统 Demo
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.agents import LeaderAgent, OutfitAgentFactory, create_llm
from src.storage import get_storage


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🌟 穿搭推荐系统 - AHP 协议 + pgvector 存储")
    print("=" * 60)
    
    # 1. 初始化存储
    print("\n[1] 初始化存储层 (pgvector)...")
    storage = get_storage()
    print("   ✅ 存储层就绪")
    
    # 2. 创建 LLM
    print("\n[2] 初始化 LLM...")
    llm = create_llm(provider="local")
    print(f"   {llm}")
    
    if not llm.available:
        print("   ❌ 本地模型未连接，请启动 gpt-oss-20b 服务")
        return
    
    # 3. 重置消息队列
    from src.protocol import get_message_queue
    mq = get_message_queue()
    
    # 4. 创建 Leader Agent
    print("\n[3] 初始化 Leader Agent...")
    leader = LeaderAgent(llm)
    
    # 5. 用户输入
    user_input = "小明，性别男，22岁，厨师，爱好旅游，今天性情比较压抑"
    print(f"\n📝 用户输入: {user_input}")
    
    # 6. 创建 Sub Agents 并启动
    print("\n[4] 启动 Sub Agents (AHP 协议)...")
    agents = OutfitAgentFactory.create_agents(llm)
    for agent in agents.values():
        agent.start()
    
    time.sleep(0.5)
    
    # 7. 处理请求 (完整流程: 解析 -> 分发 -> 收集 -> 汇总 -> 存储)
    print("\n[5] 开始处理...")
    result = leader.process(user_input)
    
    # 8. 停止 Agents
    for agent in agents.values():
        agent.stop()
    
    # 9. 存储结果到 pgvector
    print("\n[6] 存储到数据库...")
    session_id = result.session_id
    
    # 存储用户画像
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
    
    # 存储穿搭推荐
    for part in [result.head, result.top, result.bottom, result.shoes]:
        if part:
            storage.save_outfit_recommendation(
                session_id, part.category, part.items, part.colors,
                part.styles, part.reasons, part.price_range
            )
    
    print("   ✅ 结果已存储")
    
    # 10. 展示结果
    print("\n" + result.to_display())
    
    # 11. 验证存储
    print("\n[7] 验证存储...")
    saved_profile = storage.get_user_profile(session_id)
    saved_outfits = storage.get_outfit_recommendations(session_id)
    print(f"   ✅ 已保存用户画像: {saved_profile['name']}")
    print(f"   ✅ 已保存穿搭推荐: {len(saved_outfits)} 条")
    
    storage.close()
    
    print("\n" + "=" * 60)
    print("✅ 完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()