# 第 6 周技术总结：RAG 基础链路

> 16 周 AI Agent 应用开发学习记录 · 第 6 周
> 关键词：RAG、Embedding、bge-small-zh、余弦相似度、切块、Chroma、向量检索、出处标注、混合检索

---

## 本周概览

前五周，模型只能用**它自己训练时学到的知识**回答问题。第 5 周用 Function Calling 让它能查天气、做计算，但它仍然没读过**你自己的资料**。

这一周让模型读你的笔记来回答问题：

```
你：第 5 周那个 422 错误是怎么回事？
程序：在 591 块笔记里找出最相关的几块           ← 检索（Retrieval）
程序：把这几块和问题一起交给 DeepSeek           ← 增强（Augmented）
模型：422 是……[4][5]                            ← 生成（Generation），并标注出处
程序：[4] week3-fastapi-docker.md > 2.1 ……      ← 程序根据编号打印准确出处
```

| 小节 | 内容 | 产出文件 |
|---|---|---|
| 0 | 前置：CostTracker 搬家 + 区分缓存命中计价 | `common/cost_tracker.py` |
| 1 | RAG 全景 | 无代码 |
| 2 | Embedding：本地跑 bge 模型 | `week6/embed_demo.py` |
| 3 | 切块（Chunking） | `week6/chunker.py` |
| 4 | 向量数据库 Chroma | `week6/build_index.py`、`week6/search.py` |
| 5 | 完整 RAG：检索 + 生成 + 出处 + 混合检索 | `week6/rag.py`（并修改 `search.py`） |

**本周最有分量的产出**：一套完整跑通的 RAG 系统，用自己第 1~5 周的笔记做语料。它能找到没有共同字眼的相关段落，能给每句话标注出处，资料里没有的内容会老实说"没有"，并且用关键词检索补上了语义检索找不到的"422"。

**代码仓库**：`https://github.com/Ruiwen-ZHANG/ai-agent-learning`

### 本周 4 个文件的关系

```
           ┌─────────── 离线阶段（建库，提前做，只做一次）──────────┐
 5 份 md 笔记 ──▶ chunker.py ──▶ 591 个块 ──▶ build_index.py ──▶ chroma_db 文件夹
                  （切块）                   （算向量 + 存库）
           └──────────────────────────────────────────────────────┘

           ┌─────────── 在线阶段（每次提问时现场做）──────────────┐
 你的问题 ──▶ search.py ──▶ 最相关的几块 ──▶ rag.py ──▶ 带 [编号] 的回答 + 出处
           └──────────────────────────────────────────────────────┘

 embed_demo.py：原理小实验，6 句话，不依赖其他文件
```

---

## 第一章 RAG 全景

### 1.1 为什么需要 RAG

大模型自己回答问题有三个限制：

| 问题 | 例子 |
|---|---|
| 知识有截止日期 | 训练之后发生的事它不知道 |
| 没见过你的私有数据 | 你的笔记、教材、公司文档它都没读过 |
| 不知道时会编 | 第 4 周讲过的幻觉 |

把整份文档塞进 prompt 行不通：文档放不进上下文窗口；每次都按全部 token 收费；上下文太长时，模型容易忽略中间部分。

**RAG（Retrieval-Augmented Generation，检索增强生成）**：先从文档里**检索**出和问题最相关的几小段，只把它们放进 prompt，让模型基于它们**生成**回答。

### 1.2 两个阶段

```
【离线：建索引】提前做，文档更新时重做
  文档 → 加载 → 切块 → 每块算 embedding → 存进向量数据库

【在线：每次提问】
  问题 → 算 embedding → 找最相似的 top-k 块 → 拼进 prompt → LLM 生成回答 + 出处
```

**"离线"和"在线"在 RAG 里和联不联网没有关系**，区分标准是"是不是在用户提问的时候做"：

| 说法 | 意思 |
|---|---|
| `HF_HUB_OFFLINE`（离线模式） | 不联网，模型只读本地缓存 |
| RAG 的**离线阶段** | 提前准备好：用户还没提问就做完的工作 |
| RAG 的**在线阶段** | 现场做：用户提问后实时进行，用户在等，所以要快 |

> **餐厅的比方**：离线阶段是早上备菜（洗、切、腌），花多久都行，做一次用一整天；在线阶段是客人点菜后现炒，客人在等。能提前做的就提前做掉，在线阶段才能快。build_index 提前算好 591 个向量，search 只需算 1 个问题的向量。

### 1.3 和前几周的关系

- **第 4 周的 embedding 与余弦相似度**：检索的核心。问题和文档块都变成向量，余弦相似度越高，语义越接近
- **第 5 周的 Function Calling**：以后可以把检索做成一个工具，由模型决定何时查、查什么（Agentic RAG）。本周先做固定流程
- **CostTracker**：RAG 会显著增加 prompt_tokens，正好用它观察成本

### 1.4 RAG 和微调

| | RAG | 微调 |
|---|---|---|
| 补的是什么 | **知识**：模型能查到的内容 | **行为**：风格、格式、习惯 |
| 能否给出处 | 能 | 不能 |
| 文档更新 | 重建索引即可 | 要重新训练 |

实际顺序：**先试 prompt 工程，不够再加 RAG，最后才考虑微调**。"每个回答都用固定的三段式格式"连微调都不需要，system prompt 加一个 few-shot 示例就够了。

### 1.5 RAG 会在哪里出错

| 环节 | 失败表现 | 根源 |
|---|---|---|
| 检索 | 相关段落没被找到 | 切块切断语义；embedding 分不清相近的编号 |
| 检索 | 找回一堆不相关的段落 | top-k 太大；块太大导致主题混杂 |
| 生成 | 找到了正确段落，模型却没用 | prompt 没要求只根据资料回答 |
| 生成 | 资料里没有答案，模型照样编 | 没告诉它"没有就说不知道" |

**排查顺序：RAG 答错了，先看检索回来的是什么，再看 prompt。** 本周第六章的 422 实验完整演示了这个顺序。

### 1.6 检验题要点

1. 笔记只有 5 万 token 也要做 RAG：节省 token、模型读不全长文、可以给出处；而且以后会翻三倍，项目一语料几千页，RAG 的成本基本不受总量影响
2. **建库和查询必须用同一个 embedding 模型**：不同模型的向量不在同一个空间里，维度都可能不同，算出的余弦值没有意义。推论：换模型就必须重建整个索引
3. "422 资料中未提及"但笔记里明明有：**先检查检索结果**
4. 课程问答并标注讲义出处 → RAG；固定回答格式 → prompt 就够

---

## 第二章 前置：CostTracker 升级

### 2.1 搬家到 common/

CostTracker 第三次被用到（第 4 周、第 5 周、第 6 周），从 `week4/` 移到 `common/`。用 PyCharm 的 Refactor → Move（F6），新建 `common/__init__.py`，导入方式变为：

```python
from common.cost_tracker import CostTracker
```

### 2.2 区分缓存命中计价

DeepSeek 的 usage 里有 `prompt_cache_hit_tokens`，命中缓存的输入比未命中便宜 50 倍（低谷价 $0.003/M 对 $0.15/M）。旧版 CostTracker 把所有输入都按未命中计价，会多算。

```python
class CostTracker:
    """统计多次 API 调用的 token 消耗与累计花费（区分缓存命中）"""

    def __init__(self):
        # 每 token 的价格，按 deepseek-flash 低谷价；高峰期（工作日北京时间 9-12、14-18 点）翻倍
        self.price = {
            "prompt_hit": 0.003 / 1000000,     # 输入，缓存命中
            "prompt_miss": 0.15 / 1000000,     # 输入，缓存未命中
            "completion": 0.60 / 1000000,      # 输出
        }
        self.calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cache_hit_tokens = 0
        # 未命中数不单独存：未命中 = 总输入 - 命中，现算，少一个对不上的可能

    def record(self, model, usage):
        """记录一次调用，usage 直接传响应里的那个字典"""
        self.calls += 1
        self.total_prompt_tokens += usage["prompt_tokens"]
        self.total_completion_tokens += usage["completion_tokens"]
        # DeepSeek 特有字段，换别家 API 可能没有，取不到按 0 算
        self.total_cache_hit_tokens += usage.get("prompt_cache_hit_tokens", 0)

    def cost(self):
        """返回累计花费（美元）"""
        miss_tokens = self.total_prompt_tokens - self.total_cache_hit_tokens
        return (self.price["prompt_hit"] * self.total_cache_hit_tokens
                + self.price["prompt_miss"] * miss_tokens
                + self.price["completion"] * self.total_completion_tokens)

    def report(self):
        """打印统计报告"""
        print("总调用次数：", self.calls)
        print("总输入token：", self.total_prompt_tokens)
        print("总输出token：", self.total_completion_tokens)
        print("缓存命中token：", self.total_cache_hit_tokens)
        if self.total_prompt_tokens > 0:       # 先判断再除，避免 ZeroDivisionError
            print(f"缓存命中率：{self.total_cache_hit_tokens / self.total_prompt_tokens:.1%}")
        print(f"总花费：${self.cost():.6f}")
```

### 2.3 验证结果

用第 5 周两次请求的真实 usage 验证（不调 API）：

```
总调用次数： 2
总输入token： 646
总输出token： 46
缓存命中token： 256
缓存命中率：39.6%
总花费：$0.000087
```

