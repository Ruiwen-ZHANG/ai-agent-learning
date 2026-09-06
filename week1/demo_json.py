from pathlib import Path
import json

data = {"姓名":"泽恺","年龄":20,"tools":["a","b","c","d"],"dict":{"func":"direction"}}

text = json.dumps(data, ensure_ascii=False, indent=4, sort_keys=True)
print(text)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

config_json = DATA_DIR / "config.json"
config_json.write_text(text, encoding="utf-8")

data = json.loads(config_json.read_text(encoding="utf-8"))
print(data)

def safe_load_json(path):
    if not path.exists():
        print(f"文件不存在: {path}")
        return {}
    try:
       with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
    except json.JSONDecodeError as e:
        print(f"JSON 格式错误 [{path.name}]: {e}")
        return {}


bad_json = DATA_DIR / "bad.json"
bad_json.write_text("{这不是json}", encoding="utf-8")

result = safe_load_json(DATA_DIR / "bad.json")
print("返回值:", result)
print("类型:", type(result))






