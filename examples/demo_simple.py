#!/usr/bin/env python3
"""
Simple Outfit Recommendation Demo
Interactive terminal -> LLM -> Outfit Recommendation
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.utils.llm import LocalLLM


def parse_user_input(user_input: str) -> dict:
    """Parse user input into profile dict"""
    parts = [p.strip() for p in user_input.split(",")]
    
    profile = {
        "name": "用户",
        "gender": "male",
        "age": 25,
        "occupation": "general",
        "hobbies": [],
        "mood": "normal",
        "season": "spring",
        "occasion": "daily",
        "budget": "medium"
    }
    
    if len(parts) >= 1 and parts[0]:
        profile["name"] = parts[0]
    
    if len(parts) >= 2 and parts[1]:
        profile["gender"] = "female" if "女" in parts[1] else "male"
    
    if len(parts) >= 3 and parts[2]:
        try:
            profile["age"] = int(parts[2])
        except:
            pass
    
    if len(parts) >= 4 and parts[3]:
        profile["occupation"] = parts[3]
    
    if len(parts) >= 5 and parts[4]:
        profile["hobbies"] = [parts[4]]
    
    if len(parts) >= 6 and parts[5]:
        mood = parts[5]
        if "开心" in mood or "高兴" in mood:
            profile["mood"] = "happy"
        elif "抑郁" in mood or "难过" in mood:
            profile["mood"] = "depressed"
        elif "激动" in mood:
            profile["mood"] = "excited"
        else:
            profile["mood"] = "normal"
    
    return profile


def get_recommendation(profile: dict, llm: LocalLLM, lang: str = "zh") -> dict:
    """Get outfit recommendation from LLM"""
    
    if lang == "zh":
        recommend_prompt = f"""根据以下用户信息，提供穿搭建议（请用中文回复）：

用户: {profile['name']}
性别: {profile['gender']}
年龄: {profile['age']}
职业: {profile['occupation']}
爱好: {', '.join(profile.get('hobbies', []))}
心情: {profile['mood']}
季节: {profile['season']}
场合: {profile['occasion']}
预算: {profile['budget']}

请为用户推荐完整穿搭方案。返回JSON格式：
{{
    "head": {{"items": ["物品1", "物品2"], "colors": ["颜色1"], "styles": ["风格1"], "reasons": ["理由"]}},
    "top": {{"items": ["物品1"], "colors": ["颜色1"], "styles": ["风格1"], "reasons": ["理由"]}},
    "bottom": {{"items": ["物品1"], "colors": ["颜色1"], "styles": ["风格1"], "reasons": ["理由"]}},
    "shoes": {{"items": ["物品1"], "colors": ["颜色1"], "styles": ["风格1"], "reasons": ["理由"]}},
    "overall_style": "整体风格描述",
    "summary": "总结"
}}

只返回有效JSON，不要其他内容。"""
    else:
        recommend_prompt = f"""Based on the following user profile, provide outfit recommendations:

User: {profile['name']}
Gender: {profile['gender']}
Age: {profile['age']}
Occupation: {profile['occupation']}
Hobbies: {', '.join(profile.get('hobbies', []))}
Mood: {profile['mood']}
Season: {profile['season']}
Occasion: {profile['occasion']}
Budget: {profile['budget']}

Please recommend complete outfit for this person. Return JSON format:
{{
    "head": {{"items": ["item1", "item2"], "colors": ["color1"], "styles": ["style1"], "reasons": ["reason"]}},
    "top": {{"items": ["item1"], "colors": ["color1"], "styles": ["style1"], "reasons": ["reason"]}},
    "bottom": {{"items": ["item1"], "colors": ["color1"], "styles": ["style1"], "reasons": ["reason"]}},
    "shoes": {{"items": ["item1"], "colors": ["color1"], "styles": ["style1"], "reasons": ["reason"]}},
    "overall_style": "description",
    "summary": "summary"
}}