再运行 `week5/agent_loop.py`，确认搬家后 import 正常：

```
总调用次数： 6
总输入token： 3290
总输出token： 309
缓存命中token： 2048
缓存命中率：62.2%
总花费：$0.000378
```

| | 旧公式（全按未命中） | 新公式 | 旧版多算 |
|---|---|---|---|
| 测试块（2 次调用） | $0.000124 | $0.000087 | 43% |
| agent_loop（6 次调用） | $0.000679 | $0.000378 | 80% |

agent_loop 的命中率比测试块高，因为每次请求开头都是同一段 system + tools 定义，这段固定前缀会被缓存。**第 4、5 周报出的花费都偏高。**

---

## 第三章 Embedding：本地跑 bge 模型

### 3.1 为什么在本地跑

DeepSeek 没有 embedding 接口。我们用北京智源开源的 **bge-small-zh-v1.5**：中文效果好、约 100MB、CPU 能跑、输出 512 维、免费不消耗 token。

### 3.2 安装

在 PyCharm 终端（`Alt + F12`）确认提示符开头有 `(.venv)`，并且 `python -c "import sys; print(sys.executable)"` 输出的是项目里的 `.venv\Scripts\python.exe`，然后：

```powershell
python -m pip install sentence-transformers -i https://pypi.tuna.tsinghua.edu.cn/simple
```

装上了 sentence-transformers 6.2.0、torch 2.14.1 等依赖。在 `requirements.txt` 末尾加上 `sentence-transformers==6.2.0`，和其他行一样带版本号。

| 常见问题 | 解决 |
|---|---|
| PowerShell 禁止运行激活脚本 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `'pip' 不是内部或外部命令` | 用 `python -m pip` |
| 下载 torch 时超时 | 命令末尾加 `--default-timeout=200` 重试 |
| 不要用 `pip freeze > requirements.txt` | 会写进几十个间接依赖并覆盖原内容 |

### 3.3 模型下载与警告

```python
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"   # 国内镜像，必须写在 import sentence_transformers 之前
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"    # 关掉 Windows 符号链接警告
os.environ["HF_HUB_OFFLINE"] = "1"                     # 模型下载过之后才加：只读本地缓存，不再联网检查
```

`sentence_transformers` 在被 import 的那一刻就读取 `HF_ENDPOINT`，所以顺序不能反。

运行时出现的红字都是**警告，不是报错**。PyCharm 把写到 stderr 的输出都显示成红色。真正的报错以 `Traceback` 开头，程序会中断。

| 红字 | 意思 | 处理 |
|---|---|---|
| `unauthenticated requests to the HF Hub` | 没登录 HuggingFace，下载被限速 | 模型已缓存，不用管 |
| `cache-system uses symlinks` | Windows 没开开发者模式，缓存只能复制文件 | 多占一点磁盘，不影响功能 |
| `Could not reach the Hub ... Using cached` | 网络抽风，改用本地缓存 | 不影响；加 `HF_HUB_OFFLINE` 后不再出现 |

### 3.4 向量矩阵是什么样子

`model.encode(句子列表, normalize_embeddings=True)` 返回 numpy 二维数组，**每一行是一句话的向量**：

- 6 句话 → `(6, 512)`；1 个问题包成 `[query]` → `(1, 512)`
- 每个数都很小（大多在 ±0.1 以内）：归一化后每行 512 个数的平方和等于 1
- 单独看某一个数没有含义，意思由 512 个数**一起**表达

**缩小成 3 句话 × 4 维的手算例子**：

```python
doc_vecs = [[0.5,  0.5,  0.5,  0.5],     # 句子 A，平方和 = 1
            [0.5, -0.5,  0.5, -0.5],     # 句子 B
            [0.0,  0.6,  0.8,  0.0]]     # 句子 C
query_vec = [[0.6, 0.8, 0.0, 0.0]]       # 问题，平方和 0.36 + 0.64 = 1

# doc_vecs.T 形状 (4, 3)：每一列是一句话
# query_vec @ doc_vecs.T：问题和每一列对应相乘再相加（点积）
#   A：0.6×0.5 + 0.8×0.5    = 0.70
#   B：0.6×0.5 + 0.8×(-0.5) = -0.10
#   C：0.6×0.0 + 0.8×0.6    = 0.48
# 结果 [[0.70, -0.10, 0.48]]，形状 (1, 3)，取 [0] 得到 3 个分数
```

A 和问题方向一致（在第 1、2 维都是正数），分数最高；B 在第 2 维方向相反，分数被抵消成负数。**归一化后，点积就等于余弦相似度。**

### 3.5 embed_demo.py

```python
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"   # 国内镜像（必须在导入之前）
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-small-zh-v1.5")  # 加载模型，首次运行下载约 100MB
print("模型加载完成")

# 待检索的"文档库"：前 5 句来自第 4、5 周笔记，最后 1 句是无关干扰项
docs = [
    "工具执行完后，要用 role 为 tool 的消息把结果回填，并带上对应的 tool_call_id",
    "arguments 字段是 JSON 字符串，必须先用 json.loads 解析成字典",
    "messages 多套了一层方括号，接口返回 422 错误",
    "Docker 镜像构建时用 .dockerignore 排除 .env 文件",
    "temperature 设为 0 可以让输出尽量稳定，便于做对照实验",
    "今天食堂的麻辣香锅排队的人特别多",
]
query = "怎么把函数运行的结果交还给大模型？"

doc_vecs = model.encode(docs, normalize_embeddings=True)        # (6, 512)
query_vec = model.encode([query], normalize_embeddings=True)    # (1, 512)：包成列表保持二维
print(doc_vecs.shape)
print(query_vec.shape)

scores = (query_vec @ doc_vecs.T)[0]   # (1,512) @ (512,6) → (1,6)，取第 0 行得到 6 个分数
print(scores)

result = sorted(zip(scores, docs), reverse=True)   # 分数放前面，按分数从高到低排
for score, doc in result:
    print(f"{score:.4f} {doc}")
```

### 3.6 实验结果

**Q1：怎么把函数运行的结果交还给大模型？**

```
(6, 512)
(1, 512)
[0.5696694  0.45947635 0.47245082 0.3604724  0.5100527  0.1958217 ]
0.5697 工具执行完后，要用 role 为 tool 的消息把结果回填，并带上对应的 tool_call_id
0.5101 temperature 设为 0 可以让输出尽量稳定，便于做对照实验
0.4725 messages 多套了一层方括号，接口返回 422 错误
0.4595 arguments 字段是 JSON 字符串，必须先用 json.loads 解析成字典
0.3605 Docker 镜像构建时用 .dockerignore 排除 .env 文件
0.1958 今天食堂的麻辣香锅排队的人特别多
```

| query | 第 1 名 | 分数 | 与第 2 名差距 | 结论 |
|---|---|---|---|---|
| Q1 函数结果交还给大模型 | tool_call_id 回填 | 0.5697 | 0.060 | 没有共同字眼，也能靠语义命中 |
| Q2 参数为什么不能直接当字典用 | json.loads | 0.5215 | **0.009** | 和"422 方括号"那句几乎打平 |
| Q3 422 | 422 错误 | 0.5556 | 0.171 | 6 句里只有一句含 422，小库里能命中 |

三条结论：

- **分数只看相对排名，不看绝对值**。正确答案也只有 0.57，不能用"大于 0.8 才算相关"这种直觉
- **top-1 不可靠，要取 top-k**。Q2 只差 0.009，换个问法就可能翻转
- 无关内容（食堂那句）始终垫底，**真正难的是同领域干扰项**

> **Q3 的说明**：我在讲解时说"422 这种数字 embedding 处理不好"，Q3 的结果和这个说法相反，当时纠正为"说过头了"。但到了第五章，在 591 块的真实笔记里，422 确实找错了：小库里只有一句含 422 时能命中，真实语料里有 400、404 等一堆相近的错误码时，embedding 就分不清了。**小样本实验的结论不一定能推广到真实数据。**

---

## 第四章 切块（Chunking）

### 4.1 为什么要切

**① 模型有输入上限，超出部分被悄悄丢掉。** bge-small-zh 最多读 512 个 token，超出部分**直接截断，不报错也不警告**。整篇笔记编码成一个向量，后半部分等于没被索引，永远检索不到。

**② 一个向量只能代表一个"平均意思"。** 一段讲了 tool_call_id、422、json.loads、消融实验四件事，压成一个向量就成了"大概在讲 Function Calling"，问任何具体问题它都不是最匹配的。

| 块太大 | 块太小 |
|---|---|
| 主题混杂，向量被稀释 | 缺上下文："改成 json.loads 就好了"，不知道改的是什么 |
| 塞进 prompt 后 token 很贵 | 一个知识点被拆散到好几块 |

经验值：中文 300~500 字一块，再根据检索效果调整。

### 4.2 三种切法

- **固定长度**：每 N 字切一刀。简单，但会从句子中间切开
- **重叠（overlap）**：相邻块共享 10%~20% 的内容。**overlap 必须不短于关键句**，否则关键句在两块里都不完整
- **按结构切**：按标题、段落等天然边界切。**Markdown 笔记最适合这种**

### 4.3 Markdown 的三个特殊问题

1. **代码块不能切断**。代码块就像课本里的"引号"：引号里说"下课"不算真下课，代码里的 `# 注释` 也不是标题
2. **每块加标题路径**。正文"原因是 messages 多套了一层方括号"加上 `第5周 > 6. 典型错误 > 6.1 422 错误`，检索效果好很多，这是成本最低的优化
3. **记录元数据**（来自哪个文件、哪个标题），否则第六章没法标注出处

