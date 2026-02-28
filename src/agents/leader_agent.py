"""
Leader Agent - User Profile Parsing and Task Distribution (using AHP Protocol)
"""
import json
import uuid
from typing import Any, Dict, List
from ..core.models import (
    UserProfile, Gender, OutfitTask, OutfitRecommendation, OutfitResult, TaskStatus
)
from ..utils.llm import LocalLLM
from ..protocol import get_message_queue, AHPSender


SYSTEM_PROMPT = """You are a professional fashion consultant, skilled at recommending appropriate outfits based on user information and mood.

You need to:
1. Parse user information, extract key features
2. Adjust outfit style based on user's mood (depressed/happy/normal)
3. Consider user's occupation and hobbies for recommendations
4. Provide professional and thoughtful suggestions

Please reply in JSON format.
"""


class LeaderAgent:
    """Main Agent - User profile parsing and task distribution (via AHP Protocol)"""
    
    def __init__(self, llm: LocalLLM):
        self.llm = llm
        self.tasks: List[OutfitTask] = []
        self.mq = get_message_queue()
        self.sender = AHPSender(self.mq)
        self.session_id = ""
    
    def process(self, user_input: str) -> OutfitResult:
        """Process user input - full workflow"""
        print("\n" + "=" * 50)
        print("Leader Agent Processing")
        print("=" * 50)
        
        # 1. Parse user profile
        print("\n[1] Parsing user profile...")
        profile = self.parse_user_profile(user_input)
        self.session_id = str(uuid.uuid4())
        
        # 2. Create tasks
        print(f"\n[2] Creating outfit tasks (protocol: AHP)")
        tasks = self.create_tasks(profile)
        
        # 3. Dispatch tasks to Sub Agents via AHP
        print(f"\n[3] Dispatching tasks via AHP protocol...")
        self._dispatch_tasks_via_ahp(tasks, profile)
        
        # 4. Collect results
        print(f"\n[4] Waiting for Sub Agent results...")
        results = self._collect_results(tasks)
        
        # 5. Aggregate
        print(f"\n[5] Aggregating results...")
        final = self.aggregate_results(profile, results)
        
        return final
    
    def parse_user_profile(self, user_input: str) -> UserProfile:
        """Parse user input to user profile"""
        
        prompt = f"""Extract user profile information from the following input, return JSON format:

Input: {user_input}

Please return JSON in the following format:
{{
    "name": "name",
    "gender": "male/female/other",
    "age": age_number,
    "occupation": "occupation",
    "hobbies": ["hobby1", "hobby2"],
    "mood": "happy/normal/depressed/excited",
    "style_preference": "style preference (optional)",
    "budget": "low/medium/high",
    "season": "spring/summer/autumn/winter",
    "occasion": "daily/work/date/party"
}}

Only return JSON, no other content.
"""
        
        response = self.llm.invoke(prompt, SYSTEM_PROMPT)
        
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
                return UserProfile(
                    name=data.get("name", "User"),
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
        """Fallback parsing"""
        import re
        
        name = "User"
        gender = Gender.MALE
        age = 25
        occupation = ""
        hobbies = []
        mood = "normal"
        
        # Check for Chinese gender keywords
        if "男" in user_input:
            gender = Gender.MALE
        elif "女" in user_input:
            gender = Gender.FEMALE
        
        # Check for mood keywords
        if "压抑" in user_input:
            mood = "depressed"
        elif "开心" in user_input or "愉悦" in user_input:
            mood = "happy"
        
        # Extract age
        age_match = re.search(r'(\d+)岁', user_input)
        if age_match:
            age = int(age_match.group(1))
        
        # Extract occupation
        occupations = ["chef", "doctor", "teacher", "programmer", "designer", "student"]
        occ_map = {"厨师": "chef", "医生": "doctor", "教师": "teacher", 
                  "程序员": "programmer", "设计师": "designer", "学生": "student"}
        for cn, en in occ_map.items():
            if cn in user_input:
                occupation = en
                break
        
        # Extract hobbies
        hobby_words = ["旅游", "运动", "音乐", "阅读", "游戏", "美食"]
        hobby_map = {"旅游": "travel", "运动": "sports", "音乐": "music", 
                    "阅读": "reading", "游戏": "gaming", "美食": "food"}
        for cn, en in hobby_map.items():
            if cn in user_input:
                hobbies.append(en)
        
        return UserProfile(
            name=name, gender=gender, age=age, occupation=occupation,
            hobbies=hobbies, mood=mood, season="spring", occasion="daily"
        )
    
    def create_tasks(self, user_profile: UserProfile) -> List[OutfitTask]:
        """Create outfit tasks"""
        
        task_configs = [
            {"category": "head", "agent_id": "agent_head", "desc": "head accessories recommendation"},
            {"category": "top", "agent_id": "agent_top", "desc": "top clothing recommendation"},
            {"category": "bottom", "agent_id": "agent_bottom", "desc": "bottom clothing recommendation"},
            {"category": "shoes", "agent_id": "agent_shoes", "desc": "shoes recommendation"}
        ]
        
        tasks = []
        for config in task_configs:
            task = OutfitTask(
                category=config["category"],
                user_profile=user_profile
            )
            task.assignee_agent_id = config["agent_id"]
            tasks.append(task)
            print(f"   OK {config['category']} -> {config['agent_id']}")
        
        self.tasks = tasks
        return tasks
    
    def _dispatch_tasks_via_ahp(self, tasks: List[OutfitTask], profile: UserProfile):
        """Dispatch tasks via AHP protocol"""
        
        # Category description mapping
        category_desc = {
            "head": "head accessories",
            "top": "top clothing",
            "bottom": "bottom clothing",
            "shoes": "shoes"
        }
        
        for task in tasks:
            desc = category_desc.get(task.category, task.category)
            # Build compact instruction (Token control)
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
                "instruction": f"Please recommend {desc} for {profile.name}, considering their mood is {profile.mood}"
            }
            
            # Send via AHP protocol
            self.sender.send_task(
                target_agent=task.assignee_agent_id,
                task_id=task.task_id,
                session_id=self.session_id,
                payload=payload,
                token_limit=500
            )
    
    def _collect_results(self, tasks: List[OutfitTask], timeout: int = 60) -> Dict[str, OutfitRecommendation]:
        """Collect results from all agents"""
        
        import time
        results = {}
        start = time.time()
        received = set()
        
        while len(received) < len(tasks) and (time.time() - start) < timeout:
            # Leader monitors all results
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
                    print(f"   OK Received {category} result")
        
        return results
    
    def aggregate_results(
        self,
        user_profile: UserProfile,
        results: Dict[str, OutfitRecommendation]
    ) -> OutfitResult:
        """Aggregate results"""
        
        style_prompt = f"""Based on the following user profile and outfit recommendations, provide overall style suggestions:

User Profile:
{user_profile.to_prompt_context()}

Recommendations:
{json.dumps({k: {"items": v.items, "colors": v.colors, "styles": v.styles} for k, v in results.items()}, ensure_ascii=False)}

Please provide:
1. Overall style description
2. One sentence summary

Return JSON format:
{{
    "overall_style": "style description",
    "summary": "summary"
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
