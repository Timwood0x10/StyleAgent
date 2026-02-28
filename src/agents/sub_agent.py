"""
Sub Agent - 穿搭推荐执行 (使用 AHP 协议)
"""
import json
import threading
from typing import Dict, Any, Optional
from ..core.models import UserProfile, OutfitRecommendation, OutfitTask, TaskStatus
from ..utils.llm import LocalLLM
from ..protocol import get_message_queue, AHPReceiver, AHPSender


# 各品类的系统提示
CATEGORY_PROMPTS = {
    "head": """你是一位配饰专家，擅长推荐帽子、眼镜、项链、耳饰等头部配饰。
根据用户的特征和心情，推荐适合的配饰。
注意:
- 心情压抑时，选择能带来活力或安慰感的配饰
- 考虑用户的职业和日常活动
- 给出具体的颜色和款式建议""",
    
    "top": """你是一位上装搭配专家，擅长推荐T恤、衬衫、外套、卫衣等上衣。
根据用户的特征和心情，推荐适合的上装。
注意:
- 心情压抑时，选择能提升心情的颜色(如亮色)
- 考虑季节和场合
- 给出具体的款式和颜色建议""",
    
    "bottom": """你是一位裤装搭配专家，擅长推荐牛仔裤、休闲裤、西裤等下装。
根据用户的特征和心情，推荐适合的裤子。
注意:
- 考虑与上装的搭配
- 舒适度和场合需求
- 给出具体的款式和颜色建议""",
    
    "shoes": """你是一位鞋履搭配专家，擅长推荐各种鞋履。
根据用户的特征和心情，推荐适合的鞋子。
注意:
- 考虑与整体穿搭的协调
- 舒适度和实用性
- 给出具体的款式和颜色建议"""
}


class OutfitSubAgent:
    """穿搭子Agent (通过 AHP 协议通信)"""
    
    def __init__(self, agent_id: str, category: str, llm: LocalLLM):
        self.agent_id = agent_id
        self.category = category
        self.llm = llm
        self.system_prompt = CATEGORY_PROMPTS.get(category, "你是一位穿搭顾问")
        self.mq = get_message_queue()
        self.receiver = AHPReceiver(agent_id, self.mq)
        self.sender = AHPSender(self.mq)
        self._running = False
    
    def start(self):
        """启动 Agent (监听消息队列)"""
        self._running = True
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()
        print(f"   🟢 {self.agent_id} 已启动 (监听中...)")
    
    def stop(self):
        """停止 Agent"""
        self._running = False
    
    def _run_loop(self):
        """主循环 - 监听消息"""
        while self._running:
            msg = self.receiver.wait_for_task(timeout=5)
            if msg:
                print(f"\n   📬 [{self.agent_id}] 收到任务: {msg.payload.get('category')}")
                self._handle_task(msg)
    
    def _handle_task(self, msg):
        """处理任务"""
        task_id = msg.task_id
        session_id = msg.session_id
        payload = msg.payload
        
        try:
            # 1. 发送进度
            self.sender.send_progress("leader", task_id, session_id, 0.1, "开始处理")
            
            # 2. 执行推荐
            user_info = payload.get("user_info", {})
            profile = UserProfile(
                name=user_info.get("name", "用户"),
                gender=user_info.get("gender", "male"),
                age=user_info.get("age", 25),
                occupation=user_info.get("occupation", ""),
                hobbies=user_info.get("hobbies", []),
                mood=user_info.get("mood", "normal"),
                season=user_info.get("season", "spring"),
                occasion=user_info.get("occasion", "daily")
            )
            
            self.sender.send_progress("leader", task_id, session_id, 0.5, "正在推荐...")
            result = self._recommend(profile)
            
            self.sender.send_progress("leader", task_id, session_id, 0.9, "完成")
            
            # 3. 返回结果
            self.sender.send_result("leader", task_id, session_id, {
                "category": self.category,
                "items": result.items,
                "colors": result.colors,
                "styles": result.styles,
                "reasons": result.reasons,
                "price_range": result.price_range
            }, status="success")
            
            print(f"   ✅ [{self.agent_id}] 任务完成")
            
        except Exception as e:
            self.sender.send_result("leader", task_id, session_id, 
                {"error": str(e)}, status="failed")
            print(f"   ❌ [{self.agent_id}] 任务失败: {e}")
    
    def _recommend(self, user_profile: UserProfile) -> OutfitRecommendation:
        """执行推荐"""
        
        prompt = self._build_prompt(user_profile)
        response = self.llm.invoke(prompt, self.system_prompt)
        
        return self._parse_response(response)
    
    def _build_prompt(self, user_profile: UserProfile) -> str:
        """构建提示词"""
        
        category_names = {
            "head": "帽子和饰品(帽子、眼镜、项链、耳饰等)",
            "top": "上衣(T恤、衬衫、外套、卫衣等)",
            "bottom": "裤子(牛仔裤、休闲裤、西裤等)",
            "shoes": "鞋子(运动鞋、皮鞋、休闲鞋等)"
        }
        
        mood_adjustments = {
            "depressed": "用户今天心情比较压抑，建议选择能带来活力或安慰感的款式，可以适当加入一些亮色点缀",
            "happy": "用户今天心情愉悦，可以选择更加鲜艳活泼的风格",
            "excited": "用户比较兴奋，建议选择大方得体的款式",
            "normal": "用户心情一般，选择舒适自然的风格即可"
        }
        
        prompt = f"""用户信息:
{user_profile.to_prompt_context()}

请为用户推荐{category_names.get(self.category, self.category)}。

{mood_adjustments.get(user_profile.mood, "")}

要求:
1. 根据用户的年龄({user_profile.age}岁)和职业({user_profile.occupation})选择合适的款式
2. 考虑季节({user_profile.season})和场合({user_profile.occasion})
3. 预算: {user_profile.budget}
4. 如果用户有爱好: {', '.join(user_profile.hobbies)}，考虑这些爱好对穿搭的影响

请返回JSON格式:
{{
    "category": "{self.category}",
    "items": ["具体推荐单品1", "具体推荐单品2"],
    "colors": ["颜色1", "颜色2"],
    "styles": ["风格1", "风格2"],
    "reasons": ["推荐理由1", "推荐理由2"],
    "price_range": "价格区间"
}}

只返回JSON。
"""
        return prompt
    
    def _parse_response(self, response: str) -> OutfitRecommendation:
        """解析响应"""
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                return OutfitRecommendation(
                    category=data.get("category", self.category),
                    items=data.get("items", []),
                    colors=data.get("colors", []),
                    styles=data.get("styles", []),
                    reasons=data.get("reasons", []),
                    price_range=data.get("price_range", "")
                )
        except Exception as e:
            print(f"Parse error: {e}")
        
        return OutfitRecommendation(
            category=self.category,
            items=["待推荐"],
            colors=["待定"],
            reasons=["等待处理"]
        )


class OutfitAgentFactory:
    """穿搭Agent工厂 (使用 AHP 协议)"""
    
    @staticmethod
    def create_agents(llm: LocalLLM) -> Dict[str, OutfitSubAgent]:
        """创建所有穿搭Agent"""
        return {
            "agent_head": OutfitSubAgent("agent_head", "head", llm),
            "agent_top": OutfitSubAgent("agent_top", "top", llm),
            "agent_bottom": OutfitSubAgent("agent_bottom", "bottom", llm),
            "agent_shoes": OutfitSubAgent("agent_shoes", "shoes", llm)
        }