一个块最终是这样的字典：

```python
{
    "text": "week5-function-calling.md > 第三章 … > 3.3 字典分发\n正文……",   # 拿去 encode、给 LLM 看
    "source": "week5-function-calling.md",                                  # 出处：文件
    "heading": "3.3 字典分发",                                               # 出处：小节
}
```

**代码块超长怎么办？** 让它独占一块，允许超长。**存下来的文本**和**拿去算向量的文本**是两回事：算 embedding 时超出部分被截断，但开头的标题路径、说明和代码前几十行足够让检索命中；命中后放进 prompt 的是完整文本。截断只影响"能不能找到"，不影响"找到后能看到什么"。

### 4.4 核心套路：扫描 → 遇到边界就打包 → 收尾

chunker 里最难的三个函数，骨架完全一样：

```python
当前 = []          # 草稿纸：正在积累的
结果 = []          # 卡片盒：已完成的

for 元素 in 序列:
    if 遇到边界:
        if 当前:                 # 草稿纸上有内容才收
            结果.append(当前)
        当前 = []                # 换新草稿纸
        continue
    当前.append(元素)            # 不是边界：继续写

if 当前:                         # 收尾：最后一批后面没有边界来触发，要手动收一次
    结果.append(当前)
```

> **流水线装苹果的比方**：苹果一个个过来，往箱子里放；遇到"该换箱"的信号就把满箱搬走、换空箱；下班时手上没装满的那箱**也要搬走**，否则最后那些苹果就丢了。

| 函数 | 元素 | 什么时候换箱 | 结果 |
|---|---|---|---|
| `chunk_markdown` | 行 | 遇到**标题** | 一节一节 |
| `split_paragraphs` | 行 | 遇到**空行** | 一段一段 |
| `pack` | 段落 | 再装就**超过字数上限** | 一张张卡片 |

前两个函数多一个"引号模式"开关 `in_code`：开关打开时（在代码块里），边界信号全部无效。

**以后写类似的代码，先想清楚"元素是什么、边界是什么"，再往骨架里填细节。**

### 4.5 chunker.py 完整代码（v2）

```python
from pathlib import Path

MAX_CHARS = 450   # 每块正文的字数上限；加上标题路径几十字，总长控制在 500 左右


def make_chunk(path, lines, source):
    """把一张卡片的行打包成块字典；空内容返回 None"""
    body = "\n".join(lines).strip()             # 行拼回文本，去掉首尾空白
    if body == "":
        return None
    return {
        "text": source + " > " + " > ".join(path) + "\n" + body,   # 文件名 + 标题路径 + 正文
        "source": source,
        "heading": path[-1] if path else "",    # path 为空时防止 path[-1] 报错
    }


def split_paragraphs(lines):
    """把一节的行按空行拆成段落；代码块内部的空行不拆"""
    in_code = False      # 引号模式开关
    para = []            # 当前段落
    paras = []           # 所有段落

    for line in lines:
        if line.lstrip().startswith("```"):     # 代码块边界（lstrip 兼容缩进的代码块）
            in_code = not in_code
            para.append(line)                   # 边界符属于代码块，保留
            continue
        if not in_code and line.strip() == "":  # 边界：代码块外的空行
            if para:                            # 连续空行时 para 是空的，不收
                paras.append(para)
            para = []
            continue                            # 空行本身不保留
        para.append(line)                       # 正文或代码块内部的任何行

    if para:                                    # 收尾
        paras.append(para)
    return paras


def pack(paras, max_chars):
    """把段落依次装进卡片，每张不超过 max_chars 字；单段超长就独占一张"""
    groups = []      # 结果：每张卡片的所有行
    group = []       # 当前卡片
    size = 0         # 当前卡片的字数

    for para in paras:
        para_size = len("\n".join(para))
        if group and size + para_size > max_chars:   # 卡片不空且再装就超 → 换卡片
            groups.append(group)
            group = []
            size = 0
        group.extend(para)          # 这段的行逐个放进卡片
        group.append("")            # 段与段之间补回空行，保持 Markdown 格式
        size += para_size

    if group:                       # 收尾
        groups.append(group)
    return groups


def chunk_markdown(text, source):
    """把一篇 md 文本切成块列表"""
    in_code = False      # 引号模式开关
    path = []            # 当前标题路径，如 ["第5周", "第三章", "3.3 字典分发"]
    buf = []             # 草稿纸：当前小节的行
    chunks = []          # 卡片盒：已打包的块

    for line in text.splitlines():
        # ① 代码块边界
        if line.lstrip().startswith("```"):
            in_code = not in_code
            buf.append(line)
            continue

        # ② 标题：不在代码块里，以 # 开头，且 # 后面紧跟空格
        stripped = line.lstrip("#")
        if not in_code and line.startswith("#") and stripped.startswith(" "):
            level = len(line) - len(stripped)   # 去掉了几个 #，就是几级标题
            title = stripped.strip()

            # 打包这一节：拆段落 → 装卡片 → 每张贴标签
            for group in pack(split_paragraphs(buf), MAX_CHARS):
                chunk = make_chunk(path, group, source)
                if chunk is not None:
                    chunks.append(chunk)
            buf = []                            # 换新草稿纸（在 for 外面）

            path = path[:level - 1] + [title]   # 保留比自己高的级别，再接上自己
            continue

        # 分隔线 --- 对检索没意义，跳过（表格的 |---|---| 不等于 ---，不会误删）
        if not in_code and line.strip() == "---":
            continue

        # ③ 普通正文，或代码块内部的行
        buf.append(line)

    # 收尾：最后一节后面没有标题来触发打包
    for group in pack(split_paragraphs(buf), MAX_CHARS):
        chunk = make_chunk(path, group, source)
        if chunk is not None:
            chunks.append(chunk)

    return chunks


def load_all_chunks(root):
    """读取 root 下所有 week*.md 笔记，切块后合并返回"""
    all_chunks = []
    for f in sorted(root.glob("week*.md")):
        text = f.read_text(encoding="utf-8")
        all_chunks.extend(chunk_markdown(text, f.name))   # extend：逐个倒进总列表
    return all_chunks


if __name__ == "__main__":
    root = Path(__file__).parent.parent        # chunker.py → week6/ → 项目根目录
    md_files = sorted(root.glob("week*.md"))

    print(f"找到 {len(md_files)} 个文件：")
    for f in md_files:
        print("  ", f.name)
    if not md_files:
        print("没有找到 md 文件，检查文件是否在项目根目录")
        raise SystemExit

    all_chunks = []
    for f in md_files:
        chunks = chunk_markdown(f.read_text(encoding="utf-8"), f.name)
        print(f"{f.name}: {len(chunks)} 块")
        all_chunks.extend(chunks)

    lengths = [len(c["text"]) for c in all_chunks]
    print("=" * 40)
    print(f"总块数：{len(all_chunks)}")
    print(f"最长：{max(lengths)} 字")
    print(f"最短：{min(lengths)} 字")
    print(f"平均：{sum(lengths) / len(lengths):.0f} 字")
    print(f"超过 500 字的块：{len([n for n in lengths if n > 500])} 个")

    # 排序的是字典，要用 key 告诉 sorted 按 text 的长度比
    top5 = sorted(all_chunks, key=lambda c: len(c["text"]), reverse=True)[:5]
    print("=" * 40)
    print("最长的 5 块：")
    for c in top5:
        print(f"  {len(c['text'])} 字 | {c['source']} | {c['heading']}")

    sample = all_chunks[min(10, len(all_chunks) - 1)]   # 防止越界
    print("=" * 40)
    print(f"样例（{sample['source']}）：")
    print(sample["text"])
    print("=" * 40)
```

### 4.6 跟着一段真实笔记跑一遍

取第 5 周笔记的 3.3、3.4 两节（30 行），为了演示拆卡片，**临时把 MAX_CHARS 改成 200**：

~~~
 1  # 第 5 周技术总结：Function Calling 与 Agent 循环
 2
 3  ## 第三章 并行调用与多轮工具循环
 4
 5
 6  ### 3.3 字典分发
 7
 8  ```python
 9  def greet(name):
