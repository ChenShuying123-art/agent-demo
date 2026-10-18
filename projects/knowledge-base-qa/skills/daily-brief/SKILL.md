---
name: daily-brief
description: 当用户想了解"今天该知道什么"时使用：日期 + 天气 + 知识库里的相关约定
tools: [get_datetime, get_weather, search_knowledge_base]
---

回答流程：
1. 先用 get_datetime 获取今天的日期与星期。
2. 如果用户提到城市（或明显在问天气），用 get_weather 查询。
3. 再用 search_knowledge_base 查与当天或用户问题相关的记录。

输出格式：
- 先用一句话总结；
- 再分「日期」「天气」「知识库」三小节；
- 知识库内容必须标注 [n]；资料不足时明确说明。
