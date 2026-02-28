"""
Leader Agent - 用户画像解析与任务分发 (使用 AHP 协议)
"""
import json
import uuid
from typing import Any, Dict, List
from ..core.models import (
    UserProfile, Gender, OutfitTask, OutfitRecommendation, OutfitResult, TaskStatus
)
from ..utils.llm import LocalLLM
from ..protocol import get_message_queue, AHPSender


SYSTEM_PROMPT = """你是一位专业的时尚穿搭顾问，擅长根据用户的个人信息和心情推荐合适的穿搭。

你需要:
1. 解析用户信息，提取关键特征
2. 根据用户的心情(压抑/愉悦/一般)调整穿搭风格
3. 考虑用户的职业和爱好来推荐
4. 给出专业、贴心的建议

请用JSON格式回复。
"""


class LeaderAgent:
    """主Agent - 用户画像解析与任务分发 (通过 AHP 协议)"""
    
    def __init__(self, llm: LocalLLM):
        self.llm = llm
        self.tasks: List[OutfitTask] = []
        self.mq = get_message_queue()
        self.sender = AHPSender(self.mq)
        self.session_id = ""
    
    def process(self, user_input: str) -> OutfitResult:
        """处理用户输入 - 完整流程"""
        print("\n" + "=" * 50)
        print("🔵 Leader Agent 开始处理")
        print("=" * 50)
        
        # 1. 解析用户画像
        print("\n[1] 解析用户画像...")
        profile = self.parse_user_profile(user_input)
        self.session_id = str(uuid.uuid4())
        
        # 2. 创建任务
        print(f"\n[2] 创建穿搭任务 (分发协议: AHP)")
        tasks = self.create_tasks(profile)
        
        # 3. 通过 AHP 协议分发任务给各个 Sub Agent
        print(f"\n[3] 通过 AHP 协议分发任务...")
        self._dispatch_tasks_via_ahp(tasks, profile)
        
        # 4. 收集结果
        print(f"\n[4] 等待 Sub Agent 结果...")
        results = self._collect_results(tasks)
        
        # 5. 汇总
        print(f"\n[5] 汇总结果...")
        final = self.aggregate_results(profile, results)
        
        return final
    
    def parse_user_profile(self, user_input: str) -> UserProfile:
        """解析用户输入为用户画像"""
        
        prompt = f"""请从以下用户输入中提取用户画像信息，返回JSON格式:

输入: {user_input}

请返回以下格式的JSON:
{{
    "name": "姓名",
    "gender": "male/female/other",
    "age": 年龄数字,
    "occupation": "职业",
    "hobbies": ["爱好1", "爱好2"],
    "mood": "happy/normal/depressed/excited",
    "style_preference": "风格偏好(可选)",
    "budget": "low/medium/high",
    "season": "spring/summer/autumn/winter",
    "occasion": "daily/work/date/party"
}}

只返回JSON，不要其他内容。
"""
        
        response = self.llm.invoke(prompt, SYSTEM_PROMPT)
        
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                return UserProfile(
                    name=data.get("name", "用户"),
                    gender=Gender(data.get("gender", "male")),
                    age=int(data.get("age", 25)),
                    occupation=data.get("occupation", ""),
                    hobbies=data.get("hobbies", []),
                    mood=data.get("mood", "normal"),
                    style_preference=data.get("style_preference", ""),
                    budget=data.get("budget", "medium"),
                    season=data.get("season", "spring"),
                    occasion=data.get("occasion", "daily")
                )
        except Exception as e:
            print(f"Parse error: {e}")
        
        return self._fallback_parse(user_input)
    
    def _fallback_parse(self, user_input: str) -> UserProfile:
        """降级解析"""
        import re
        
        name = "用户"
        gender = Gender.MALE
        age = 25
        occupation = ""
        hobbies = []
        mood = "normal"
        
        if "男" in user_input:
            gender = Gender.MALE
        elif "女" in user_input:
            gender = Gender.FEMALE
        
        if "压抑" in user_input:
            mood = "depressed"
        elif "开心" in user_input or "愉悦" in user_input:
            mood = "happy"
        
        age_match = re.search(r'(\d+)岁', user_input)
        if age_match:
            age = int(age_match.group(1))
        
        occupations = ["厨师", "医生", "教师", "程序员", "设计师", "学生"]
        for occ in occupations:
            if occ in user_input:
                occupation = occ
                break
        
        hobby_words = ["旅游", "运动", "音乐", "阅读", "游戏", "美食"]
        for h in hobby_words:
            if h in user_input:
                hobbies.append(h)
        
        return UserProfile(
            name=name, gender=gender, age=age, occupation=occupation,
            hobbies=hobbies, mood=mood, season="spring", occasion="daily"
        )
    
    def create_tasks(self, user_profile: UserProfile) -> List[OutfitTask]:
        """创建穿搭任务"""
        
        task_configs = [
            {"category": "head", "agent_id": "agent_head", "desc": "帽子和饰品推荐"},
            {"category": "top", "agent_id": "agent_top", "desc": "上身穿搭推荐"},
            {"category": "bottom", "agent_id": "agent_bottom", "desc": "裤子推荐"},
            {"category": "shoes", "agent_id": "agent_shoes", "desc": "鞋子推荐"}
        ]
        
        tasks = []
        for config in task_configs:
            task = OutfitTask(
                category=config["category"],
                user_profile=user_profile
            )
            task.assignee_agent_id = config["agent_id"]
            tasks.append(task)
            print(f"   ✓ {config['category']} → {config['agent_id']}")
        
        self.tasks = tasks
        return tasks
    
    def _dispatch_tasks_via_ahp(self, tasks: List[OutfitTask], profile: UserProfile):
        """通过 AHP 协议分发任务"""
        
        # 类别描述映射
        category_desc = {
            "head": "帽子和饰品",
            "top": "上身穿搭",
            "bottom": "裤子",
            "shoes": "鞋子"
        }
        
        for task in tasks:
            desc = category_desc.get(task.category, task.category)
            # 构建精简指令 (Token 控制)
            payload = {
                "category": task.category,
                "description": desc,
                "user_info": {
                    "name": profile.name,
                    "gender": profile.gender.value,
                    "age": profile.age,
                    "occupation": profile.occupation,
                    "mood": profile.mood,
                    "hobbies": profile.hobbies,
                    "season": profile.season,
                    "budget": profile.budget
                },
                "instruction": f"请为{profile.name}推荐{desc}，考虑他今天心情{profile.mood}"
            }
            
            # 通过 AHP 协议发送
            self.sender.send_task(
                target_agent=task.assignee_agent_id,
                task_id=task.task_id,
                session_id=self.session_id,
                payload=payload,
                token_limit=500
            )
    
    def _collect_results(self, tasks: List[OutfitTask], timeout: int = 60) -> Dict[str, OutfitRecommendation]:
        """收集各 Agent 的结果"""
        
        import time
        results = {}
        start = time.time()
        received = set()
        
        while len(received) < len(tasks) and (time.time() - start) < timeout:
            # Leader 监听所有结果
            for agent_id in [t.assignee_agent_id for t in tasks if t.assignee_agent_id not in received]:
                msg = self.mq.receive("leader", timeout=2)
                if msg and msg.method == "RESULT":
                    result_data = msg.payload.get("result", {})
                    category = result_data.get("category", "unknown")
                    results[category] = OutfitRecommendation(
                        category=category,
                        items=result_data.get("items", []),
                        colors=result_data.get("colors", []),
                        styles=result_data.get("styles", []),
                        reasons=result_data.get("reasons", []),
                        price_range=result_data.get("price_range", "")
                    )
                    received.add(agent_id)
                    print(f"   ✓ 收到 {category} 结果")
        
        return results
    
    def aggregate_results(
        self,
        user_profile: UserProfile,
        results: Dict[str, OutfitRecommendation]
    ) -> OutfitResult:
        """汇总结果"""
        
        style_prompt = f"""根据以下用户画像和穿搭推荐，给出整体风格建议:

用户画像:
{user_profile.to_prompt_context()}

各部分推荐:
{json.dumps({k: {"items": v.items, "colors": v.colors, "styles": v.styles} for k, v in results.items()}, ensure_ascii=False)}

请给出:
1. 整体风格描述
2. 一句话总结

返回JSON格式:
{{
    "overall_style": "风格描述",
    "summary": "总结"
}}
"""
        
        response = self.llm.invoke(style_prompt, SYSTEM_PROMPT)
        
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                return OutfitResult(
                    session_id=self.session_id,
                    user_profile=user_profile,
                    head=results.get("head"),
                    top=results.get("top"),
                    bottom=results.get("bottom"),
                    shoes=results.get("shoes"),
                    overall_style=data.get("overall_style", ""),
                    summary=data.get("summary", "")
                )
        except:
            pass
        
        return OutfitResult(
            session_id=self.session_id,
            user_profile=user_profile,
            head=results.get("head"),
            top=results.get("top"),
            bottom=results.get("bottom"),
            shoes=results.get("shoes")
        )