10      return f"你好，{name}"
11
12  func_map = {"greet": greet}    # 存的是函数本身，不加括号
13  f = func_map["greet"]          # 按名字取出函数
14  print(f("小明"))               # 再调用：你好，小明
15  ```
16
17  Python 里函数也是对象，可以当字典的值存。……
18
19  > 这就是第 1 周写的 `ToolRegistry`。……
20
21  ### 3.4 `**` 解包
22
23  ```python
24  args = {"a": 18, "b": 12, "operation": "subtract"}
25  calculate(**args)
26  # 等价于 calculate(a=18, b=12, operation="subtract")
27  ```
28
29  `**` 只负责**把字典拆成关键字参数**……
30
~~~

**buf 的变化**（`''` 表示空行，◀ 表示新加入的行）：

```
第 1 行  # 第5周…      ② 标题  打包前 buf = []           → 不产生块；path → [第5周]
第 2 行  空行          ③       buf = ['']  ◀
第 3 行  ## 第三章      ② 标题  打包前 buf = ['']         → 只有空行，不产生块；path → [第5周, 第三章]
第 4、5 行 空行         ③       buf = ['', '']
第 6 行  ### 3.3       ② 标题  打包前 buf = ['', '']     → 不产生块；path → [第5周, 第三章, 3.3 字典分发]
第 7 行  空行          ③       buf = ['']  ◀
第 8 行  ```python     ①       in_code → True   buf = ['', '```python']  ◀
第 9 行  def greet…    ③       buf = ['', '```python', 'def greet(name):']  ◀
第 10 行 return…       ③       buf = [... , '    return f"你好，{name}"']  ◀
第 11 行 空行（代码里） ③       buf = [... , '']  ◀            ← 在代码块里，照样写上
第 12~14 行 func_map…  ③       buf 末尾依次追加这 3 行代码
第 15 行 ```           ①       in_code → False  buf = [... , '```']  ◀
第 16~20 行            ③       依次追加 ''、'Python 里函数也是对象…'、''、'> 这就是第 1 周写的…'、''
第 21 行 ### 3.4       ② 标题  打包 3.3 节的全部 14 行（见下）；清空 buf；path 最后一级换成 3.4
第 22~25 行            ③       buf = ['', '```python', 'args = {…}', 'calculate(**args)']
第 26 行 # 等价于…      ③ !!   buf 末尾追加 '# 等价于 calculate(…)'   ← 像标题，但 in_code 是 True，只是普通代码
第 27 行 ```           ①       in_code → False
第 28~30 行            ③       依次追加 ''、'`**` 只负责…'、''
循环结束               收尾    打包 3.4 节的 9 行
```

第 21 行打包 3.3 节时，三个函数依次处理：

| 步骤 | 输入 | 输出 |
|---|---|---|
| `split_paragraphs` | 14 行 | 3 段：代码块（183 字，**第 11 行的空行留在里面**）、"函数也是对象"（59 字）、引用（52 字）。第 7、16、18、20 行代码块外的空行用作分界，然后被丢掉 |
| `pack(…, 200)` | 3 段 | 183 装入卡片 1；183+59=242>200，换卡片；59+52=111 装入卡片 2 → **2 张卡片** |
| `make_chunk` | 2 张卡片 | 2 个块，开头都是 `week5.md > 第5周… > 第三章… > 3.3 字典分发` |

最终 30 行 → 4 块：3.3 代码、3.3 说明、3.4 代码（含第 26 行注释）、3.4 说明。用真实的 450，3.3 节 183+59+52=294 不超，会合成一块。

**这段演示说明了三件事**：前 3 个标题时 buf 里只有空行，不产生垃圾块；第 26 行就是 `in_code` 开关存在的意义，没有它，3.4 会在代码中间被切断，path 也会变成 `["等价于 calculate(…)"]`；忘了收尾，3.4 整节都会丢失。

### 4.7 v1 → v2 的统计对比

| 指标 | v1（只按标题切） | 过滤 `---` 后 | v2（段落拆分 + 装箱） |
|---|---|---|---|
| week1 / 2 / 3 / 4 / 5 块数 | 119 / 110 / 53 / 51 / 66 | 同左 | 174 / 134 / 77 / 86 / 120 |
| 总块数 | 399 | 399 | **591** |
| 最长 | 3754 | 3716 | **1990** |
| 最短 | 24 | 24 | 50 |
| 平均 | 505 | 504 | **383** |
| 超过 500 字 | 133 | 132 | 111 |

v1 最长的 5 块都是第 5 周的整节（根因一 3754、根因三 2683、3.9 call_llm 2256……）。v2 最长的 5 块：

```
1990 字 | week5-function-calling.md | 2.5 实验代码
1932 字 | week5-function-calling.md | 3.9 call_llm 与 run_agent
1423 字 | week3-fastapi-docker.md   | 附录 A：本周完整命令速查
1296 字 | week4-llm-api-prompt.md   | 2.6 CostTracker 实现
1154 字 | week5-function-calling.md | 4.7 最终的内层循环
```

**全是代码或命令清单**，正是"单个代码块超长就独占一块"的设计结果。剩下 111 个超过 500 字的块，一部分只是被标题路径（四五十字）撑过了 500，另一部分是单个超长的代码块或整张表格。

### 4.8 一个排查：为什么样例缺了文档标题

v1 样例的路径是 `二、类与对象 > 2.8 魔术方法`，缺了"第 1 周……"这一级。两种可能：

- **原因 A**：章节标题也用了 `#`。读到 `# 二、类与对象` 时 level=1，`path[:0]` 是空列表，文档标题被替换
- **原因 B**：文件开头有 BOM（`﻿`），第一行实际是 `'﻿# …'`，`startswith("#")` 判断失败。用 `print(repr(text.splitlines()[0]))` 检查，修复方法是 `encoding="utf-8-sig"`

`repr` 检查显示 5 个文件第一行都以 `'# ` 开头，没有 BOM，确认是原因 A。这不是程序 bug，程序严格按照笔记的标题层级处理。v2 在 text 开头加上 source，出处信息就完整了。

---

## 第五章 向量数据库 Chroma

### 5.1 为什么需要向量数据库

591 块 × 512 维，numpy 一次矩阵乘法不到 1 毫秒就算完。用数据库是为了：

| 问题 | numpy 方案 | Chroma |
|---|---|---|
| **持久化** | 每次运行都重新 encode，等十几秒 | 算一次存硬盘，以后直接读 |
| **元数据** | 自己维护一个和向量顺序对应的列表，容易错位 | 每条记录自带 source、heading |
| **过滤** | 自己写 | 一个参数搞定 |
| **规模** | 几百万块逐个算点积太慢 | HNSW 索引做近似搜索 |

安装：`python -m pip install chromadb -i https://pypi.tuna.tsinghua.edu.cn/simple`，版本 1.5.9，`requirements.txt` 加 `chromadb==1.5.9`，`.gitignore` 加 `chroma_db/`。

### 5.2 核心概念

```
Client（指向硬盘上的一个文件夹）
 └── Collection（集合，相当于一张表，如 "notes"）
      └── Record（每块一条）
           ├── id         唯一编号，必须是字符串
           ├── document   原文
           ├── embedding  向量
           └── metadata   {"source": ..., "heading": ...}
```

> **档案柜的比方**：PersistentClient 是放柜子的房间（chroma_db 文件夹），Collection 是房间里一个叫 notes 的柜子，每张卡片有索书号（id）、正面内容（document）、"意思地图"上的坐标（embedding）、背面标签（metadata）。HNSW 是柜子里的分区目录，查询时先看目录，只在问题坐标附近那一片比较。

`col.add` 之后，`chroma_db` 里是一个 `chroma.sqlite3`（存编号、原文、元数据）和一个以 UUID 命名的文件夹（存向量和 HNSW 索引），都是二进制文件，通过 Chroma 读写。

### 5.3 三个大坑

**坑 1：Chroma 自带一个默认 embedding 模型。** 写入时不传 `embeddings`，或查询时用 `query_texts` 而不是 `query_embeddings`，Chroma 会自动用它的默认模型算向量。**写入和查询都要自己用 bge 算好再传。**

> 更正：讲课时我说这种情况"不会报任何错误"，在本周的场景下不对。默认模型输出 384 维，集合里存的是 512 维，查询时会直接报 `Collection expecting embedding with dimension of 512, got 384`。"不报错但结果没有意义"只会在两个模型**恰好维度相同**时出现，那才是最危险的情况。

**坑 2：返回的是距离不是相似度。** 用 `"hnsw:space": "cosine"` 后，返回余弦距离 = 1 − 余弦相似度，**越小越相关**。不指定的话默认 L2 距离，数值完全不同。

**坑 3：`query` 返回列表套列表，`get` 返回一层列表。** `query` 可以一次查多个问题，所以 `res["documents"][0]` 才是第一个问题的结果；`get` 只是按条件筛选，**不能取 `[0]`**。

### 5.4 build_index.py

```python
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"                   # 模型已缓存，离线模式

from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer
from week6.chunker import load_all_chunks            # 和 common.cost_tracker 一样从项目根目录写

ROOT = Path(__file__).parent.parent                  # build_index.py → week6/ → 项目根目录
DB_DIR = ROOT / "chroma_db"                          # Path 用 / 拼接子路径

# 切块
chunks = load_all_chunks(ROOT)                       # 591 个块字典
print(f"共 {len(chunks)} 块")
texts = [c["text"] for c in chunks]                  # 只取文本交给模型

# 算向量
model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
print(f"向量形状：{embeddings.shape}")                 # (591, 512)

# 连接数据库：先删旧集合，再新建，每次都是最新的完整索引
client = chromadb.PersistentClient(path=str(DB_DIR))   # path 要传字符串
try:
    client.delete_collection("notes")
except Exception:                 # 第一次运行时集合不存在，删除会报错，忽略
    pass                          # 若删除因其他原因失败，下面的 create 会报"已存在"，问题会暴露
col = client.create_collection(
    name="notes",
    metadata={"hnsw:space": "cosine"},               # 余弦距离
)

# 编号和出处
ids = [f"chunk-{i}" for i, c in enumerate(chunks)]                      # 必须唯一、必须是字符串
metadatas = [{"source": c["source"], "heading": c["heading"]} for c in chunks]

# 写入：四个列表长度相同，第 i 个元素描述第 i 块
col.add(ids=ids, documents=texts, embeddings=embeddings.tolist(), metadatas=metadatas)
print(f"集合里共有 {col.count()} 条记录")
```

