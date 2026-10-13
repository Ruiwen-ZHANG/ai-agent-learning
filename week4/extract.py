from cost_tracker import CostTracker
import os                           # 标准库，用来读取环境变量
import httpx
import json
import sys
from dotenv import load_dotenv      # 第三方库，负责把 .env 的内容加载进环境变量

resume_text = """
李明远
男 | 1998年生 | 上海

教育背景
2016.09-2020.06  华东师范大学  计算机科学与技术  本科
2020.09-2023.06  同济大学  软件工程  硕士

工作经历
2023.07-至今  某电商科技公司  后端开发工程师
负责订单系统的微服务改造，使用 Python 和 Go 重构了三个核心模块，
将平均响应时间从 320ms 降低到 95ms。主导了消息队列选型，
最终采用 Kafka 替换原有的 RabbitMQ 方案。

技能
Python、Go、MySQL、Redis、Kafka、Docker、Kubernetes
英语六级，可阅读英文技术文档

其他
2022年获得全国研究生数学建模竞赛二等奖
"""

load_dotenv()                       # 执行加载，这一行必须在 getenv 之前
key = os.getenv("DEEPSEEK_API_KEY") # 按名字取值，取不到返回 None

if not key:
    raise ValueError("未找到 DEEPSEEK_API_KEY，请检查项目根目录下的 .env 文件")

headers = {
    "Content-Type": "application/json",
    "Authorization":f"Bearer {key}"
}

url = "https://api.deepseek.com/v1/chat/completions"

payload = {
    "model":"deepseek-flash",
    "messages":[{"role":"system","content":"""你是一个简历信息抽取助手。从用户提供的简历文本中抽取信息，以 json 格式输出，结构如下：

{
  "name": "姓名",
  "education": "最高学历",
  "skills": ["技能1", "技能2"],
  "years_of_experience": 工作年限数字
}
规则：
- education 填最高学历，格式为"学位 专业"
- skills 只包含技术技能，不包含语言能力、证书、获奖经历
- 任何字段在简历中找不到对应信息时，填 null，严禁编造或推测
当前日期：2026-10-13
years_of_experience 根据工作经历起止时间计算，'至今'按当前日期算，取整数年"""
                 },
                {"role":"user","content":resume_text}],
    "temperature":0,
    "max_tokens":500,
    "thinking": {"type": "disabled"},
    "response_format": {"type": "json_object"}
}

tracker = CostTracker()     # 括号表示调用，这一步会执行 __init__

try:
    response = httpx.post(
         url,           # 第一个参数是地址
         headers=headers,    # 请求头字典
         json=payload,       # 请求体，用 json= 参数
         timeout=30,
    )
except httpx.TimeoutException as e:
    print("超时了:",e)
    sys.exit(1)
except httpx.RequestError as e:
    print("网络错误：",e)
    sys.exit(1)

if response.status_code != 200:
    print(response.status_code)   # 先看状态码
    print(response.text)
    sys.exit(1)
#print(response.json())        # 再看完整响应

#print(json.dumps(response.json(), indent=2, ensure_ascii=False))

data = response.json()      # 先把响应体转成 Python 字典

content = data["choices"][0]["message"]["content"]
print(content)

finish_reason = data["choices"][0]["finish_reason"]
print(finish_reason)

usage = data["usage"]    # 先拿到整个 usage 字典

tracker.record("deepseek-flash", usage)
tracker.report()