Only return valid JSON."""

    response = llm.invoke(recommend_prompt)
    
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(response[start:end])
    except:
        pass
    
    return {}


def display_result(profile: dict, result: dict, lang: str = "zh"):
    """Display recommendation result"""
    if lang == "zh":
        print("\n" + "=" * 50)
        print(f"👤 用户: {profile['name']} ({profile['age']}岁 {profile['occupation']})")
        print(f"📝 心情: {profile['mood']} | 场合: {profile['occasion']} | 预算: {profile['budget']}")
        print("=" * 50)
        
        categories = {
            "head": "🎩 头部配饰",
            "top": "👕 上装",
            "bottom": "👖 下装", 
            "shoes": "👟 鞋子"
        }
        
        for cat, title in categories.items():
            if cat in result:
                item = result[cat]
                print(f"\n{title}")
                print(f"  推荐: {', '.join(item.get('items', []))}")
                print(f"  颜色: {', '.join(item.get('colors', []))}")
                print(f"  风格: {', '.join(item.get('styles', []))}")
                print(f"  理由: {', '.join(item.get('reasons', []))}")
        
        if "overall_style" in result:
            print(f"\n🎯 整体风格: {result['overall_style']}")
        
        if "summary" in result:
            print(f"\n📝 总结: {result['summary']}")
    else:
        print("\n" + "=" * 50)
        print(f"👤 User: {profile['name']} ({profile['age']} {profile['occupation']})")
        print(f"📝 Mood: {profile['mood']} | Occasion: {profile['occasion']} | Budget: {profile['budget']}")
        print("=" * 50)
        
        categories = {
            "head": "🎩 Head",
            "top": "👕 Top", 
            "bottom": "👖 Bottom",
            "shoes": "👟 Shoes"
        }
        
        for cat, title in categories.items():
            if cat in result:
                item = result[cat]
                print(f"\n{title}")
                print(f"  Items: {', '.join(item.get('items', []))}")
                print(f"  Colors: {', '.join(item.get('colors', []))}")
                print(f"  Styles: {', '.join(item.get('styles', []))}")
                print(f"  Reasons: {', '.join(item.get('reasons', []))}")
        
        if "overall_style" in result:
            print(f"\n🎯 Overall Style: {result['overall_style']}")
        
        if "summary" in result:
            print(f"\n📝 Summary: {result['summary']}")
    
    print("=" * 50)


def main():
    """Main function"""
    print("\n" + "=" * 50)
    print("🧥 穿搭推荐系统")
    print("=" * 50)
    
    # Check LLM
    llm = LocalLLM()
    if not llm.available:
        print("❌ LLM 不可用，请确保 Ollama 已启动")
        return
    
    print(f"✅ LLM 已连接: {llm.model_name}")
    
    # Parse command line args
    import argparse
    parser = argparse.ArgumentParser(description="穿搭推荐系统")
    parser.add_argument("-l", "--lang", choices=["zh", "en"], default="zh", help="输出语言")
    parser.add_argument("-i", "--input", type=str, help="用户信息")
    args = parser.parse_args()
    
    lang = args.lang
    
    # User input
    if args.input:
        user_input = args.input
    else:
        print("\n" + "-" * 50)
        print("请输入用户信息 (格式: 姓名, 性别, 年龄, 职业, 爱好, 心情)")
        print("示例: 小红, 女, 28, 设计师, 阅读, 开心")
        print("-" * 50)
        
        user_input = input("\n> ").strip()
    
    if not user_input:
        print("❌ 输入不能为空")
        return
    
    # Parse
    print("\n🔄 解析用户信息...")
    profile = parse_user_input(user_input)
    
    if lang == "zh":
        gender_str = "女" if profile["gender"] == "female" else "男"
        print(f"✅ 已解析: {profile['name']}, {gender_str}, {profile['age']}岁, {profile['occupation']}")
    else:
        print(f"✅ Parsed: {profile['name']}, {profile['gender']}, {profile['age']}, {profile['occupation']}")
    
    # Get recommendation
    print("\n🔄 生成穿搭推荐...")
    result = get_recommendation(profile, llm, lang)
    
    # Display
    display_result(profile, result, lang)
    
    print("\n✅ 完成!")


if __name__ == "__main__":
    main()