运行结果：

```
共 591 块
Batches: 100%|██████████| 19/19 [00:15<00:00,  1.23it/s]
向量形状：(591, 512)
集合里共有 591 条记录
```

### 5.5 实验：重复运行会怎样

最初的版本用 `get_or_create_collection` + `add`，不改代码再运行一次：**count 仍是 591，没有报错也没有警告**。说明在 Chroma 里，**用已存在的 id 调用 add，新数据被直接忽略**。

这藏着一个坑：**笔记改了，索引不会更新**。修改了 week5 的某一段，重建时 `chunk-300` 已存在，add 直接忽略，柜子里还是旧内容。更隐蔽的是编号按位置生成，在 week1 里加一节，后面所有编号顺延，原文和坐标就对不上了。

| 方案 | 能解决"改了不更新" | 能解决"块变少了旧块还在" |
|---|---|---|
| `add` | ❌ | ❌ |
| `upsert`（有就更新，没有就插入） | ✅ | ❌ |
| **删除集合后全部重建** | ✅ | ✅ |

591 块重建只要十几秒，所以选全部重建。重建时用 `create_collection` 而不是 `get_or_create`：如果删除悄悄失败了，create 会报"已存在"把问题暴露出来，而 get_or_create 会悄悄打开旧集合。

### 5.6 search.py：语义检索

```python
model = SentenceTransformer("BAAI/bge-small-zh-v1.5")   # 必须和建库时同一个模型；放函数外，只加载一次
client = chromadb.PersistentClient(path=str(DB_DIR))
col = client.get_collection("notes")                    # 用 get：不存在就报错，提醒先建库


def search(query, k=3):
    """检索与问题最相关的 k 块，返回结果列表（只返回，不打印，供 rag.py 复用）"""
    query_vec = model.encode([query], normalize_embeddings=True)          # (1, 512)
    res = col.query(query_embeddings=query_vec.tolist(), n_results=k)     # 用 query_embeddings，不用 query_texts

    hits = []
    # 每个字段先取 [0]（只查了一个问题），zip 按位置配对
    for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0],
                                    res["metadatas"][0], res["distances"][0]):
        hits.append({
            "id": cid,                     # 块编号，混合检索去重用
            "text": doc,
            "source": meta["source"],
            "heading": meta["heading"],
            "score": 1 - dist,             # 余弦距离 → 相似度，越大越相关
            "via": "语义",
        })
    return hits                            # 和 for 对齐：3 个结果都放进去再返回
```

**search 只 return 不 print** 是一个设计原则：rag.py 要 import 它，把结果拼进 prompt。import 时，search.py 里不在函数中、也不在 `if __name__ == "__main__":` 下的代码（加载模型、打开集合）会自动执行，而 main 下面的提问循环不会执行。

### 5.7 检索测试（591 块）

| 问题 | 第 1 名 | 分数 | 判断 |
|---|---|---|---|
| 怎么把函数运行的结果交还给大模型？ | week5 · 1.7 结果回填 | 0.6048 | ✅ 前 3 名只差 0.008 |
| **422 错误是怎么回事** | **week2 · 7.3「400 判断成地址错」** | 0.6462 | ❌ 含 422 的块没进前 3 |
| 类属性和实例属性有什么区别 | week1 · 2.4（前 3 名都是这一节） | 0.7222 | ✅ |
| .env 文件为什么不能提交 | week1 · 6.9 .gitignore 两个必须记住的坑 | 0.6578 | ✅ |
| 怎么统计调用 API 花了多少钱 | week3 · 3.7 usage 统计块；week4 · 2.6 CostTracker | 0.6458 | ✅ |

```
问题（直接回车退出）：422 错误是怎么回事
1. 0.6462 | week2-git-http-async.md | 7.3 【犯了 2 次】400 判断成"地址错"
2. 0.6409 | week5-function-calling.md | 4.4 错误信息写给模型看
3. 0.6330 | week5-function-calling.md | 4.5 哪些回填，哪些直接停
```

**422 那题**：在 embedding 看来，400 和 422 都是"HTTP 错误码"，意思几乎一样；"错误处理"也和"错误是怎么回事"很像。**语义检索擅长理解意思，却分不清长得像的编号。** §2 的小实验没测出这个弱点，真实语料里出现了。

另外两个现象：**同一节占满 top-k**（类属性那题 3 个名额都是 2.4 节，v2 把它拆成了 3 块）；**每块开头的长标题路径**让同一文件的块彼此更像，可能是 Q1 前 3 名分数挤在一起的原因之一。

---

## 第六章 完整 RAG：检索 + 生成 + 出处

### 6.1 在线阶段的完整流程

```
你的问题
  ├─①检索──▶ hybrid_search(问题) ──▶ 3~5 块 + 出处
  ├─②拼 prompt──▶ 规则 + 编号资料 [1][2][3] + 问题
  ├─③生成──▶ 调用 DeepSeek ──▶ 带 [编号] 的回答
  └─④展示──▶ 回答 + 编号对应的出处 + 编号检查 + 本次花费
```

### 6.2 Prompt 设计

```
【system】
你是学习笔记问答助手。请遵守：
1. 只根据【资料】回答，不要用你自己的知识补充
2. 每个结论后面用 [编号] 标注它来自哪条资料，例如 [1] 或 [1][3]
3. 资料里没有答案时，直接回答"笔记中没有相关内容"
4. 资料里的代码可以直接引用

【user】
【资料】
[1] 出处：week5-function-calling.md > 1.7 结果回填
……正文……

[2] 出处：……

【问题】
怎么把函数运行的结果交还给大模型？
```

| 规则 | 作用 |
|---|---|
| 只根据资料 | 否则答案混入模型自己的知识，分不清哪些来自笔记，RAG 的价值在于**可核实** |
| 用编号标注 | 编号短，模型不容易抄错；**程序能核对**（资料只有 3 条，出现 [4] 就是编的）；完整出处由程序按编号打印 |
| 没有就说没有 | 对付幻觉的关键：明确允许它说不知道，它才敢说 |
| 规则 2 给出格式示例 | 第 4 周的 few-shot 思想 |

**为什么规则放 system、资料放 user？** DeepSeek 的缓存**按前缀匹配**。固定的规则放最前面，每次都能命中；资料每次都不同，放后面。如果资料在前，前缀每次不同，后面的规则一字不差也命中不了，按未命中价格贵 50 倍。

**`$contains` 不能随便用普通词**：用 "API" 匹配会找回几百块，而且 `$contains` **只判断有没有、不排序**，返回的是数据库里最先找到的几块，和问题相关度无关。

### 6.3 rag.py

```python
import os
import re                                    # 正则：找回答里的 [编号]
import sys
import httpx
from dotenv import load_dotenv

from week6.search import hybrid_search       # import 时自动加载模型、打开集合
from common.cost_tracker import CostTracker

load_dotenv()
API_KEY = os.getenv("DEEPSEEK_API_KEY")      # 变量名与自己 .env 中的一致；Key 绝不写死在代码里

MODEL = "deepseek-flash"                     # 连字符，不是下划线
URL = "https://api.deepseek.com/v1/chat/completions"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

SYSTEM_PROMPT = """你是学习笔记问答助手。请遵守：
1. 只根据【资料】回答，不要用你自己的知识补充
2. 每个结论后面用 [编号] 标注它来自哪条资料，例如 [1] 或 [1][3]
3. 资料里没有答案时，直接回答"笔记中没有相关内容"
4. 资料里的代码可以直接引用"""


def build_context(hits):
    """把检索结果拼成带编号的资料文本"""
    readings = []
    for i, h in enumerate(hits, 1):                       # 编号从 1 开始
        body = h["text"].split("\n", 1)[1]                # 去掉第一行标题路径（上面已写出处，避免重复）
        reading = f"[{i}] 出处：{h['source']} > {h['heading']}\n{body}"
        readings.append(reading)
    return "\n\n".join(readings)                          # 块与块之间空一行


def ask_llm(messages):
    """调用 DeepSeek，返回 (回答文本, usage)"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,                      # RAG 要忠实于资料，不需要发挥
        "max_tokens": 1000,                    # 要解释、引用代码，200 不够
        "thinking": {"type": "disabled"},
    }
    try:
        response = httpx.post(URL, headers=HEADERS, json=payload, timeout=30)
    except httpx.TimeoutException as e:        # 具体的异常在前
        print("超时了：", e)
        sys.exit(1)
    except httpx.RequestError as e:            # 宽泛的在后
        print("网络错误：", e)
        sys.exit(1)

    if response.status_code != 200:
        print(response.status_code)
        print(response.text)
        sys.exit(1)

    data = response.json()
    choice = data["choices"][0]
    if choice["finish_reason"] == "length":    # 正常结束是 "stop"，被 max_tokens 截断是 "length"
        print("⚠ 回答被截断，可以调大 max_tokens")
    return choice["message"]["content"], data["usage"]


def check_citations(answer, n):
    """找出回答里不合法的引用编号（不在 1~n 之间的），返回去重排序后的列表"""
    nums = re.findall(r"\[(\d+)\]", answer)     # 1. 找出所有 [数字]，得到字符串列表
    nums = [int(x) for x in nums]               # 2. 转成整数
    bad = [x for x in nums if not 1 <= x <= n]  # 3. 挑出不在 1~n 的
    return sorted(set(bad))                     # 4. 去重、排序


def rag(question, tracker):
    """检索 → 拼 prompt → 生成 → 记账，返回 (回答, 检索结果)"""
    hits = hybrid_search(question, k=3)
    context = build_context(hits)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"【资料】\n{context}\n\n【问题】\n{question}"},   # 和 system 一致用方头括号
    ]
    answer, usage = ask_llm(messages)
    tracker.record(MODEL, usage)               # 由 rag 记账，ask_llm 不依赖全局变量
    return answer, hits


if __name__ == "__main__":
    tracker = CostTracker()                    # 循环外创建：整个会话共用一个

    while True:
        q = input("\n问题（直接回车退出）：").strip()
        if not q:
            break

        answer, hits = rag(q, tracker)
        print("\n【回答】")
        print(answer)

        print("\n【出处】")
        for i, h in enumerate(hits, 1):        # 编号和 build_context 一一对应
            if h["score"] is None:
                print(f"[{i}] {h['source']} > {h['heading']}（关键词命中）")
            else:
                print(f"[{i}] {h['source']} > {h['heading']}（相似度 {h['score']:.4f}）")

        bad = check_citations(answer, len(hits))   # 给了几条就按几条检查，不写死 3
        if bad:
            print(f"⚠ 回答中出现了不存在的编号：{bad}")

    tracker.report()                           # 循环外：退出后打印整个会话的统计
```

