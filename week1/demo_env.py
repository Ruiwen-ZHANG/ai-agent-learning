"""演示 .env 环境变量的加载、读取、类型转换与必填校验。"""

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR.parent / ".env"
# .parent 往上跳一层：week1/ → 项目根目录

if not ENV_FILE.exists():
    raise FileNotFoundError(
        f"未找到配置文件: {ENV_FILE}\n请复制 .env.example 为 .env 并填入配置"
    )

load_dotenv(ENV_FILE)
# 必须在所有 os.getenv 之前调用


def check_required_config() -> None:
    """校验必填项，一次性列出所有缺失的键。"""
    required = ["API_KEY", "MODEL_NAME"]
    missing = [key for key in required if not os.getenv(key)]
    # 列表推导式：遍历 required，把不存在的键收集起来

    if missing:
        raise ValueError(f"缺少必需的配置项: {missing}\n请检查: {ENV_FILE}")


check_required_config()


app_name = os.getenv("APP_NAME", "未命名Agent")
model_name = os.getenv("MODEL_NAME", "deepseek-chat")
api_key = os.getenv("API_KEY")

max_turns = int(os.getenv("MAX_TURNS", "10"))
# .env 是纯文本，读出来是字符串，必须转换
# 默认值写 "10" 而不是 10，getenv 第二个参数只接受字符串

temperature = float(os.getenv("TEMPERATURE", "0.7"))

debug = os.getenv("DEBUG", "false").lower() == "true"
# 不能写 bool(...)，因为 bool("False") 是 True

not_exist = os.getenv("NOT_EXIST_KEY")


print("=" * 50)
print(f"配置文件     : {ENV_FILE}")
print(f"APP_NAME     : {app_name}")
print(f"MODEL_NAME   : {model_name}")
print(f"MAX_TURNS    : {max_turns}  ({type(max_turns).__name__})")
print(f"TEMPERATURE  : {temperature}  ({type(temperature).__name__})")
print(f"DEBUG        : {debug}  ({type(debug).__name__})")
print(f"API_KEY      : {api_key[:10]}...")
# 永远不要完整打印密钥
print(f"不存在的键   : {not_exist}  ({type(not_exist).__name__})")
print("=" * 50)


raw = os.getenv("MAX_TURNS", "10")
print(f"原始值 {raw!r} 类型: {type(raw).__name__}")
print(f"字符串相加: {raw + raw}")
print(f"整数相加  : {max_turns + max_turns}")