**`check_citations` 的正则**：

| 符号 | 含义 |
|---|---|
| `r"..."` | 原始字符串，反斜杠不转义 |
| `\[` `\]` | 字面方括号（`[` 在正则里有特殊含义）。单独的 `]` 其实不用转义，PyCharm 会提示 Redundant character escape，写上更对称 |
| `\d+` | 一个或多个数字 |
| `( )` | 只取括号里的部分 |

```python
check_citations("回填要用 tool 消息 [1]，id 要和调用对应 [1][4]，详见 [0]", 3)   # → [0, 4]
check_citations("回填要用 tool 消息 [1][2]", 3)                                  # → []
check_citations("笔记中没有相关内容", 3)                                          # → []
```

### 6.4 第一轮测试（只有语义检索）

| # | 问题 | 检索 | 回答 | 判断 |
|---|---|---|---|---|
| 1 | 函数结果交还给大模型 | [1] 1.7 结果回填 | 只引用 [1]，[2][3] 不相关就没用 | ✅ |
| 2 | **422 错误是怎么回事** | 3 块都没有 422 | **"笔记中没有相关内容。资料里只涉及 400、404、401、402……没有提到 422 错误"** | ⚠ |
| 3 | 类属性和实例属性 | 3 块都是 2.4 | 分 4 点回答，[1][2][3] 都用上 | ✅ |
| 4 | Python 的 GIL 是什么 | 笔记里没有 | **"笔记中没有相关内容"** | ✅ 遵守规则 3 |
| 5 | 第 5 周 CostTracker 为什么会算错钱 | 1.10、遗留任务 | 引用了 $0.000087 和 $0.000124 | ✅ |

每个回答的编号都合法，没有出现警告。

**第 2 题：模型没错，错在检索。** 模型拿到的是 400 和错误处理的资料，没有硬凑答案，老实说"没有"，生成环节是正确行为。但笔记里明明有 422，排查顺序是先看检索，问题出在检索。所以要改的是检索，不是 prompt。

**第 4 题：分数没法判断"笔记里有没有"。** GIL 那题检索回来的 3 块完全无关，分数却是 0.6085、0.6084、0.6065，比第 1 题**正确答案**的 0.6048 还高。**不能用"相似度低于某个值"判断资料里没有答案**，只有 LLM 读完资料后能判断，这就是规则 3 必须存在的原因。

### 6.5 混合检索：语义 + 关键词

```
问题 ──┬──▶ 语义检索：embedding 找意思最接近的 3 块
       └──▶ 关键词检索：找字面上包含 "422" 的块（最多 2 块）
                  │
           合并、按 id 去重 ──▶ 交给 LLM
```

只挑**专有标识符**做关键词（含数字、下划线或点，至少 3 个字符），普通词交给语义检索。这是一个 🔧 设计决策，换了文档类型（比如法律条文的条款编号）要跟着调整。

```python
def extract_keywords(question):
    """从问题里挑出专有标识符：含数字、下划线或点，且至少 3 个字符（如 422、tool_call_id、json.loads）"""
    tokens = re.findall(r"[A-Za-z0-9_.]{3,}", question)    # 先找出连续 3 个以上的英文、数字、_、.
    return [t for t in tokens if any(ch.isdigit() or ch in "_." for ch in t)]   # 再只保留含数字、_ 或 . 的


def keyword_search(keyword, limit=2):
    """找原文里字面包含 keyword 的块，最多 limit 块"""
    res = col.get(where_document={"$contains": keyword}, limit=limit)
    hits = []
    for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"]):   # get 的结果不取 [0]
        hits.append({"id": cid, "text": doc, "source": meta["source"],
                     "heading": meta["heading"], "score": None, "via": "关键词"})   # 字面匹配没有相似度
    return hits


def hybrid_search(question, k=3):
    """语义检索 top-k，再补上关键词命中的块（去重）"""
    hits = search(question, k)                         # 第 1 路：语义
    seen = {h["id"] for h in hits}                     # 集合推导式：已有的编号，in 判断快
    for kw in extract_keywords(question):              # 第 2 路：每个关键词
        for h in keyword_search(kw):
            if h["id"] not in seen:                    # 语义已经找到的不重复加
                hits.append(h)
                seen.add(h["id"])
    return hits
```

| 问题 | `extract_keywords` 结果 |
|---|---|
| 422 错误是怎么回事 | `['422']` |
| 怎么统计调用 API 花了多少钱 | `[]`，API 不含数字被过滤 |
| tool_call_id 填错了会怎样 | `['tool_call_id']` |
| 第 5 周 CostTracker 为什么算错钱 | `[]`，5 太短，CostTracker 不含数字 |

没有关键词时，for 循环一次都不执行，结果和原来的 search 完全一样，**不影响普通问题**。

### 6.6 第二轮测试（混合检索）

**422 错误是怎么回事**

```
【回答】
422 是 FastAPI 在请求体校验失败时自动返回的错误，函数根本不会被执行 [4]。
具体来说，当参数类型注解写成模型类时，FastAPI 会自动做三件事：从请求体解析 JSON、按模型定义校验字段的存在性与类型、校验失败直接返回 422 [4]。……

【出处】
[1] week2-git-http-async.md > 7.3 【犯了 2 次】400 判断成"地址错"（相似度 0.6462）
[2] week5-function-calling.md > 4.4 错误信息写给模型看（相似度 0.6409）
[3] week5-function-calling.md > 4.5 哪些回填，哪些直接停（相似度 0.6330）
[4] week3-fastapi-docker.md > 2.1 它解决什么问题（关键词命中）
[5] week3-fastapi-docker.md > 2.2 422 报错信息怎么读（关键词命中）
```

| | 只有语义检索 | 混合检索 |
|---|---|---|
| 资料 | [1][2][3] 都没有 422 | 多了 [4][5] week3 关键词命中 |
| 回答 | "笔记中没有相关内容" | 正确解释 FastAPI 的 422，引用 [4][5] |

**遗留问题**：第 5 周笔记里那个 422（messages 多一层方括号）仍然没出现。笔记里含 "422" 的块不止 2 个，`limit=2` 取的是**最先存进库的 2 个**，week3 比 week5 先建索引。回答没错，但不完整。

**类属性和实例属性有什么区别**：没有关键词，资料、要点、编号和第一轮**完全一样**，混合检索没有影响普通问题。

**tool_call_id 是做什么的**：语义找到 3.2 节（2 块）和 1.6 节，关键词补上了 **[4] 1.7 结果回填**。回答的第 4 条"回填时 tool_call_id 必须和 assistant 消息里的 id 对应 [4]"就来自它，只用语义检索这一条会漏掉。

```
总调用次数： 3
总输入token： 2229
总输出token： 717
缓存命中token： 1020
缓存命中率：45.8%
总花费：$0.000615
```

平均每次提问约 740 token 输入、$0.0002。命中缓存的部分：固定的 system 规则每次都命中；"类属性"上一轮问过，资料完全相同，几乎整个 prompt 都命中。

---

## 第七章 典型错误合集

> ⚠️ **本章所有标记 ❌ 的代码都是错误示范，请勿复制使用。**
> 按根因分类而非时间顺序。标注"审查时发现"的错误是在运行前看代码时改掉的，没有实际运行输出，写的是按代码推断会出现的报错。

### 根因一：分不清对象、属性和数据的形状（本周最高频）

---

**错误 1：embed_demo.py 的计算部分（4 处问题在一段里）**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
query_vec = model.encode(query, normalize_embeddings=True)    # 问题 A：query 没包成列表
scores = query_vec.shape @ doc_vecs.T [0]                     # 问题 B、C
list(zip(scores, docs))                                       # 问题 D：算完没赋值，结果丢了
result = sorted(zip(scores, docs), reverse=True)
for scores, docs in result:                                   # 问题 E：循环变量和列表重名
    print(f"{scores} {docs}")
```

审查时发现，未运行。

| | 问题 | 后果 |
|---|---|---|
| A | `encode(query)` 传字符串 | 得到一维 `(512,)`，不是 `(1, 512)` |
| B | `query_vec.shape` | `.shape` 只是形状元组 `(1, 512)`，不是向量 |
| C | `doc_vecs.T [0]` | `.T` 和 `[0]` 先算、`@` 最后算，取的是 `doc_vecs.T` 的第 0 行，不是乘积的第 0 行 |
| D | 单独一行 `list(zip(...))` | 示例语法被照抄进来，结果没被使用 |
| E | `for scores, docs in` | 每次循环把原列表覆盖成一个数字和一句话，循环后原列表找不到了 |

**✅ 正确写法**：

```python
query_vec = model.encode([query], normalize_embeddings=True)   # (1, 512)
scores = (query_vec @ doc_vecs.T)[0]                           # 先乘，再取第 0 行
result = sorted(zip(scores, docs), reverse=True)
for score, doc in result:                                      # 复数是列表，单数是元素
    print(f"{score:.4f} {doc}")
```

> **运算优先级的类比**：`-2²` 先算平方再取负，结果是 -4；想要 4 必须写 `(-2)²`。`A @ B[0]` 同理，要先乘就写 `(A @ B)[0]`。

---

**错误 2：把块字典直接当文本交给模型（build_index.py）**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
texts = load_all_chunks(ROOT)       # 返回的是 [{"text":…, "source":…, "heading":…}, …]
texts_vec = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
print(texts_vec.shape)              # PyCharm 在 .shape 下画了波浪线
```

审查时发现，未运行。encode 需要字符串列表，传进字典会报错；而且后面第 6 步还要用 source、heading，字典必须先保存下来。

**✅ 正确写法**：

```python
chunks = load_all_chunks(ROOT)                 # 完整的块字典留着
texts = [c["text"] for c in chunks]            # 只取文本给模型
```

---

**错误 3：对问题字符串调用 `.tolist()`（search.py）**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
query_vec = model.encode([query], normalize_embeddings=True)   # PyCharm 把 query_vec 显示成灰色
res = col.query(query_embeddings=query.tolist(), n_results=k)  # query 是字符串
```

审查时发现，未运行。按代码会报 `AttributeError: 'str' object has no attribute 'tolist'`。

**线索**：`query_vec` 是灰色的，说明"算出来了但没用上"。**灰色变量几乎总是意味着某处用错了变量。**

**✅ 正确写法**：`col.query(query_embeddings=query_vec.tolist(), n_results=k)`

> **这是第 5 周"对字符串调用 `.json()`"的同类错误**：方法属于特定的对象。`.tolist()` 属于 numpy 数组，`.json()` 属于 httpx 响应，`.shape` 是 numpy 数组的属性。调用前先确认手里的变量是什么类型。

### 根因二：语法与占位符

---

**错误 4：冒号写成了类型注解**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
DB_DIR:ROOT / "chroma_db"
```

审查时发现，未运行。`变量名: 某个东西` 是**类型注解**，只声明不赋值，后面用到 DB_DIR 会报 `NameError: name 'DB_DIR' is not defined`。整行下面有波浪线。

**✅ 正确写法**：`DB_DIR = ROOT / "chroma_db"`

---

**错误 5：把讲解里的占位符和语法示例照抄进代码**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
变量名 = SentenceTransformer("BAAI/bge-small-zh-v1.5")    # "变量名"是占位说明

p = Path("某个文件.md")                                    # 演示语法用的三行，写在了模块顶层
text = p.read_text(encoding="utf-8")
lines = text.splitlines()
```

- 第一处：Python 3 允许中文变量名，能运行，但后面 `变量名.encode(...)` 很别扭，应改成 `model`
- 第二处：项目里没有"某个文件.md"，运行时直接 `FileNotFoundError`。函数参数 `lines` 下面的波浪线 `Shadows name 'lines' from outer scope` 也是它造成的

**教训**：讲解里的语法示例用的是别的变量名，是为了说明写法，不是要原样放进代码。

### 根因三：状态变量和控制流（chunker 与主程序）

---

**错误 6：chunk_markdown 的第一版（6 处错误）**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
    for line in lines:
        if line.startswith("```"):
            in_code = True                                  # 错误 1：开关只能开不能关
            buf.append(line)
            continue

        stripped = line.lstrip("#")
        if not in_code and line.startswith("#") and stripped.startswith(" "):
            level = len(line) - len(stripped)               # level 是灰色：算了没用
            title = stripped.strip()
            if buf != None:                                 # 错误 3：buf 是列表，永远不是 None
                chunks.append(make_chunk(path,buf,title))   # 错误 2：第三个参数应是 source
                buf = []                                    # 错误 4：清空和 continue 缩进进了 if

                continue
                                                            # 错误 5：漏了更新 path
        else:
            buf.append(line)
        if buf != None:                                     # 错误 6：收尾缩进在 for 里面
            chunks.append(make_chunk(path, buf, title))
    return chunks
```

审查时发现，未运行。

| # | 问题 | 后果 |
|---|---|---|
| 1 | `in_code = True` | 遇到第一个代码块开头后永远处于代码模式，后面所有标题失效，整篇只切出一块 |
| 2 | 传了 `title` 而不是 `source` | 出处记成了标题。线索：参数 `source` 是灰色的 |
| 3 | `if buf != None` | 条件永远成立；真正可能是 None 的是 make_chunk 的**返回值**，还会把 None 塞进 chunks |
| 4 | `buf = []`、`continue` 缩进进 if | 不管打包是否成功，都要清空并跳过，应和 if 对齐 |
| 5 | 漏了 `path = path[:level-1] + [title]` | 所有块的标题路径都是空的 |
| 6 | 收尾写在 for 里面 | 每读一行就打包一次，产生一堆碎块；`title` 下的波浪线：文件没标题时 title 未定义 |

**✅ 正确写法**：见 4.5 节完整代码。核心是 `in_code = not in_code`、`chunk = make_chunk(path, buf, source)` + `if chunk is not None`，以及收尾和 for 对齐。

---

**错误 7：rag.py 主程序的第一版（5 处错误）**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
if __name__ == "__main__":
    while True:
        answer, hits = rag("",tracker)          # 错误 1：tracker 没创建；错误 2：问题是空字符串
        print(answer)
        print(hits)                             # 错误 4：原样打印 3 个大字典
        check_result = check_citations(answer, 3)   # 错误 5：写死 3
        if check_result != []:
            print("存在不合法编号")
        else:
            break                               # 错误 3：编号合法就退出了
    tracker.report()
```

审查时发现，未运行。错误 1 按代码会报 `NameError: name 'tracker' is not defined`。

| # | 问题 | 改法 |
|---|---|---|
| 1 | tracker 没创建 | 循环**前**加 `tracker = CostTracker()`；放循环里每次都新建，统计就丢了 |
| 2 | `rag("", …)` | 先 `q = input(…).strip()`，直接回车就 break |
| 3 | `else: break` | 逻辑反了：第一个问题答对程序就结束。检查编号只需不合法时警告，不要 else |
| 4 | `print(hits)` | 用 enumerate 打印"编号 → 出处" |
| 5 | `check_citations(answer, 3)` | 用 `len(hits)`。混合检索后资料变成 4~5 条时，写死 3 会误报 |

第 5 点在加入混合检索后立刻体现出价值：资料从 3 条变成 5 条，`len(hits)` 自动跟着变。

---

**错误 8：照搬第 5 周的 call_llm（运行前改掉）**

第 5 周的 `call_llm` 结构能复用，但有两处不适合 RAG：

- `"max_tokens": 200`：第 5 周回答是"北京 12°C"这种短句，RAG 要解释概念、引用代码，200 会被拦腰截断。改成 1000，并检查 `finish_reason == "length"`
- 函数里直接 `tracker.record(...)`：悄悄依赖一个全局变量，只看参数 `call_llm(messages)` 看不出来，复制到别的文件就 `NameError`。改成返回 `(content, usage)`，由 `rag(question, tracker)` 记账

### 根因四：字符串常量和配置

---

**错误 9：模型名写成下划线**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
MODEL = "deepseek_flash"
```

运行结果：

```
问题（直接回车退出）：怎么把函数运行的结果交还给大模型？
400
{"error":{"message":"The supported API model names are deepseek-flash, deepseek-v4-pro, but you passed deepseek_flash. (request_id: 63d349c9-…

进程已结束，退出代码为 1
```

**✅ 正确写法**：`MODEL = "deepseek-flash"`（连字符）

错误处理按设计生效：状态码不是 200，打印状态码和错误信息后立即退出。报错信息直接列出了允许的模型名和你传的值。**看到 4xx，先读错误信息**，和第 5 周读 422 是同一个习惯。用了 `MODEL` 常量，改一处，请求和记账同时生效。

---

**错误 10：prompt 里的标记和 system 对不上**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
{"role": "user", "content": f"[资料]\n{context}\n\n[问题]\n{question}"}
```

审查时发现，未运行。system 规则写的是"只根据【资料】回答"，user 里却是英文方括号 `[资料]`：

- 规则里的标记在 user 消息里找不到，两边对不上
- `[资料]` 和引用格式 `[1]` 用的是同一种括号，模型可能混淆，甚至把 `[资料]` 当成引用写进回答

**✅ 正确写法**：`f"【资料】\n{context}\n\n【问题】\n{question}"`

---

**错误 11：文件名多了一个 .md**

`week2-git-http-async.md.md`。用 `git mv` 改名，Git 会识别为重命名，而不是"删一个、加一个"：

```
git mv week2-git-http-async.md.md week2-git-http-async.md
```

### 我（讲解方）的错误与更正

| 我当时说的 | 实际情况 |
|---|---|
| 检验题 3："422 这种数字 embedding 处理不好"；§2 Q3 命中后又改口说"说过头了" | 两次都不准确：小库里只有一句含 422 时能命中；真实 591 块里有一堆相近错误码时确实找错了（5.7 节） |
| Chroma 坑 1："用 query_texts 查询不会报任何错误" | 默认模型 384 维对 bge 512 维，会直接报维度不匹配；"不报错但无意义"只在维度恰好相同时出现 |
| PyCharm 提示时说"你还没把 sentence-transformers 加进 requirements" | 你第 19 行已经加了，只是 PyCharm 还没重新检查 |

---

## 第八章 本周自检

- [x] 能说清 RAG 解决什么问题，以及为什么不直接把整份文档塞进 prompt
- [x] 能区分 RAG 的离线阶段和在线阶段，以及它和"联不联网"无关
- [x] 能说清 RAG 和微调分别补的是什么
- [x] 知道建库和查询必须用同一个 embedding 模型，以及换模型要重建索引
- [x] 能在 Windows 虚拟环境里装好 sentence-transformers，会用国内镜像下载模型
- [x] 能区分 HuggingFace 的警告和真正的报错
- [x] 能解释 `(1,512) @ (512,6) → (1,6)`，以及归一化后点积为什么等于余弦相似度
- [x] 知道相似度只看相对排名、top-1 不可靠
- [x] 能说清块太大和块太小各有什么问题，以及代码块为什么不能切开
- [x] 能写出"扫描 → 遇到边界就打包 → 收尾"的骨架，并说出 chunker 里三个函数各自的边界是什么
- [x] 能解释 `in_code` 开关、`path[:level-1] + [title]`、`group and` 条件的作用
- [x] 能用统计数据（块数、长度分布、最长块）检查切块效果
- [x] 能用 Chroma 建库、查询，知道 query 和 get 返回格式的区别
- [x] 知道 add 已存在 id 会被忽略，以及为什么选择全部重建
- [x] 知道距离和相似度的换算，以及为什么要指定 cosine
- [x] 能设计带编号引用的 RAG prompt，说出三条规则的作用
- [x] 能从缓存角度解释规则为什么放在 system 里
- [x] 能用正则检查引用编号是否合法
- [x] 能按"先看检索，再看 prompt"的顺序排查 RAG 答错的问题
- [x] 知道相似度分数不能用来判断"资料里有没有答案"
- [x] 能说清语义检索和关键词检索各自擅长什么，并实现简单的混合检索

---

## 附录 A：RAG 速查

### 照搬的部分（记住或会查就行）

| 内容 | 写法 |
|---|---|
| HF 镜像 | `os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"`，写在 import 之前 |
| 加载模型 | `SentenceTransformer("BAAI/bge-small-zh-v1.5")` |
| 编码 | `model.encode(列表, normalize_embeddings=True)`，单个问题也包成列表 |
| 连库 | `chromadb.PersistentClient(path=str(DB_DIR))` |
| 建集合 | `create_collection(name=…, metadata={"hnsw:space": "cosine"})` |
| 写入 | `col.add(ids=…, documents=…, embeddings=….tolist(), metadatas=…)` |
| 查询 | `col.query(query_embeddings=….tolist(), n_results=k)`，结果取 `[0]` |
| 字面匹配 | `col.get(where_document={"$contains": 词}, limit=n)`，结果不取 `[0]` |
| 转相似度 | `1 - distance` |

**两条铁律**：① 建库和查询用同一个模型；② 自己算好向量再交给 Chroma。

### 要自己设计的部分（换项目时重新想）

| 设计决策 | 本周的选择 | 换项目时要问自己 |
|---|---|---|
| 怎么切 | Markdown 标题 → 空行 → 字数 | PDF 按页还是按段？代码按函数？ |
| 切多大 | 450 字 | 模型能读多长？一个知识点通常多长？ |
| 什么不能切开 | 代码块 | 表格？公式？对话的一问一答？ |
| 块里放什么 | 文件名 + 标题路径 + 正文 | 还要加什么上下文才能单独看懂？ |
| 元数据 | source、heading | 页码？URL？日期？要不要按类别过滤？ |
| 模型 | bge-small-zh | 什么语言？准确率和速度的要求？ |
| 更新策略 | 每次全部重建 | 数据量多大？多久更新一次？ |
| 取几块 | k=3 + 关键词最多 2 块 | 能否接受漏检？prompt 成本预算？ |
| 关键词规则 | 含数字、_、. 且 ≥3 字符 | 语料里有哪些"专有标识符"？ |
| 怎么验证 | 统计长度 + 固定测试问题 | 测试集要包含哪些容易错的问题（比如 422）？ |

## 附录 B：本周新语法

| 语法 | 例子 | 说明 |
|---|---|---|
| numpy 矩阵乘法 | `a @ b.T` | `.T` 转置；`(1,512) @ (512,6) → (1,6)` |
| `.shape` | `arr.shape` → `(6, 512)` | 属性，不加括号 |
| 带筛选的列表推导式 | `[n for n in lengths if n > 500]` | 先筛选再组成新列表 |
| 集合推导式 | `{h["id"] for h in hits}` | 花括号，结果是集合，`in` 判断快 |
| `set` 去重 | `sorted(set([4, 4, 0]))` → `[0, 4]` | 集合自动去重，sorted 转回有序列表 |
| `extend` vs `append` | `a.extend([3, 4])` | extend 逐个加入；append 把整个列表当一个元素 |
| `sorted` 的 key | `sorted(cs, key=lambda c: len(c["text"]))` | 字典没法直接比大小，告诉它按什么比 |
| `lambda` | `lambda c: len(c["text"])` | 一行的小函数 |
| 三元表达式 | `path[-1] if path else ""` | 一行的 if/else |
| 连写比较 | `1 <= x <= n` | 和数学写法一样 |
| `any` | `any(ch.isdigit() for ch in t)` | 有一个满足就是 True |
| `str.split(sep, 1)` | `"a\nb\nc".split("\n", 1)` → `['a', 'b\nc']` | 最多切一次 |
| `str.lstrip(字符)` | `"## 标题".lstrip("#")` → `" 标题"` | 去掉左边指定字符 |
| `repr` | `repr(line)` | 显示看不见的字符（如 BOM） |
| 正则 `re.findall` | `re.findall(r"\[(\d+)\]", s)` | 找出所有匹配，只取括号里的部分 |
| 多行字符串 | `"""第一行\n第二行"""` | 直接换行 |
| `Path` | `Path(__file__).parent.parent`、`root / "data"`、`root.glob("*.md")` | 定位、拼接、匹配文件 |
| `input` + `while True` | `q = input("问题：").strip()` | 交互式循环，空输入 break |
| `raise SystemExit` | | 主程序里提前结束 |
| 类型注解（踩坑） | `x: int` | 只声明不赋值，`DB_DIR:` 就是这样出错的 |

## 附录 C：提交记录

```
refactor: move CostTracker to common/, track cache hit pricing
feat: week6 embedding demo with bge-small-zh
feat: week6 markdown chunker with heading path and code-block protection
feat: chunker v2 - split long sections by paragraph, add source prefix, drop hr lines
feat: build Chroma index for week1-5 notes with bge embeddings
feat: semantic search over notes with Chroma, return top-k with sources
feat: RAG pipeline with citations, citation check and hybrid keyword search
chore: ignore data/ for project-1 corpus
```

---

## 遗留任务

- **关键词命中重排**：`limit=2` 取的是最先入库的块，422 找到了 week3 却漏了 week5。改成先取 10 个候选，再按语义相似度排序取前 2（"召回 + 重排"雏形），约 5 行代码
- **同一节占满 top-k**：同一 heading 只保留得分最高的一块，或把相邻块合并后交给 LLM
- **标题路径过长**：同一文件所有块共享很长的前缀，可能让块彼此"更像"；可以只保留文件名和最后两级标题，做对照实验
- **项目一语料接入**：Hello-Agents 中文版（正文 16 章 + 扩展 14 篇，约 115 万字符）已放在 `data/hello-agents-zh/`，CC BY-NC-SA 4.0 许可，`data/` 已加入 .gitignore。chunker 的文件匹配要改成 `rglob("*.md")`
- **第 5 周遗留**：工具参数预校验、tools 声明与 tool_map 统一来源、消融实验扩大样本
- **第 4 周遗留**：多轮对话滑动窗口、few-shot 版简历抽取

---

## 下周预告

把本周的 RAG 系统用到**项目一语料 Hello-Agents** 上：几百页的真实教程，代码块更多、章节更长，切块和检索都会遇到新问题。先补上关键词重排，再建一套固定的测试问题，用数据比较每个改进的效果。

语料本身讲的就是 Agent：第八章"记忆与检索"讲 RAG，第九章是上下文工程，第十章是 MCP。**用自己写的 RAG 去检索一本讲 RAG 和 Agent 的书**，一边做项目一边预习后面的内容。

这也离你的研究方向更近了一步：本周的 RAG 默认"资料都是对的"。当检索回来的几块**互相矛盾，或者有新有旧**时，模型会怎么选？这正是"记忆冲突与时间一致性"要回答的问题。
