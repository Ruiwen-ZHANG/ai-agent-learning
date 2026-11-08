# 第 8 周技术总结：项目一上线——服务化、聊天网页与 Docker

> 16 周 AI Agent 应用开发学习记录 · 第 8 周
> 关键词：延迟优化、rag_app 工程化、FastAPI lifespan、同源与 CORS、HTML/CSS/JS、fetch、res.ok、marked、DOMPurify、XSS、Dockerfile、层缓存、CPU 版 torch、.dockerignore、--env-file、分支与 PR

---

## 本周概览

第 7 周做出了一组漂亮的检索指标（test 集 Hit@3 87.5%），但它只是**一堆脚本**：每个问题要等 10 秒，只能在 PyCharm 里运行，别人既用不了，也看不懂。

第 8 周要把它变成一个**能交付的项目**：

1. **够快**：用评测集量化"省几秒、掉几分"，把重排延迟从 10 秒降到 3~4 秒
2. **够规整**：从 week7 的练习脚本整理成独立的 `rag_app` 包
3. **能被调用**：用 FastAPI 包成 HTTP 服务
4. **能被使用**：做一个聊天网页，不会编程的人也能提问、看到出处
5. **能被搬走**：Docker 打包，换一台机器 `docker run` 就能跑
6. **能被看懂**：README 写清楚架构、选型理由和评测数据

> **比方**：第 7 周是在自家厨房里把菜做好吃了；第 8 周是开一家餐厅——定菜单（API）、摆好店面（网页）、做成冷冻便当能外送（Docker）、门口贴上介绍（README）。

| 小节 | 内容 | 产出文件 |
|---|---|---|
| §0 | 重排延迟实验：pool × max_length 四种配置 | `week8/latency_exp.py` |
| §1 | 整理成独立项目 rag_app：配置中心、依赖单向、模型只加载一次 | `rag_app/*.py` |
| §2 | FastAPI 服务：`/health`、`/ask`，错误码设计 | `rag_app/api.py` |
| §3 | 聊天网页：第一次写 HTML 和 JavaScript，7 小步完成 | `rag_app/static/index.html`，修改 `api.py` |
| §4 | Docker 打包：CPU 版 torch、模型进镜像、Key 不进镜像 | `rag_app/Dockerfile`、`rag_app/Dockerfile.dockerignore`、`rag_app/requirements.txt`、`rag_app/download_models.py` |
| §5 | README：用 Claude Code 开 PR 更新，网页上传截图，合并 | `README.md`、`.env.example`、`assets/chat-page.png` |

**本周最有分量的产出**：

| 项目 | 结果 |
|---|---|
| 重排延迟 | dev 集每题 8.33 秒 → **2.86 秒**（快 2.9 倍，只少答对 2 题）；test 集 10.40 秒 → **3.94 秒** |
| 聊天网页 | 回答 Markdown 排版 + 安全清洗、出处带分数、422/502/500/网络错误都有清楚提示 |
| Docker 镜像 | 压缩后 **1.65 GB**（解压后 4.94 GB），自带模型和向量库，Key 不在镜像里 |
| README | 架构图、选型理由、评测表、延迟表、运行方法、截图，PR #2 合并 |

**代码仓库**：`https://github.com/Ruiwen-ZHANG/ai-agent-learning`

### 本周文件一览

```
rag_app/
├── __init__.py              包的"门牌"
├── config.py                配置中心：HF 镜像/离线、路径、检索参数、模型名（RAG_ 前缀环境变量可覆盖）
├── chunker.py               切块（来自 week7）
├── build_index.py           入口：离线建库，2505 块
├── retriever.py             Retriever 类：模型、Chroma、BM25 一次性加载
├── llm.py                   ask_llm：调用 DeepSeek，重试 + 指数退避
├── rag.py                   SYSTEM_PROMPT、build_context、check_citations、answer
├── cli.py                   入口：命令行问答（依赖根目录的 common/）
├── api.py                   入口：FastAPI 服务（GET /、GET /health、POST /ask）
├── static/index.html        聊天网页
├── download_models.py       Docker build 时下载两个模型
├── requirements.txt         Docker 用的精简依赖（不含 torch）
├── Dockerfile               项目一镜像
└── Dockerfile.dockerignore  只对上面这个 Dockerfile 生效的排除清单

week8/latency_exp.py         §0 延迟实验
assets/chat-page.png         README 里的页面截图
README.md、.env.example      §5 更新
```

---

## 第一章 §0 重排延迟优化

### 1.1 先测，再改：分段计时

第 7 周最终方案每题 10.40 秒。优化之前先回答一个问题：**时间到底花在哪里？**

```
召回（BM25 + 语义）：0.066 秒
重排（bge-reranker）：7.11 秒      ← 占 99%
平均候选块数：34.1 块，平均每块 444 字
```

召回几乎不花时间，所以只优化重排。重排的耗时大致正比于"**候选块数 × 每块读多少 token**"，于是有两个旋钮：

| 旋钮 | 含义 | 调小的代价 |
|---|---|---|
| `pool` | BM25 和语义检索各取前几块，再取并集 | 召回率可能下降 |
| `max_length` | reranker 每块最多读多少 token | 只读每块开头，长块后半部分看不到 |

> 经验：**优化前先分段计时。** 凭感觉去优化召回，就算召回快了 10 倍，总耗时也只少了不到 1%。

### 1.2 dev 集上的四种配置

在 dev 集（91 题）上，两个旋钮各取两档，一共 4 种组合。格式为"严格 Hit@3 / MRR；同节 Hit@3 / MRR；平均耗时"：

| 配置 | pool | max_length | 严格 Hit@3 / MRR | 同节 Hit@3 / MRR | 平均耗时 |
|---|---|---|---|---|---|
| A | 20 | 512 | 85.7 / 82.5 | 93.4 / 88.7 | 8.33 秒 |
| B | 10 | 512 | 84.6 / 81.4 | 92.3 / 88.5 | 4.76 秒 |
| C | 20 | 256 | 84.6 / 80.5 | 92.3 / 88.3 | 5.53 秒 |
| **D** | **10** | **256** | **83.5 / 79.4** | **92.3 / 87.6** | **2.86 秒** |

**读表**：

- 两个旋钮**各自**都能省时间：B（只减 pool）省了 43%，C（只减 max_length）省了 34%
- 两个一起调（D），耗时只剩 A 的三分之一
- 代价很小：严格 Hit@3 从 85.7% 降到 83.5%，91 题里**只少答对 2 题**；同节 Hit@3 只差 1 题

**选择 D**：快 2.9 倍，只少答对 2 题。用户等 3 秒和等 10 秒，体验差别很大；少答对 2% 的题，大多数用户感觉不到。

### 1.3 test 集：如实报告

test 集已经在第 7 周用过一次（验证配置 A），这是**第 2 次使用**：

| test 集（32 题） | 严格 Hit@3 / MRR | 同节 Hit@3 / MRR | 平均耗时 |
|---|---|---|---|
| A（第 7 周） | 87.5 / 82.1 | 90.6 / 86.6 | 10.40 秒 |
| D（本周部署配置） | 81.2 / 74.7 | 84.4 / 81.1 | 3.94 秒 |

- 严格 Hit@3 差 6.3 个百分点，就是 32 题里差了 **2 题**，和 dev 上"少答对 2 题"一致
- **MRR 的下降是真实的**：正确答案的排名整体往后挪了一些
- 决策依据仍然是 dev 集，test 上的结果**照实报告，不因为它变差就改选 A**

> **test 集以后不再用于调参。** 每多用一次，test 集就多一分"被我们看过"，分数就越不能代表新问题上的表现。

### 1.4 不改代码就能切回 A

配置写进 config.py，并且支持环境变量覆盖（见第二章）。以后有 GPU、重排不再是瓶颈时：

```
RAG_POOL=20
RAG_RERANK_MAX_LEN=512
```

---

## 第二章 §1 整理成独立项目 rag_app

### 2.1 为什么要整理

week6、week7 是"学习过程"：每周复制上一周的文件再修改，`search.py` 里堆着语义、BM25、RRF、重排好几种检索函数，评测脚本和问答脚本混在一起。这适合学习和做对比实验，但不适合交付：

- 别人看不出**哪个才是最终方案**
- 模型、路径、参数散落在好几个文件里，改一个参数要改好几处
- 第 7 周遗留任务里就有一条：**配置集中**（集合名、数据库路径、模型名只定义一次）

所以本周新建 `rag_app/`，只放最终方案用到的代码。week6、week7 保持原样，作为学习记录。

### 2.2 模块结构

| 文件 | 角色 | 被谁用 | 自己用谁 |
|---|---|---|---|
| config.py | 配置中心（HF 镜像/离线环境变量、路径、POOL / RERANK_MAX_LEN / TOP_K / LLM_MODEL，支持 `RAG_` 前缀环境变量覆盖，用 `int()` 转换） | 所有 | 无 |
| chunker.py | 切块（复制自 week7，参数来自 config） | build_index | config |
| llm.py | ask_llm：调用 DeepSeek，重试 3 次并指数退避，非 200 时抛 RuntimeError，Key 从 .env 读取 | rag | .env |
| retriever.py | Retriever 类：`__init__` 一次性加载 bge-small、reranker、Chroma、BM25；search / bm25_search / candidates / retrieve | cli、api | config |
| rag.py | SYSTEM_PROMPT（4 条规则）、build_context、check_citations、answer(question, retriever, tracker=None) | cli、api | llm |
| build_index.py | 入口：离线建库，共 2505 块 | 直接运行 | config、chunker |
| cli.py | 入口：命令行问答 | 直接运行 | retriever、rag、CostTracker |
| api.py | 入口：FastAPI 服务 | uvicorn | retriever、rag |

### 2.3 两条设计原则

**① 依赖单向**

```
入口（api.py、cli.py、build_index.py）
    ↓
rag.py / retriever.py
    ↓
llm.py / config.py
```

下层永远不 import 上层。这样改 api.py 不会影响 rag.py；以后再加一个入口（比如 MCP Server），直接复用下面两层。

**② 慢的操作只做一次**

加载两个模型、建 BM25 索引要十几秒。如果写在模块顶层，**import 一下就开始加载**；如果每个问题都加载一次，每题都要多等十几秒。所以：

- 模型在 `Retriever()` **创建对象时**才加载（import 时不加载）
- `answer(question, retriever)` 通过**参数**接收已经建好的 retriever，自己不创建

比喻：厨师每天开店时开一次火，而不是每来一个客人就重新生一次火。

### 2.4 config.py 的两个关键设计

```python
# setdefault：环境变量里已经设置了就不覆盖，没设置才用这里的值（Docker 里可以改成联网下载）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")          # 国内镜像
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")          # 关掉 Windows 符号链接警告
os.environ.setdefault("HF_HUB_OFFLINE", "1")                           # 模型已缓存，只读本地，不联网检查

ROOT = Path(__file__).parent.parent                                    # config.py → rag_app/ → 项目根目录
DB_DIR = Path(os.getenv("RAG_DB_DIR", str(ROOT / "chroma_db")))         # Chroma 数据库文件夹
POOL = int(os.getenv("RAG_POOL", "10"))                                 # 召回时 BM25 和语义各取几块
RERANK_MAX_LEN = int(os.getenv("RAG_RERANK_MAX_LEN", "256"))            # reranker 每块最多读多少 token
LLM_MODEL = os.getenv("RAG_LLM_MODEL", "deepseek-flash")                # 连字符，不是下划线
```

| 设计 | 好处（本周实际用上了） |
|---|---|
| `setdefault` 而不是直接赋值 | §4 Docker build 下载模型时，在命令前加 `HF_HUB_OFFLINE=0` 就能联网，config.py 不用改 |
| 路径基于 `__file__` | §4 容器里项目放在 `/app`，`ROOT` 自动变成 `/app`，路径不用改 |
| `RAG_` 前缀环境变量覆盖 | §3 测试 502 时，用 `RAG_LLM_MODEL=no-such-model` 制造错误，不用动代码，也不用动 .env |
| `int()` 转换 | 环境变量读出来永远是字符串，`"10"` 不转换的话，切片 `[:POOL]` 会报错 |

### 2.5 一个问题的完整流程

```
answer(q)
  → retriever.retrieve(q)
      → candidates：bm25_search(10) + search(10)，去重后约 15~20 块
      → reranker.predict 打分，取前 3
  → build_context：生成带编号的资料 [1][2][3]
  → ask_llm：DeepSeek 生成回答
  → check_citations：检查回答里的编号是否都存在
  → 返回 {answer, sources, bad_citations, usage}
```

实例：问"ReAct 智能体为什么要设置最大步数？"，正确答案在 chunk-962（第七章 > 7.4.2 ReActAgent，396 字，包含"max_steps：ReAct循环的最大执行步数，防止无限循环"）。它走完全程，3 条出处的重排分数是 0.9804 / 0.9315 / 0.8858，tokens 708 / 64。本周后面网页、Docker 的测试都用这个问题，**每次的出处和分数都完全一致**，这本身就是一个很好的回归检查。

提交：`5c5eec0`（rag_app）；`93cec80`（修复 chunker 里的重复 import）。

---

## 第三章 §2 FastAPI 服务

### 3.1 要点

| 要点 | 做法 | 原因 |
|---|---|---|
| 模型只加载一次 | `lifespan`（`asynccontextmanager`）里创建 `Retriever()`，放进 `app.state` | 服务启动时加载一次，所有请求共用 |
| `/ask` 用普通 `def` | 不用 `async def` | 检索和调模型是**同步的慢操作**；普通 def 会被 FastAPI 放进线程池执行，不会卡住其他请求 |
| 请求校验 | `AskRequest` 的 `question` 用 `Field(min_length=1, max_length=500)` | 空问题和超长问题在进入检索之前就被拦下 |
| 响应校验 | `Source` 嵌套模型，`AskResponse` 设为 `response_model` | 返回的字段和类型有保证，/docs 里也能看到格式 |
| 错误码 | LLM 出错（`httpx.HTTPError`、`RuntimeError`）→ 502；参数校验失败 → 422；未捕获的异常 → 500 | 调用方看状态码就知道是谁的问题 |

错误处理的写法（detail 的具体文字以仓库中的 api.py 为准）：

```python
    try:
        result = answer(req.question, retriever)                  # 调用 RAG 主流程
    except (httpx.HTTPError, RuntimeError) as e:                 # 网络错误、DeepSeek 返回非 200
        raise HTTPException(status_code=502, detail=f"大模型调用失败：{e}")   # 502：上游（DeepSeek）出错
```

### 3.2 三个状态码的含义

| 状态码 | 谁的问题 | 比喻 |
|---|---|---|
| 422 | **调用方**：请求格式不对 | 顾客的点菜单填错了，窗口直接退回 |
| 502 | **上游**：DeepSeek 没响应或报错 | 后厨没问题，供应商没送货 |
| 500 | **我们自己**：代码有 bug | 后厨自己出了事故 |

### 3.3 测试结果

| 测试 | 结果 |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `POST /ask` 正常提问 | 200，缓存命中 512 tokens |
| JSON 里写成中文引号 | 422 `json_invalid` |
| 空问题 | 422 `string_too_short` |

### 3.4 §3 时新增的 `GET /`

```python
from fastapi.responses import FileResponse

INDEX_HTML = pathlib.Path(__file__).parent / "static" / "index.html"   # 以 api.py 所在位置为起点，不受启动目录影响


@app.get("/", include_in_schema=False)       # 网页不是接口，不写进 /docs
def index():
    return FileResponse(INDEX_HTML)          # 读取文件内容发给浏览器，自动设置 Content-Type: text/html
```

- `include_in_schema=False`：/docs 是给"调用 JSON 接口的开发者"看的说明书，网页放在里面会让人困惑。验证：/docs 里只剩 /health 和 /ask
- index.html 还没建时访问 `/`，浏览器显示纯文本 `Internal Server Error`，终端报 `RuntimeError: File at path ... does not exist`。这正好演示了 **500 返回的不是 JSON**（§3 错误处理要用到）

### 3.5 后来发现：/health 的 loading 分支永远执行不到

/health 当初设计成"模型没加载完返回 loading，加载完返回 ok"。§5 写 README 时 Claude Code 指出：**uvicorn 要等 lifespan 里的加载全部完成，才开始接收请求**，加载期间请求根本进不来，所以实际上永远看不到 loading。

`else: return {"status": "loading"}` 在当前设计下是**执行不到的代码**。README 里只写返回 `{"status": "ok"}`。

---

## 第四章 §3 聊天网页：第一次写前端

### 4.1 为什么要做网页

| 问题 | 回答 |
|---|---|
| 这是不是要自己设计一个前端？ | 是，但规模很小：一个页面、一百多行 HTML + JS，不用前端框架，不追求好看 |
| 目的是什么？ | ① 面试官、HR 不会 clone 仓库跑 Python，点开链接就能提问；② 把"引用溯源"直观地展示出来；③ /docs 给开发者，网页给普通用户；④ 完整走一遍"浏览器 → 服务器 → 模型 → 浏览器" |
| 做完别人能用吗？ | 现在只有自己（`127.0.0.1` 就是"我自己"）；同一 Wi-Fi 下用局域网 IP 可以；任何人都能用要等部署到云服务器 |
| 别人提问用的是谁的 token？ | **你的 Key、你的钱**。Key 一直在服务器的 .env 里，网页只把问题发给 `/ask`，由服务器带着 Key 去调 DeepSeek |

**为什么 Key 绝不能写进前端**：网页文件会被**原样发给每个访问者**，在他的浏览器里运行，按 F12 就能看到全部内容。Key 写在里面，等于把采购卡复印给每个顾客。

一个问题约 $0.00014（输入 700 tokens、输出 60 tokens），1000 个问题约 1 块钱。真正的风险是**被恶意刷接口**，公开部署前要做：DeepSeek 少充值、IP 限流、每日上限、访问口令。

### 4.2 用餐厅来理解前后端

| 现实 | 比喻 |
|---|---|
| 浏览器 | 顾客 |
| FastAPI 服务 | 餐厅 |
| `GET /`（返回 index.html） | 迎宾台：顾客进门，递上菜单 |
| `POST /ask` | 点菜窗口：接收订单，交给后厨 |
| retriever + rag + DeepSeek | 后厨（DeepSeek 是外面的供应商） |
| 网页里的 JS | 服务员：把单子送到窗口，再把菜端回来 |
| JSON | 规定格式的点菜单 |

网页由三部分组成：

| | 是什么 | 比喻 | 本节用来做什么 |
|---|---|---|---|
| HTML | 页面上**有什么** | 墙、门、窗 | 输入框、按钮、消息区 |
| CSS | 东西**长什么样** | 装修 | 颜色、间距 |
| JavaScript | 东西**怎么动** | 电线和开关 | 提交问题、显示回答 |

**JS ≠ JSON ≠ Java**：JavaScript 是在浏览器里运行的编程语言；JSON 是一种数据格式（JavaScript Object Notation，借用了 JS 写对象的格式，Python 的 `json.dumps` 读写的就是它）；Java 是另一门无关的语言。**浏览器只认 HTML、CSS、JS 三种**，所以网页里不能写 Python。前后端语言不同，靠 JSON 交流。

### 4.3 同源与 CORS

浏览器规定：页面从哪个"源"（`协议 + 主机 + 端口`）加载，JS 默认只能访问同一个源的接口。

| 页面从哪来 | 访问 `/ask` | 结果 |
|---|---|---|
| `http://127.0.0.1:8000/`（FastAPI 的 `GET /` 返回） | `http://127.0.0.1:8000/ask` | 同源，成功 |
| PyCharm 浏览器图标打开（`http://localhost:63342/...`） | `http://127.0.0.1:8000/ask` | 端口不同，**跨源**，被拦下 |
| 双击 html 文件（`file:///D:/...`） | 同上 | 跨源 |

> **比喻**：访客证只能进发证的那栋楼。CORS 是那栋楼愿意给外来访客放行的名单。

让 FastAPI 自己返回网页，页面和接口就是同一个源：fetch 直接写 `/ask`，不用配置 CORS，部署后换了域名也不用改代码。

### 4.4 拆成 7 小步

第一轮讲解后，7 道检验题一道都答不上来（前端概念全是第一次接触），于是改成**每一步都能在浏览器里看到效果**：

| 步 | 做什么 | 看到什么算成功 |
|---|---|---|
| 1 | api.py 加 `GET /`；index.html 只写一个标题 | 访问 `/` 能看到标题，/docs 里没有 `/` |
| 2 | 加 form、input、button、消息区 div | 页面上出现输入框和按钮 |
| 3 | JS 接管提交：`preventDefault`，打印输入内容 | 控制台打印出输入，页面不刷新 |
| 4 | `fetch` POST `/ask`，打印返回结果 | 控制台看到 200 和 answer / sources |
| 5 | 回答和出处显示到页面（textContent） | 页面上能看到问答和出处 |
| 6 | marked 排版 + DOMPurify 清洗 | 粗体、代码样式、分段都正常 |
| 7 | 思考中、禁用按钮、错误处理、样式 | 7 项测试全部通过 |

### 4.5 关键概念

**① HTML 的三条规则**（和 Python 最不一样的地方）

```html
<p>这是一段文字</p>                       <!-- 开始标签 + 内容 + 结束标签（多一个斜杠），不是冒号加缩进 -->
<input id="question" placeholder="请输入问题">   <!-- 设置写成"属性名=值"；只有设置没有内容的标签不用关闭 -->
<!-- 注释写在这里 -->
```

| 属性 | 给谁看 | 作用 |
|---|---|---|
| `id` | JS | 元素的名字，`getElementById` 靠它找到元素，页面上看不到 |
| `placeholder` | 用户 | 输入框为空时的灰色提示文字 |
| `class` | CSS | "衣服款式"，很多元素可以穿同一款，CSS 一次给它们上色 |

**② form 的"老习惯"**

不写 JS 时按回车，页面会**整页刷新**：地址栏变成 `/?`，uvicorn 终端每按一次多一行 `"GET / HTTP/1.1" 200 OK`。这是 JS 流行之前的表单提交方式：把内容发给服务器，跳转到新页面。

> **比喻**：顾客把点菜单交出去，服务员不是送去后厨，而是把整张桌子撤走换了一张新的。

所以提交处理函数的第一行是 `event.preventDefault()`：拦住老习惯，交给 JS 处理。

**③ 服务员回来了，不代表菜做好了（本节最重要的一句话）**

```
服务器有回应（200、422、500、502 都算）→ fetch 正常返回 res，不进 catch
网络不通（服务没启动、断网、被 CORS 拦下）→ fetch 抛出 TypeError，进 catch
```

所以拿到 res 以后必须先看 `res.ok`（状态码在 200~299 才是 true）。和第 2 周 httpx 要检查 `status_code` 是同一个道理。

不同错误的 body 格式也不一样：

| 状态码 | 由谁产生 | body |
|---|---|---|
| 422 | Pydantic 校验失败 | `{"detail": [{"loc": [...], "msg": "...", "type": "string_too_short"}]}`，detail 是**数组** |
| 502 | 我们自己 raise 的 HTTPException | `{"detail": "..."}`，detail 是**字符串** |
| 500 | 未捕获的异常 | 纯文本 `Internal Server Error`，**不是 JSON**，`res.json()` 会报 SyntaxError |

**④ marked 是排版员，DOMPurify 是安检员**

- `marked.parse(md)`：Markdown → HTML 字符串。但它**照单全收**，回答里夹带的 `<img src=x onerror="...">` 会原样保留
- 直接赋给 `innerHTML`，浏览器会把它当指令执行，这就是 **XSS**
- 模型输出是**不可信数据**：Hello-Agents 语料里本来就有很多 HTML；第 11 周还会讲到有人在文档里埋注入指令
- 正确顺序：`DOMPurify.sanitize(marked.parse(answer))`，**安检必须是最后一道**

实测（控制台）：

```
marked.parse('<img src=x onerror="alert(1)">')                      → 结果里 onerror 还在
DOMPurify.sanitize(marked.parse('<img src=x onerror="alert(1)">'))   → onerror 被没收
```

**⑤ innerHTML 是说明书，textContent 是玻璃展示柜**

| | 效果 | 本页面用在 |
|---|---|---|
| `innerHTML` | 把内容当 HTML 执行，`<strong>` 变粗体，`<script>` 也会执行 | 只有回答（经过排版和安检） |
| `textContent` | 原样显示，什么都不执行，天然安全 | 用户的问题、出处、错误提示 |

原则：**能用 textContent 的地方就不用 innerHTML。**

**⑥ 往页面上放东西的三个动作**

| 动作 | 写法 | 比喻 |
|---|---|---|
| 新建元素 | `document.createElement("div")` | 拿一张空白便利贴 |
| 写上文字 | `div.textContent = 文字` | 在便利贴上写字 |
| 放进页面 | `messageBox.appendChild(div)` | 贴到留言墙上 |

**⑦ fetch 与 httpx 对照**

| 要做的事 | Python（ask_llm） | JS |
|---|---|---|
| 发 POST | `httpx.post(URL, headers=..., json=payload)` | `await fetch(URL, 选项)` |
| 发送的数据 | `json=payload`（自动转 JSON） | `body: JSON.stringify(数据)`（自己转） |
| 声明 JSON | httpx 自动加 | `headers: { "Content-Type": "application/json" }`（自己写） |
| 状态码 | `response.status_code` | `res.status` / `res.ok` |
| 读 JSON | `response.json()` | `await res.json()` 或先 `res.text()` 再 `JSON.parse` |

要等两次：第一次 `await fetch` 等盒子拿回来，第二次 `await res.text()` 等打开盒子。

**⑧ finally：离开房间关灯**

成功、HTTP 错误、网络错误，三条路最后都要删掉"思考中…"、恢复按钮。写在 try 末尾的话，出错时就执行不到，按钮会一直是灰的。**try 里的 return 也拦不住 finally。**

### 4.6 完整代码：`rag_app/static/index.html`

第 1~4 步由自己写；第 5 步说写不出，`addMessage` 和修改后的 `handleSubmit` 由讲解方直接给出；第 6、7 步为了当天提交，整份文件由讲解方给出，第二天再逐段讲解。每一段都标了【第 X 步】。

```html
<!DOCTYPE html>
<!-- 声明：这是一个现代 HTML 网页 -->
<html lang="zh-CN">
<head>
    <!-- 【第 1 步】字符编码 UTF-8，避免中文乱码 -->
    <meta charset="utf-8">
    <!-- 【第 1 步】网页标题，显示在浏览器标签页上 -->
    <title>Hello-Agents RAG 问答</title>

    <!-- 【第 6 步】从 CDN 引入两个库（锁定大版本号）；必须在我们自己的 script 之前加载 -->
    <!-- marked：把 Markdown 转成 HTML（排版员） -->
    <script src="https://cdn.jsdelivr.net/npm/marked@15/marked.min.js"></script>
    <!-- DOMPurify：清洗 HTML，删掉脚本等危险内容（安检员） -->
    <script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>

    <!-- 【第 7 步】最基本的样式：区分不同类型的消息（CSS 的注释写法是 /* */） -->
    <style>
        body { max-width: 800px; margin: 20px auto; font-family: sans-serif; }   /* 内容居中，限制最大宽度 */
        .msg { margin: 8px 0; padding: 8px 12px; border-radius: 6px; }          /* 每条消息的间距和圆角 */
        .user { background: #e8f0fe; }                                           /* 用户的问题：浅蓝背景 */
        .assistant { background: #f5f5f5; }                                      /* 回答：浅灰背景 */
        .assistant p { margin: 4px 0; }                                          /* 回答里的段落间距小一点 */
        .source { color: #555; font-size: 14px; padding: 2px 12px; margin: 0; }  /* 出处：灰色小字 */
        .error { background: #fdecea; color: #b3261e; }                          /* 错误提示：红色 */
        #ask-form { display: flex; gap: 8px; margin-top: 12px; }                 /* 输入框和按钮排成一行 */
        #question { flex: 1; padding: 6px; }                                     /* 输入框占满剩余宽度 */
    </style>
</head>
<body>
    <!-- 【第 1 步】页面大标题 -->
    <h1>Hello-Agents RAG 问答</h1>

    <!-- 【第 2 步】消息区：所有问答都追加到这里，一开始是空的 -->
    <div id="message"></div>

    <!-- 【第 2 步】表单：输入框 + 发送按钮 -->
    <form id="ask-form">
        <!-- 输入框：placeholder 是灰色提示文字；maxlength 和后端的 max_length=500 保持一致 -->
        <input id="question" placeholder="请输入关于 Hello-Agents 的问题" maxlength="500">
        <!-- 发送按钮：type="submit" 表示点击时提交表单；id 用于第 7 步禁用按钮 -->
        <button id="send-btn" type="submit">发送</button>
    </form>

    <script>
        // ===== 【第 3 步】按 id 取出要用到的页面元素 =====
        const input = document.getElementById("question");       // 输入框
        const form = document.getElementById("ask-form");        // 表单
        const button = document.getElementById("send-btn");      // 【第 7 步】发送按钮，等待时禁用
        const messageBox = document.getElementById("message");   // 【第 5 步】消息区

        // ===== 【第 5 步】辅助函数：在消息区追加一条纯文本消息 =====
        // text：要显示的文字；className：样式类名（user / source / error / assistant）
        function addMessage(text, className) {
            const div = document.createElement("div");   // 新建一个空 div（空白便利贴）
            div.className = "msg " + className;          // 【第 7 步】设置样式类名，例如 "msg user"
            div.textContent = text;                      // 写入文字：textContent 原样显示，不执行 HTML，安全
            messageBox.appendChild(div);                 // 放进消息区的最后面（贴上留言墙）
            return div;                                  // 返回这个 div，方便之后删除（如“思考中…”）
        }

        // ===== 【第 6 步】辅助函数：显示需要 Markdown 排版的回答 =====
        // 和 addMessage 只有一行不同：用 innerHTML + 排版 + 安检，代替 textContent
        function addAnswer(markdown) {
            const div = document.createElement("div");   // 新建一个空 div
            div.className = "msg assistant";             // 回答的样式
            // 先 marked.parse 排版（Markdown → HTML），再 DOMPurify.sanitize 安检；安检必须是最后一道
            div.innerHTML = DOMPurify.sanitize(marked.parse(markdown));
            messageBox.appendChild(div);                 // 放进消息区
            return div;
        }

        // ===== 【第 7 步】辅助函数：把出错的响应变成一句人能看懂的话 =====
        // status：状态码；data：解析出的 JSON（不是 JSON 时为 null）；text：响应的原始文字
        function formatError(status, data, text) {
            // 422（参数校验失败）：detail 是数组，每一项的 msg 是错误说明
            if (data && Array.isArray(data.detail)) {
                const msgs = data.detail.map(e => e.msg).join("；");   // 取出每一项的 msg，用分号连起来
                return `请求参数有误（${status}）：${msgs}`;
            }
            // 502 等（我们自己 raise 的 HTTPException）：detail 是字符串
            if (data && typeof data.detail === "string") {
                return `服务出错（${status}）：${data.detail}`;
            }
            // 500 等：响应不是 JSON（如纯文本 Internal Server Error），显示原文的前 200 个字
            return `服务出错（${status}）：${text.slice(0, 200)}`;
        }

        // ===== 【第 3~7 步】表单提交时执行：发送问题，显示回答、出处或错误 =====
        async function handleSubmit(event) {
            event.preventDefault();                        // 【第 3 步】拦住 form 的老习惯：不刷新页面

            const question = input.value.trim();           // 【第 5 步】先把问题存起来；trim() 去掉首尾空格
            if (question === "") {                         // 【第 7 步】空问题不发送，直接结束
                return;
            }

            addMessage("你：" + question, "user");          // 【第 5 步】立刻显示用户的问题
            input.value = "";                              // 【第 5 步】清空输入框

            // 【第 7 步】等待状态：显示“思考中…”，禁用按钮防止重复提交
            const thinking = addMessage("思考中…", "assistant");
            button.disabled = true;

            try {
                // 【第 4 步】把问题发给 /ask
                const res = await fetch("/ask", {
                    method: "POST",                                   // 请求方法
                    headers: { "Content-Type": "application/json" },  // 告诉服务器：body 是 JSON
                    body: JSON.stringify({ question: question }),     // 把 {question: 问题} 转成 JSON 字符串
                });

                // 【第 7 步】先把响应当成普通文字读出来，再尝试按 JSON 解析（500 返回的是纯文本，不是 JSON）
                const text = await res.text();
                let data = null;                           // 解析失败时保持 null
                try {
                    data = JSON.parse(text);               // 相当于 Python 的 json.loads
                } catch {
                    data = null;                           // 不是 JSON，什么都不做
                }

                // 【第 7 步】先看盒子上的标签：状态码不是 2xx，就显示错误并结束
                if (!res.ok) {
                    addMessage(formatError(res.status, data, text), "error");
                    return;                                // 结束函数；下面的 finally 仍然会执行
                }

                // 【第 6 步】显示回答：Markdown 排版 + 安检
                addAnswer(data.answer);

                // 【第 7 步】回答里引用了不存在的资料编号时，给出提示
                if (data.bad_citations.length > 0) {
                    addMessage("⚠ 回答中有不存在的引用编号：" + data.bad_citations.join(", "), "error");
                }

                // 【第 5 步】逐条显示出处：[编号] 文件 › 标题（分数保留 4 位小数）
                let n = 1;                                 // 编号从 1 开始；会变化，所以用 let
                for (const s of data.sources) {
                    addMessage(`[${n}] ${s.source} › ${s.heading}（${s.score.toFixed(4)}）`, "source");
                    n++;                                   // 编号加 1
                }
            } catch (err) {
                // 【第 7 步】网络不通（服务没启动、断网）时 fetch 会抛错，进到这里
                console.error(err);                        // 在控制台打印完整的错误，方便调试
                addMessage("请求失败（服务可能没有启动，或网络断开）：" + err.message, "error");
            } finally {
                // 【第 7 步】无论成功、HTTP 错误还是网络错误，最后都要执行（离开房间关灯）
                thinking.remove();                         // 删掉“思考中…”
                button.disabled = false;                   // 恢复按钮
                input.focus();                             // 光标回到输入框，方便继续提问
            }
        }

        // 【第 3 步】表单被提交时，执行 handleSubmit（函数名后面不加括号）
        form.addEventListener("submit", handleSubmit);
    </script>
</body>
</html>
```

> **待改**：检验题讲解时发现，catch 会接住 try 里**所有**的错误（不只是网络错误），上面这句"服务可能没有启动"在 marked 没加载、formatError 出错时会误导用户，应改成中性说法，例如 `addMessage("请求失败：" + err.message, "error");`。提交 `58d6bc7 fix(week8): neutral error message in catch` 实际**只改了文件末尾的换行**，提示文字还没有改（见错误 29），仓库里的代码和上面完全一致。

### 4.7 运行结果

**第 3 步之前**（没有 JS，按回车）：

```
INFO:     127.0.0.1:54381 - "GET / HTTP/1.1" 200 OK
INFO:     127.0.0.1:56189 - "GET / HTTP/1.1" 200 OK
INFO:     127.0.0.1:2106 - "GET / HTTP/1.1" 200 OK
……
```

每按一次回车多一行 `GET /`：浏览器又去迎宾台要了一份新菜单。冒号后面的数字是**浏览器那一端**的临时端口，每次连接都不一样。

**第 3 步之后**：控制台打印出输入的 `sin`，输入框内容保留，终端不再新增 `GET /`。

**第 4 步**：控制台打印

```
200
{answer: 'ReAct 智能体设置最大步数（`max_steps`）是为了防止无限循环 [3]。\n\n此外…',
 bad_citations: [],
 sources: [{source: 'main/第四章 智能体经典范式构建.md', heading: '4.2.3 ReAct 智能体的编码实现', score: 0.9804449081420898}, …],
 usage: {prompt_tokens: 708, completion_tokens: 64, prompt_cache_hit_tokens: 512, prompt_cache_miss_tokens: 196, total_tokens: 772}}
```

数字和 §2 用 /docs 测试时完全一样。`[[Prototype]]` 是 JS 内部的东西，可以忽略。

**第 5 步**：页面显示问答和 3 条出处，但回答里的 `**或达到最大步数限制**` 和反引号**原样显示**，`\n\n` 的分段也挤成了一段（HTML 把换行当空格）→ 引出第 6 步。

**第 6、7 步**：

| # | 测试 | 结果 |
|---|---|---|
| 1 | 正常提问 | `max_steps` 变成代码字体，"或达到最大步数限制"变成粗体，回答恢复分段；出处为灰色小字 |
| 2 | 空问题直接回车 | 什么都不发生（前端拦下） |
| 3 | 停掉 uvicorn 后提问 | 红色提示"请求失败……Failed to fetch"，按钮恢复 |
| 4 | `$env:RAG_LLM_MODEL="no-such-model"` 启动后提问 | 红色"服务出错（502）……"，按钮恢复 |
| 5 | 控制台直接 fetch 空问题 | detail 数组里是 `string_too_short` |

控制台里还有 8 条黄色警告 `Tracking Prevention blocked access to storage for <URL>.`：这是 Edge 的跟踪防护，不让 CDN（jsdelivr）在浏览器里读写存储。它是警告不是错误，库已正常加载。以后把两个库下载到 static/ 自己提供就能消除。

### 4.8 检验题讲解（第 6、7 步）

**题 1：把 marked 的 `<script src>` 挪到自己的 script 下面，会怎样？**

script 里有两种代码：**顶层代码读到就执行**，**函数里的代码被调用时才执行**。marked 只在 addAnswer 里用，用户几秒后提问时它早就加载好了，所以**一般不会出错**。只有两种情况会报 `ReferenceError: marked is not defined`：顶层代码直接用了 marked（和第 7 周错误 12 同一个道理）；网很慢、CDN 没下载完用户就提问了。后一种情况错误在 try 里，被 catch 接住，页面却显示"服务可能没有启动"——**catch 会接住 try 里所有的错误**。库放在 head 里，是为了不去赌"用户提问时它应该已经下载完了"。

**题 2：addAnswer 里写成 `textContent = DOMPurify.sanitize(marked.parse(md))`？**

页面上会把 `<p>…<strong>…</strong></p>` 这些标签**作为文字原样显示**。安全，但排版完全没生效。比喻：排好版、安检过了，最后把**排版说明书**本身贴在了墙上。

**题 3：后端返回 502 时执行了哪些步骤？**

①preventDefault ②trim ③显示问题 ④思考中、禁用按钮 ⑤fetch（拿回了盒子）⑥读文字、解析 JSON ⑦`!res.ok` → 显示错误 → return → ⑩finally。**跳过 ⑧（显示回答）和 ⑨（catch）**。502 不进 catch；return 之后 finally 照样执行。

**题 4：前端拦下了空问题，为什么后端的 `min_length=1` 不能删？**

请求不一定来自你的页面：控制台 fetch（测试 5 就是这样绕过的）、/docs、Python 脚本都能直接调用接口。**前端校验是为了体验，后端校验才是为了安全；永远不要相信客户端发来的数据。** 比喻：导购在门口帮顾客少走弯路，金库门上的锁才真正挡人。

**题 5：formatError 里去掉 `data &&` 会怎样？**

500 时 `data = null`，`null.detail` 报 `TypeError: Cannot read properties of null (reading 'detail')`，被 catch 接住，页面显示"服务可能没有启动"，**真实的 500 被掩盖了**。`&&` 短路：左边是 null 就直接判假，右边不执行，和第 7 周 `r is not None and r <= cut` 一样。

| 题 | 背后的道理 |
|---|---|
| 1 | 顶层代码立刻执行，函数里的代码调用时才执行 |
| 2 | textContent 只显示文字，innerHTML 才按 HTML 显示 |
| 3 | 拿回了响应就不进 catch；return 之后 finally 仍然执行 |
| 4 | 前端校验为体验，后端校验为安全 |
| 5 | 短路求值防止对 null 取属性；catch 接住 try 里所有错误 |

---

## 第五章 §4 Docker 打包

### 5.1 复习：Docker 是什么

| 概念 | 比喻 |
|---|---|
| 要解决的问题 | 在家能做的菜，到别人家就做不出来：没有这个调料，锅也不一样 |
| Dockerfile | 菜谱：用什么 Python、装哪些库、复制哪些文件、怎么启动 |
| 镜像（`docker build`） | 按菜谱做好的冷冻便当，所有东西都封在里面 |
| 容器（`docker run`） | 加热好、正在吃的那一份 |
| 端口映射 `-p 8000:8000` | 容器是封闭的小房间，在墙上开一扇窗 |
| `WORKDIR` | 进入小房间后"站在哪里" |

### 5.2 这次和第 3 周有什么不一样

| | 第 3 周 echo 服务 | 这次 rag_app |
|---|---|---|
| 依赖 | fastapi、uvicorn，几十 MB | 还有 sentence-transformers、torch、chromadb……torch 一个就可能好几 GB |
| 模型 | 没有 | bge-small（约 100 MB）、bge-reranker（约 1.1 GB） |
| 数据 | 没有 | chroma_db 向量库（2505 块） |
| 密钥 | 没有 | DeepSeek API Key |
| 启动 | 一瞬间 | 加载两个模型和 BM25，十几秒 |

### 5.3 要解决的 6 个问题

| # | 问题 | 解决办法 |
|---|---|---|
| ① | 依赖：`pip freeze` 的 requirements.txt 列了所有包，可能有只能在 Windows 装的包，也有很多用不到的 | 给 rag_app 单独写**精简版** requirements，版本和本机一致 |
| ② | Linux 上 `pip install torch` 默认装 GPU 版，多下载好几 GB 的 CUDA 库 | 先从 PyTorch 的 CPU 专用地址单独装 torch |
| ③ | 模型在本机 HF 缓存里，容器看不到 | **build 时下载进镜像**，运行时离线读取 |
| ④ | chroma_db 在本机；容器里重建需要语料（许可不允许分发），而且要好几分钟 | 直接 COPY 建好的 chroma_db |
| ⑤ | **API Key 绝不能进镜像** | `.dockerignore` 排除 `.env`；运行时 `--env-file .env` 从外面传入 |
| ⑥ | 容器里 `127.0.0.1` 只接待容器自己 | uvicorn 加 `--host 0.0.0.0`，配合 `-p 8000:8000` |

**模型放哪里，其实有三种做法**：

| 做法 | 什么时候获取模型 | 问题 |
|---|---|---|
| 容器每次启动时下载 | 每次 `docker run` | 每次都要下载 1 GB 多，又慢又依赖网络 |
| 运行时挂载（`-v`） | 不下载，用本机已有的缓存 | 只有本机有缓存，换到服务器还得先准备模型 |
| **build 时下载进镜像** | build 时一次 | 镜像大一些，但**到哪里都能直接跑** |

选第三种的主要原因不是"快"，而是**镜像可以独立运行，不依赖目标机器上有什么**。便当里要把菜都装好。

### 5.4 层缓存：慢的、不常变的放上面

Dockerfile 每条指令生成一层。重新 build 时，某一层的内容没变就复用；**一旦某一层变了，它下面的所有层都要重做**。

```
1. 基础镜像                ← 几乎不变
2. 装 CPU 版 torch         ← 几乎不变，很慢
3. 装其他依赖              ← 偶尔变，慢
4. 下载模型                ← 几乎不变，很慢
5. 复制 chroma_db          ← 偶尔变
6. 复制 rag_app 代码       ← 经常变，很快
7. 启动命令
```

> **比喻**：叠积木时抽掉中间一块，上面的都要重新摆。最常换的那块放最上面。

第 3 周的 Dockerfile 已经用了这个思路：先 COPY requirements.txt 和 pip install，最后才 COPY 代码。

### 5.5 检验题与批改

| 题 | 我的回答 | 批改 |
|---|---|---|
| 1. 不写 .dockerignore 直接 `COPY . .` 有什么问题？ | 会把 API Key 发过去导致密钥泄露，而且可能还有其他信息 | ✅ 对了一部分。还有：.venv 几个 GB 且是 Windows 版、data/ 语料违反许可、.git 历史、week1~7 练习代码 |
| 2. 先 `COPY .env` 再 `RUN rm .env` 安全吗？ | 不安全，但我不清楚原因 | 方向对。镜像是一层层叠起来的，rm 只是在新的一层记一笔"看不到了"，**前一层里 .env 原封不动**，`docker save` 解开就能找到。比喻：笔记本第 3 页写"前面的作废"，第 2 页还在 |
| 3. 日志显示启动完成，浏览器却无法访问，最可能是什么原因？ | 是使用别的电脑的浏览器访问的，容器没监听 0.0.0.0 | 对一半。"别的电脑"不是关键，**用自己电脑访问也一样进不去**，因为请求是从容器外面通过端口映射进来的。两个原因：没加 `--host 0.0.0.0`；忘了 `-p 8000:8000` |
| 4. "先复制代码，再装依赖、下载模型"，改 index.html 一个字后重新 build 会怎样？ | 不会有任何改变，因为先 copy 里面的代码还是改动之前的 | ❌ **理解反了**。每次 build，COPY 都读取**最新的文件**；层缓存管的是"这一步要不要重做"。COPY 那层变了 → 下面装 torch、装依赖、下载模型**全部被迫重做**，改一个字要等十几二十分钟 |
| 5. 为什么模型 build 时下载进镜像，而不是运行时挂载？ | 那样启动前还要先下载一遍很浪费时间 | 对一半。那是"每次启动时下载"的问题；挂载不用下载，但**只有本机有模型**。选 build 时下载是为了镜像独立可运行 |

### 5.6 动手前确认：依赖、Python 版本、Docker 状态

**① rag_app 用到了哪些库**：在 PyCharm 里 `Ctrl+Shift+F` 搜索 `import`，只看容器里会运行的 5 个文件：

| 文件 | Python 自带 | 第三方库 | 项目内部 |
|---|---|---|---|
| config.py | os、pathlib | | |
| api.py | contextlib、pathlib | fastapi、pydantic、httpx | rag_app.retriever、rag_app.rag |
| llm.py | os、time | httpx、dotenv | rag_app.config |
| rag.py | re | | rag_app.llm |
| retriever.py | re | chromadb、jieba、rank_bm25、sentence_transformers | rag_app.config |

- 没有从 week 文件夹导入；只有 cli.py 依赖 `common.cost_tracker`，但容器不运行 cli.py
- **只看 import 会漏掉 uvicorn**：它是"启动器"，是 uvicorn 去运行 api.py，没有人 import 它
- 两个**安装名和 import 名不一样**：`dotenv` → `python-dotenv`，`rank_bm25` → `rank-bm25`

**② Python 3.14.6**：基础镜像用 `python:3.14-slim`。3.14 比较新，如果某个库没有 Linux 版安装包，就换成 `python:3.12-slim`。

**③ Docker 没启动**：

```
PS> docker ps
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine; check if the path is correct and if the daemon is running: open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

`docker --version` 能显示版本，只说明命令行工具在；这个报错是找不到 Docker 引擎。打开 Docker Desktop，等左下角显示 Engine running 再试。

**④ 版本号**（`pip show` 一次查多个）：

| 库 | 版本 |
|---|---|
| fastapi | 0.141.1 |
| uvicorn | 0.52.4 |
| pydantic | 2.13.5 |
| httpx | 0.28.1 |
| python-dotenv | 1.2.3 |
| chromadb | 1.5.9 |
| jieba | 0.42.1 |
| rank-bm25 | 0.2.2 |
| sentence-transformers | 6.2.0 |
| torch | 2.14.1（单独写在 Dockerfile 里） |

版本必须和本机一致，尤其是 chromadb：不同版本的存储格式可能不兼容，容器可能读不了复制进去的 chroma_db。

### 5.7 差点覆盖第 3 周的 Dockerfile

在根目录新建 Dockerfile 时 PyCharm 提示"名称为 'Dockerfile' 的文件已存在"。打开一看是第 3 周的（`COPY week3 ./week3`、`CMD ["uvicorn", "week3.main:app", …]`），根目录的 .dockerignore 也是第 3 周的。于是换位置：

| 文件 | 位置 |
|---|---|
| Dockerfile | `rag_app/Dockerfile`，build 时用 `-f` 指定 |
| 排除清单 | `rag_app/Dockerfile.dockerignore`：和 Dockerfile 放在一起、名字是"Dockerfile 文件名 + .dockerignore"，**只对这一个 Dockerfile 生效** |

- 如果把 `week*/` 写进根目录的 .dockerignore，第 3 周的 build 就会坏掉
- 用了 `Dockerfile.dockerignore`，Docker 就**完全不读**根目录那份（是替换，不是合并），所以它必须自己写全，第一条就是 `.env`
- Dockerfile 里的 `COPY rag_app/...` 路径是相对于 **build 范围**（命令最后那个点，项目根目录），不是相对于 Dockerfile 所在的位置

### 5.8 四个文件

**`rag_app/requirements.txt`**（在 PyCharm 里手动输入，不要用 PowerShell 的 `>` 生成，否则是 UTF-16 编码）

```
# rag_app 在 Docker 里运行所需的第三方库
# 版本号和本机一致（pip show 查到的），尤其是 chromadb，版本不同可能读不了 chroma_db
# torch 不写在这里：Dockerfile 里单独安装 CPU 版

# Web 服务：FastAPI 框架、启动器 uvicorn、数据校验 pydantic
fastapi==0.141.1
uvicorn==0.52.4
pydantic==2.13.5

# 调用 DeepSeek：HTTP 客户端、从 .env 读取环境变量
httpx==0.28.1
python-dotenv==1.2.3

# 检索：向量库、中文分词、BM25、向量模型和重排模型
chromadb==1.5.9
jieba==0.42.1
rank-bm25==0.2.2
sentence-transformers==6.2.0
```

**`rag_app/download_models.py`**

```python
"""Docker build 时运行一次：下载向量模型和重排模型，存进镜像里的 HuggingFace 缓存。

运行方式（写在 Dockerfile 里）：HF_HUB_OFFLINE=0 python -m rag_app.download_models
命令前面的 HF_HUB_OFFLINE=0 允许联网；config.py 用的是 setdefault，看到已经有值就不会改成 1
"""
# 必须第一个导入：config.py 负责设置 HF 镜像地址（hf-mirror.com），并提供两个模型的名字
from rag_app import config

# 必须在 config 之后导入：HF 的环境变量要在 sentence_transformers 被导入之前设置好
from sentence_transformers import SentenceTransformer, CrossEncoder

print(f"开始下载向量模型：{config.EMBED_MODEL}")
SentenceTransformer(config.EMBED_MODEL)          # 创建模型时，本地没有就自动下载到缓存

print(f"开始下载重排模型：{config.RERANK_MODEL}")
CrossEncoder(config.RERANK_MODEL)                # 同上；运行时 retriever.py 会从缓存里读取

print("模型下载完成")
```

**`rag_app/Dockerfile`**（Dockerfile 的注释只能单独占一行，不能写在指令后面）

```dockerfile
# 使用方式（在项目根目录执行）：docker build -f rag_app/Dockerfile -t rag-app .

# ① 基础镜像：Python 3.14 精简版，和本机 Python 版本一致
FROM python:3.14-slim

# ② 容器里的工作目录；config.py 的 ROOT = Path(__file__).parent.parent 会自动变成 /app
WORKDIR /app

# ③ 让 print 和日志立刻输出，docker logs 才能及时看到
ENV PYTHONUNBUFFERED=1

# ④ 单独安装 CPU 版 torch：默认的 GPU 版会多下载好几 GB 用不到的 CUDA 库；最慢、几乎不变，放最前面
RUN pip install --no-cache-dir torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu

# ⑤⑥ 先只复制依赖清单，再安装：requirements.txt 不变，改代码后重新 build 不会重装依赖
COPY rag_app/requirements.txt rag_app/requirements.txt
RUN pip install --no-cache-dir -r rag_app/requirements.txt

# ⑦ 只复制下载模型需要的 3 个文件：改 api.py、index.html 时，第 ⑧ 步不会重做
#    复制多个文件时，最后一项是目标目录，必须以 / 结尾
COPY rag_app/__init__.py rag_app/config.py rag_app/download_models.py rag_app/

# ⑧ 联网下载两个模型存进镜像；HF_HUB_OFFLINE=0 只对这一条命令有效
RUN HF_HUB_OFFLINE=0 python -m rag_app.download_models

# ⑨ 复制本机建好的向量库（2505 块）
COPY chroma_db chroma_db

# ⑩ 最后复制全部代码：最常改，放在最下面
COPY rag_app rag_app

# ⑪ 说明容器使用 8000 端口（真正开窗靠 docker run 的 -p）
EXPOSE 8000

# ⑫ 容器启动时执行；--host 0.0.0.0：接受来自容器外面的请求
CMD ["uvicorn", "rag_app.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

（仓库里的版本注释更详细，这里为了篇幅合并了几行。）

| 指令 | 作用 | 比喻 |
|---|---|---|
| `FROM` | 从哪个基础镜像开始 | 用哪口锅 |
| `WORKDIR` | 工作目录 | 在哪张台子上做 |
| `ENV` | 环境变量，运行时也有效 | 贴在厨房墙上的提示 |
| `COPY` | 从电脑复制进镜像 | 把食材搬进厨房 |
| `RUN` | **build 时**执行命令，结果存进镜像 | 做菜的一个步骤 |
| `EXPOSE` | 说明使用的端口（只是说明） | 菜单上写着"窗口在 8000 号" |
| `CMD` | **每次 docker run 时**执行 | 加热便当的方法 |

**`rag_app/Dockerfile.dockerignore`**

```
# 只对 rag_app/Dockerfile 生效；用了它，根目录的 .dockerignore（第 3 周的）就不会再被读取
# 注释必须单独占一行

# 密钥：绝不能进入镜像，运行时用 docker run --env-file .env 从外面传入
.env

# 虚拟环境：几个 GB，而且是 Windows 版的，Linux 容器里用不了
.venv/

# Git 历史和 PyCharm 配置
.git/
.idea/

# Hello-Agents 语料：许可不允许公开分发；容器直接用 chroma_db
data/

# 第 1~7 周的练习代码，以及 cli.py 用到的 common 文件夹
week*/
common/

# Python 缓存文件（任意层级）
**/__pycache__/
**/*.pyc
```

### 5.9 build、run 与验证

```powershell
# 在项目根目录：-f 指定 Dockerfile 位置，-t 给镜像起名，最后的点是 build 范围
docker build -f rag_app/Dockerfile -t rag-app .

# --rm 停止后自动删除容器；--env-file 把 Key 从外面传进去；-p 开窗；--name 起名
docker run --rm --env-file .env -p 8000:8000 --name rag-app rag-app
```

**启动日志**：

```
INFO:     Started server process [1]
INFO:     Waiting for application startup.
Could not reach the Hub (Cannot reach https://hf-mirror.com/api/models/BAAI/bge-small-zh-v1.5: offline mode is enabled. To disable it, please unset the `HF_HUB_OFFLINE` environment variable.). Using cached commit hash for 'BAAI/bge-small-zh-v1.5'.
Loading weights: 100%|██████████| 71/71 [00:00<00:00, 49599.53it/s]
Could not reach the Hub (Cannot reach https://hf-mirror.com/api/models/BAAI/bge-reranker-base: offline mode is enabled. ...). Using cached commit hash for 'BAAI/bge-reranker-base'.
Loading weights: 100%|██████████| 201/201 [00:00<00:00, 3249.59it/s]
Building prefix dict from the default dictionary ...
Dumping model to file cache /tmp/jieba.cache
Loading model cost 0.470 seconds.
Prefix dict has been built successfully.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

| 日志 | 说明什么 |
|---|---|
| `offline mode is enabled … Using cached` | 运行时离线，**模型是从镜像里读的**，第 ⑧ 步生效 |
| `/tmp/jieba.cache` | 这是在 Linux 里（本机是 `C:\Users\…\Temp\`） |
| `Application startup complete` | lifespan 完成，chroma_db 也读到了 |
| `running on http://0.0.0.0:8000` | 监听所有网卡，外面能进来 |

当时以为程序"卡住了"，其实是**服务启动成功，正在等请求**，和本机运行 uvicorn 一样。浏览器要输入 `http://127.0.0.1:8000/`，**不能输入 `0.0.0.0`**：0.0.0.0 是服务器一侧"所有网卡都接待"的意思，不是能访问的地址。

**页面测试**：问"ReAct 智能体为什么要设置最大步数？"，3 条出处的文件、标题、分数（0.9804 / 0.9315 / 0.8858）和本机**完全一致**，说明模型、向量库、参数被完整地搬进了容器。回答措辞略有不同，是 DeepSeek 生成的正常波动。

```
PS> docker ps
CONTAINER ID   IMAGE     COMMAND                  CREATED         STATUS         PORTS                                         NAMES
0507b35b7726   rag-app   "uvicorn rag_app.api…"   4 minutes ago   Up 4 minutes   0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp   rag-app

PS> docker images rag-app
IMAGE            ID             DISK USAGE   CONTENT SIZE   EXTRA
rag-app:latest   5d6326c42adc       4.94GB         1.65GB    U
```

- CONTENT SIZE 1.65 GB：压缩后的大小，推送或下载时要传输的量
- DISK USAGE 4.94 GB：解压后在硬盘上的占用

**安全验证：镜像里有没有 .env**

```
PS> docker run --rm rag-app ls -a /app
.
..
chroma_db
rag_app
```

只有 `chroma_db` 和 `rag_app`，**没有 .env**，也没有 .venv、data、week*。镜像名后面写的命令会**替换掉 CMD**，这里没有启动 uvicorn，而是执行 `ls`，执行完就退出。

### 5.10 现在谁能访问？

| 范围 | 地址 | 条件 |
|---|---|---|
| 只有自己 | `http://127.0.0.1:8000/` | 已经可以 |
| 同一个 Wi-Fi | `http://局域网IP:8000/`（`ipconfig` 查 IPv4） | Windows 防火墙放行；校园网可能开了客户端隔离 |
| 任何人 | `http://服务器公网IP:8000/` | 部署到云服务器（至少 2 核 4 GB，安全组放行端口），并先做好防刷 |

**推送到 GitHub ≠ 能访问**：GitHub 上放的是菜谱（代码），餐厅只开在你家里。别人 clone 了也跑不起来：chroma_db、语料都不在仓库里，还需要自己的 Key。所以 README 要写清楚怎么准备。

---

## 第六章 §5 README：用 Claude Code 开 PR

### 6.1 为什么要把数据写进提示词

Claude Code 能看到仓库里的**代码**，但看不到评测数字、延迟实验结果，它们记录在对话和项目文档里。不告诉它的话，它要么写不出评测表，要么自己编数字。所以给它的提示词里写明了：

- 工作方式：新建分支 `docs/week8-readme`，开 PR，只改 README，不改代码；**所有数字照抄，不要编造**；代码里能查到的信息以代码为准；绝不写出 Key
- 内容：项目简介、Mermaid 架构图、技术选型与理由（包括"为什么没用 RRF"）、第 7 周评测表、第 8 周延迟表、API 用法、运行方法、已知局限

### 6.2 Claude Code 提出的 5 个问题和决定

| 问题 | 决定 |
|---|---|
| 截图链接是空的 | 自己截图上传到 `assets/chat-page.png` |
| 仓库里没有记录语料怎么下载 | 从过去的对话里找到了：克隆 `datawhalechina/hello-agents`（2026-10-14 版本），正文 `docs/chapterN/第N章*.md` → `main/`，扩展 `Extra-Chapter/Extra*.md` → `extra/`，附 LICENSE.txt、SOURCE.md，不含英文版、代码目录和图片 |
| `.env.example` 写的是 `API_KEY`，llm.py 读的是 `DEEPSEEK_API_KEY` | **真正的 bug，必须修**：新用户照抄就读到空值，调用 DeepSeek 返回 401，每个问题都报 502。改成 `DEEPSEEK_API_KEY`，并提醒 .env 里的值不要加引号 |
| `/health` 的 loading 实际上看不到 | README 只写 `{"status": "ok"}`（见 3.5） |
| 本地安装方式 | 先装 `torch==2.14.1`（Windows 直接装就是 CPU 版；Linux 加 `--index-url https://download.pytorch.org/whl/cpu`），再装 `rag_app/requirements.txt`；说明根目录 requirements.txt 是第 1~7 周的完整依赖 |

追加的一个问题：第 1 周的 `week1/demo_env.py` 读的还是 `API_KEY`。决定：**练习代码不改**，在 `.env.example` 里加一行注释说明。另外 `.env.example` 前三行 `APP_NAME`、`MODEL_NAME`、`MAX_TURNS` 也是第 1 周 Config 类留下的，rag_app 不读。

### 6.3 分支与 PR

| | 比喻 | 作用 |
|---|---|---|
| main | 论文正式版 | 别人打开 GitHub 默认看到的版本 |
| docs/week8-readme | 复印出来的草稿副本 | Claude Code 在上面改，改坏了也不影响正式版 |
| PR #2 | 交给导师的"请审阅并合并"申请 | 检查没问题后合并，草稿上的改动才写进正式版 |

所以 assets 文件夹在合并前**只存在于草稿上**，main 里看不到。截图也要传到草稿分支上，和新 README 在同一个 PR 里一起审阅、一起合并。

### 6.4 在 GitHub 网页上传、替换截图

1. 左上角分支下拉菜单切到 `docs/week8-readme`，进入 `assets`（里面的 `.gitkeep` 是占位文件：Git 不记录空文件夹）
2. Add file → Upload files，拖入 `chat-page.png`
3. 选 **Commit directly to the docs/week8-readme branch**，不要选 Create a new branch

第一次传错了图（传成了 Claude Code 那段说明文字的截图）。因为文件名相同，直接**上传同名文件就会覆盖**，不用先删除。传错的图里没有 Key 或隐私信息，留在提交历史里也没关系；如果有，删除文件并不能从 Git 历史里抹掉。

GitHub 的提示 "ProTip! Great commit summaries contain fewer than 50 characters"：提交说明第一行最好少于 50 个字符，太长会在列表里被截断。只是建议，不影响提交。

### 6.5 合并

- 合并前在 **Files changed** 里逐个检查：README 的数字、命令、有没有 Key；.env.example 只有占位值；截图正确
- Confirm merge 页面的 "This commit will be authored by 邮箱"：公开仓库的提交邮箱**任何人都能看到**。介意的话：Settings → Emails → Keep my email addresses private，本地用 `git config --global user.email` 改成 noreply 邮箱
- 合并后本地 `git checkout main`、`git pull`

合并后的 README 包含：截图、两张 Mermaid 图（请求数据流、模块依赖）、文件结构、技术选型表、test 集和 dev 集评测表、延迟 A~D 表、API 用法、运行方法。所有数字逐个核对过，和原始数据一致。

---

## 第七章 典型错误合集

> ⚠️ **本章所有标记 ❌ 的代码都是错误示范，请勿复制使用。**
> 按根因分类。标注"审查时发现"的是运行前看截图改掉的，写的是按代码推断的后果；有运行输出的照实收录。

### 根因一：引号——分不清"文字本身"和"代码"（本周最高频，出现 4 次）

> **规律**：加了引号就是文字本身，不加引号才是代码（变量、参数名、对象、函数调用）。第 7 周错误 11 是变量名多加了引号，本周正好反过来。

| 加引号 | 不加引号 |
|---|---|
| 固定的文字：路径 `"/"`、文件夹名 `"static"`、文件名 `"index.html"`、`"POST"` | 变量 `INDEX_HTML`、参数名 `include_in_schema`、`False`、对象 `{ … }`、函数调用 `JSON.stringify(…)` |

---

**错误 1：文件夹名和文件名没加引号**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
PATH = pathlib.Path(__file__).parent/static/index.html     # ← static、index 被当成变量名
```

审查时发现：`static`、`index.html` 下有红色波浪线。Python 会去找叫 `static` 的变量，`index.html` 被理解成"变量 index 的 html 属性"，运行报 `NameError`。

**✅ 正确写法**：

```python
INDEX_HTML = pathlib.Path(__file__).parent / "static" / "index.html"   # 文件夹名、文件名是固定文字，加引号
```

---

**错误 2：参数也被包进了路径字符串**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
@app.get("/,include_in_schema=False")      # ← 一整段都在同一对引号里
```

审查时发现：从 `/` 一直绿到 `False`（绿色 = 字符串）。路由的路径变成了 `/,include_in_schema=False` 这 26 个字符，访问 `/` 返回 404，参数也没有传进去。

**✅ 正确写法**：引号只包住路径，参数名在引号外面，和 `FastAPI(title="...", lifespan=lifespan)` 同一个格式。

```python
@app.get("/", include_in_schema=False)
```

---

**错误 3：fetch 的 headers 和 body 写成了字符串**

```js
// ❌❌❌ 错误示范，请勿复制 ❌❌❌
const res = await fetch("/ask", {method:"POST",headers:"\"Content-Type\": \"application/json\"",body:"JSON.stringify(...)"});
```

运行结果（控制台）：

```
Uncaught (in promise) TypeError: Failed to execute 'fetch' on 'Window': Failed to read the 'headers' property from 'RequestInit': The provided value is not of type '(record<ByteString, ByteString> or sequence<sequence<ByteString>>)'.
    at HTMLFormElement.handleSubmit ((索引):18:31)
```

**读报错**：`(in promise)` 表示错误发生在 async 函数里且没有被接住；`TypeError` 是类型不对；`Failed to read the 'headers' property … not of type 'record<…>'` 翻译成大白话：**headers 应该是一个对象，你给了一个字符串**。`\"` 是转义引号，说明这一整段都在外层引号里。

body 也有同样的问题：`"JSON.stringify(...)"` 加了引号，函数**不会执行**，发出去的是这串文字本身。

**✅ 正确写法**：headers 是对象里套对象（快递箱里装一个真的小盒子，不能画在纸上塞进去）；拆成多行更容易看清。

```js
const res = await fetch("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },   // 花括号：对象；键里有短横线要加引号
    body: JSON.stringify({ question: question }),      // 函数调用，不加引号
});
```

---

**错误 4：改成对象后残留了转义反斜杠**

```js
// ❌❌❌ 错误示范，请勿复制 ❌❌❌
headers: {\"Content-Type\": \"application/json\"},     // ← 字符串里的 \" 留在了代码里
```

审查时发现：红色波浪线，连带下面的 `});` 也标红。外层引号去掉以后，这些反斜杠就成了不认识的符号，语法错误。

### 根因二：用 Python 的习惯写 HTML

---

**错误 5：用冒号代替标签**

```html
<!-- ❌❌❌ 错误示范，请勿复制 ❌❌❌ -->
<head>:
    utf-8, HELLOW_AGENT RAG问答
<body>:
```

审查时发现：浏览器不知道哪个是编码、哪个是标题。HTML 没有冒号和缩进规则，每样东西都要用对应的标签包起来：编码是 `<meta charset="utf-8">`，标题是 `<title>…</title>`。

> HTML 和 Python 最不一样的地方：**Python 写错会报错停下，HTML 写错浏览器会尽量猜着显示。** 所以要靠 PyCharm 的波浪线和页面效果来检查。

---

**错误 6：标签没有关闭，结构嵌套错了**

```html
<!-- ❌❌❌ 错误示范，请勿复制 ❌❌❌ -->
<div id = "名字">
    <form>
        <input placeholser = "请输入一个id">
        <button type = "submit">          <!-- ← 没有文字，也没有 </button> -->
    </form>                               <!-- ← 红线：button 还开着 -->
</body>                                   <!-- ← 红线：div 一直没关 -->
```

审查时发现：`</form>` 和 `</body>` 下有红色波浪线。消息区 div 和表单应该是**并列**的（桌上并排放着的两样东西），空 div 开了就马上关；button 有内容（按钮上的文字），要像 h1 一样关闭。

**✅ 正确写法**：

```html
<div id="message"></div>
<form id="ask-form">
    <input id="question" placeholder="请输入关于 Hello-Agents 的问题">
    <button type="submit">发送</button>
</form>
```

---

**错误 7：属性名拼错，浏览器悄悄忽略**

`placeholser`（应为 `placeholder`，place + holder）。浏览器不报错，只是**忽略这个属性**，输入框里没有提示文字。黄色波浪线就是 PyCharm 在提醒"不认识这个属性"。

---

**错误 8：多了一个 `>`**

```html
<!-- ❌❌❌ 错误示范，请勿复制 ❌❌❌ -->
<div id = "message"></div>>
```

审查时发现：多出来的 `>` 不属于任何标签，会被当成普通文字显示在页面上。

### 根因三：把说明当成代码，概念混淆

---

**错误 9：照抄说明里的"名字"，id 和 placeholder 搞混**

```html
<!-- ❌❌❌ 错误示范，请勿复制 ❌❌❌ -->
<div id = "名字">                          <!-- ← 照抄了"这里填一个名字" -->
<input placeholser = "请输入一个id">       <!-- ← 用户看到的提示写成了 id -->
<form ask-form>                            <!-- ← 第二版：名字对了，但少了 id="..." -->
<input question placeholder = "…">
```

审查时发现：`id` 是给 JS 看的名字，`placeholder` 是给用户看的提示。只写名字不写 `id=`，浏览器把它当成一个叫 `ask-form` 的未知属性忽略掉。属性的格式永远是 `属性名="值"`：快递单上不能只写"张三"，要写"收件人：张三"。

---

**错误 10：照抄占位说明 `你的form变量`**

```js
// ❌❌❌ 错误示范，请勿复制 ❌❌❌
console.log(你的form变量);
```

运行结果（控制台）：

```
这里写你想打印的文字                                   (索引):13
Uncaught ReferenceError: 你的form变量 is not defined      (索引):16
    at (索引):16:13
```

**读报错**：`ReferenceError` 相当于 Python 的 `NameError`；`(索引):16` 是 index.html 第 16 行（浏览器把 index 翻译成了"索引"，点一下能跳过去）。JS 允许中文变量名，所以把它当成变量去找。第一行打印的"这里写你想打印的文字"也是照抄的占位说明。

**✅ 正确写法**：`console.log(form);`。修好后控制台打印出 `<form id="ask-form">…</form>`，还能展开看到 input 和 button。

> 这个坑是讲解方挖的：结构清单里用中文写占位说明，看起来像代码。之后改用【】标出需要替换的部分。

---

**错误 11：传了输入框元素本身，而不是它的文字**

```js
// ❌❌❌ 错误示范，请勿复制 ❌❌❌
body: JSON.stringify({question: input}),      // ← input 是元素，input.value 才是文字
```

审查时发现：`JSON.stringify` 遇到元素对象会把它转成 `{}`，发出去的是 `{"question": {}}`，后端要求字符串，返回 **422**。比喻：要寄的是信纸上写的内容，却把整个信封寄了出去。

**✅ 正确写法**：`body: JSON.stringify({ question: question })`，其中 `question` 是清空输入框**之前**存下来的 `input.value.trim()`。

### 根因四：残留旧代码、用错对象

---

**错误 12：自动补全从错误的模块导入**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
from ast import List          # ← 灰色：没有用到
```

审查时发现：§2 时写 `List[Source]`，PyCharm 自动补全从 `ast`（分析 Python 代码结构的模块）导入了 List，不是类型注解用的那个。后来改成 `list[Source]`，这行就残留了下来。**自动补全导入时要看一眼是从哪个模块导入的。**

---

**错误 13：`retrun` 拼错**

审查时发现：红色波浪线。Python 不认识这个词，整个文件 SyntaxError，**连 /ask 都跑不起来**。

---

**错误 14：返回了路径，而不是文件**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
@app.get("/")
def index():
    return PATH                 # ← FileResponse 导入了，却是灰色（没用到）
```

审查时发现：FastAPI 会把路径当成数据转成 JSON，浏览器里看到的是一行 `"D:\\PythonProjects\\...\\index.html"`，不是网页。比喻：迎宾台没把菜单递给顾客，而是告诉他"菜单在三号柜子里"。另外 `PATH` 和操作系统的环境变量同名，改成 `INDEX_HTML`。

**✅ 正确写法**：`return FileResponse(INDEX_HTML)`。**灰色的 import 往往就是线索。**

### 根因五：FastAPI 服务（§2）

| # | 错误 | 后果 | 改法 |
|---|---|---|---|
| 15 | `Field` 漏写 `min_length=1` | 空问题也能进入检索 | `Field(min_length=1, max_length=500)` |
| 16 | `List[Source]` 没导入 typing | NameError | Python 3.9+ 直接写 `list[Source]` |
| 17 | `bad_citations: int` | 实际返回的是列表，**响应校验失败，返回 500** | `list[int]` |
| 18 | `FastAPI()` 没传 `lifespan=lifespan` | lifespan 不执行，retriever 永远不会加载，AttributeError，返回 500 | `FastAPI(title=..., lifespan=lifespan)` |
| 19 | `answer = answer(question, retriever)` | 同名遮蔽引发 UnboundLocalError，而且 `question` 未定义 | `result = answer(req.question, retriever)` |
| 20 | except 分支只 print 不 raise；两种异常的说明写反；拼错 `HTTPExcception` | 出错时返回 None，响应校验失败 | 统一 `except (httpx.HTTPError, RuntimeError) as e: raise HTTPException(502, ...)` |
| 21 | /health 里单独一行 `hasattr(...)`，以及 `== True` | 算出结果什么都没做；`== True` 多余 | 只留 `if hasattr(app.state, "retriever"):` |
| 22 | 检验题：未捕获的异常返回什么 | 答成了 422 | **500**；422 是参数校验失败 |

### 根因六：环境与工具（不是代码错误，但卡住过）

| # | 现象 | 原因与处理 |
|---|---|---|
| 23 | `docker ps` 报 `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` | Docker Desktop 没启动。`docker --version` 能显示版本只说明命令行工具在 |
| 24 | 以为容器"卡在" `Uvicorn running on http://0.0.0.0:8000` | 服务已经启动成功，正在等请求。浏览器访问 `127.0.0.1:8000`，不是 `0.0.0.0` |
| 25 | 在根目录新建 Dockerfile 提示已存在 | 是第 3 周的，差点覆盖。改放 `rag_app/Dockerfile` + `Dockerfile.dockerignore` |
| 26 | GitHub 上传错了截图 | 同名文件直接上传覆盖；如果错图里有隐私，删除文件也抹不掉 Git 历史 |
| 27 | `Ctrl+Alt+L` 格式化没反应 | 快捷键疑似被其他软件（QQ、输入法等）占用；改用菜单"代码 → 重新格式化代码"，或选中后 Tab / Shift+Tab 手动缩进 |
| 28 | Docker 检验题 4：以为 COPY 复制的是"改动之前的代码" | 每次 build 都读最新文件；层缓存管的是"这一步要不要重做"，上面一层变了，下面全部重做 |
| 29 | 提交 `58d6bc7 fix(week8): neutral error message in catch`，但 `git show 58d6bc7` 显示只改了 1 行：文件末尾补了一个换行（`\ No newline at end of file` 消失），catch 的提示文字没变 | 很可能是改完没保存，或改在了别的地方。**提交前先看 `git diff`**，确认改动和提交说明一致；提交说明写的是"做了什么"，不是"打算做什么" |

### 本周反复出现的模式

| 模式 | 次数 | 对策 |
|---|---|---|
| 引号（字符串 vs 代码） | 4 | 看颜色：绿色范围就是字符串的范围 |
| 照抄说明 / 占位文字 | 3（"名字"、"这里写你想打印的文字"、"你的form变量"） | 看到中文词出现在代码里，先问自己"这是要我替换的吗" |
| 标签或括号没关 | 2 | 写开始标签时顺手写结束标签，再往中间填内容 |
| 灰色 = 没用到 | 2（`from ast import List`、`FileResponse`） | 灰色的 import 往往说明代码写错了地方 |
| 以为改了，其实没改 | 2（catch 提示文字、/health 多余的 hasattr 行） | 提交前 `git diff` 看一眼；改完在浏览器或终端里验证一次 |

### 讲解方的错误与更正

| 我当时说的 | 实际情况 |
|---|---|
| 按回车后 uvicorn 日志会显示 `GET /?` | 实际显示 `GET /`：查询字符串为空时日志省略问号，地址栏里才有 `?` |
| 结构清单里用中文写占位说明（"名字"、"这里写你想打印的文字"、"你的form变量"） | 看起来像代码，导致照抄（错误 9、10）。之后改用【】标出要替换的部分 |
| 第 3 小步举例用了函数名 `loadData` | 被照用了；含义是"加载数据"，和"处理提交"不符，改为 `handleSubmit` |
| 检验题"把 marked 挪到自己的 script 下面"预设了一定会报错 | 一般不会出错：marked 只在函数里用，调用时早已加载。只有顶层代码直接使用或 CDN 太慢时才报错 |
| index.html 里 catch 的提示写成"服务可能没有启动，或网络断开" | 太绝对：catch 会接住 try 里所有错误（marked 未加载、formatError 出错等），会误导用户。应改为中性提示（仓库里还没改，见错误 29） |
| §2 设计 /health 在模型未加载完时返回 loading | uvicorn 要等 lifespan 完成才接收请求，loading 分支永远执行不到 |

---

## 第八章 本周自检

- [x] 能说清为什么优化前要先分段计时，以及 pool 和 max_length 两个旋钮各自的代价
- [x] 能解释为什么选 D，以及为什么 test 集变差了也如实报告、不改选
- [x] 能说出 rag_app 的依赖方向，以及"慢的操作只做一次"是怎么实现的
- [x] 能解释 config.py 里 setdefault、`__file__`、`RAG_` 环境变量覆盖各自的用处
- [x] 能说清 /ask 为什么用 def 而不是 async def，以及 422 / 502 / 500 分别是谁的问题
- [x] 能说清同源策略和 CORS，以及为什么让 FastAPI 自己返回网页
- [x] 知道 HTML 的标签、属性规则，能分清 id、placeholder、class
- [x] 能解释 form 的默认行为，以及 preventDefault 的作用
- [x] 知道 fetch 拿回响应就不进 catch，必须检查 res.ok
- [x] 能说出 422、502、500 返回的 body 格式有什么不同，以及为什么先 res.text() 再 JSON.parse
- [x] 能解释 XSS，以及为什么要"先排版、再安检"
- [x] 能分清 innerHTML 和 textContent，知道什么时候用哪个
- [x] 能解释 finally 的作用，以及 return 之后 finally 仍然执行
- [x] 能说清前端校验和后端校验各自的作用
- [x] 能说清 API Key 为什么不能放在前端，以及公开部署前的防刷措施
- [x] 能说出这次 Docker 要解决的 6 个问题
- [x] 能解释为什么 `COPY .env` 再 `rm` 不安全（镜像分层）
- [x] 能解释层缓存，以及 Dockerfile 指令为什么要这样排序
- [x] 能分清 RUN 和 CMD
- [x] 知道容器里要监听 0.0.0.0，浏览器访问要用 127.0.0.1
- [x] 能用 `docker run --rm 镜像 ls -a /app` 验证镜像里有什么
- [x] 能解释分支和 PR，能在 GitHub 网页上传、覆盖文件并合并 PR

---

## 附录 A：本周速查

**前端：一次完整的请求**

```js
event.preventDefault();                                  // 拦住刷新
const res = await fetch("/ask", {                        // 发请求
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: question }),
});
const text = await res.text();                           // 先读文字
let data = null;
try { data = JSON.parse(text); } catch { data = null; }  // 再试着解析
if (!res.ok) { /* 显示 formatError(res.status, data, text) */ }
div.innerHTML = DOMPurify.sanitize(marked.parse(data.answer));   // 先排版、再安检
```

**错误 body**：422 → detail 是数组；502 → detail 是字符串；500 → 纯文本。

**Docker**

```powershell
docker build -f rag_app/Dockerfile -t rag-app .                       # 打包镜像
docker run --rm --env-file .env -p 8000:8000 --name rag-app rag-app   # 启动容器
docker ps                                                             # 正在运行的容器
docker images rag-app                                                 # 镜像大小
docker run --rm rag-app ls -a /app                                    # 查看镜像里有什么（替换 CMD）
```

**Git 分支与 PR**

```
Claude Code 新建分支并开 PR → 在 Files changed 里检查 → 网页上传补充文件（选 Commit directly to 分支）
→ Merge pull request → 本地 git checkout main、git pull
```

## 附录 B：本周新语法

| 语法 | 例子 | 说明 |
|---|---|---|
| HTML 标签 | `<p>文字</p>` | 开始标签 + 内容 + 结束标签 |
| HTML 属性 | `<input id="question" placeholder="…">` | `属性名="值"`；无内容的标签不用关闭 |
| HTML 注释 | `<!-- 注释 -->` | |
| `<script src="…">` | 引入 CDN 上的库 | 标签中间留空 |
| CSS 选择器 | `.user { … }`、`#ask-form { … }`、`.assistant p { … }` | `.` 选 class，`#` 选 id，空格表示"里面的" |
| CSS 注释 | `/* 注释 */` | |
| `const` / `let` | `let n = 1;` | 不变的用 const，会变的用 let |
| `function` | `function addMessage(text, className) { … }` | 花括号代替冒号和缩进 |
| `async` / `await` | `const res = await fetch(…)` | 和 Python 一样 |
| `document.getElementById` | `document.getElementById("question")` | 按 id 找元素，找不到返回 null |
| `addEventListener` | `form.addEventListener("submit", handleSubmit)` | 函数名后面不加括号 |
| `event.preventDefault()` | | 拦住默认行为 |
| `createElement` / `appendChild` / `remove` | `messageBox.appendChild(div)` | 新建、放进页面、删除元素 |
| `textContent` / `innerHTML` | `div.textContent = text` | 原样显示 / 按 HTML 显示 |
| `className` | `div.className = "msg user"` | 设置 class，空格分隔多个 |
| `disabled` / `focus()` | `button.disabled = true` | 禁用按钮 / 光标回到输入框 |
| JS 对象 | `{ method: "POST", "Content-Type": "…" }` | 键一般不加引号，带短横线的键要加 |
| `JSON.stringify` / `JSON.parse` | | 相当于 `json.dumps` / `json.loads` |
| 模板字符串 | `` `[${n}] ${s.source}` `` | 反引号，相当于 f-string |
| `for … of` | `for (const s of data.sources) { … }` | 相当于 `for s in …` |
| `n++` | | 相当于 `n += 1` |
| `toFixed(4)` | `s.score.toFixed(4)` | 相当于 `f"{x:.4f}"` |
| `trim()` / `slice(0, 200)` | | 相当于 `strip()` / `[:200]` |
| `===` / `!` / `&&` | `if (!res.ok)`、`data && …` | 严格相等 / not / and（短路） |
| `Array.isArray` / `typeof` | `typeof x === "string"` | 相当于 `isinstance` |
| `map` + 箭头函数 + `join` | `detail.map(e => e.msg).join("；")` | 相当于列表推导式 + `"；".join()` |
| `try { } catch (err) { } finally { }` | `catch { }` 可以不写参数 | 相当于 try / except / finally |
| `console.log` / `console.error` | | 打印到 F12 控制台 |
| `FileResponse` | `return FileResponse(INDEX_HTML)` | 把文件内容发给浏览器 |
| `include_in_schema=False` | `@app.get("/", include_in_schema=False)` | 不写进 /docs |
| Dockerfile 指令 | `FROM`、`WORKDIR`、`ENV`、`COPY`、`RUN`、`EXPOSE`、`CMD` | 见 5.8 |
| 单条命令的环境变量 | `RUN HF_HUB_OFFLINE=0 python -m …` | 只对这一条命令有效 |
| `Dockerfile.dockerignore` | | 只对同名 Dockerfile 生效，替换根目录的 .dockerignore |
| `docker run` 参数 | `--rm`、`--env-file`、`-p`、`--name` | 见附录 A |
| PowerShell 临时环境变量 | `$env:RAG_LLM_MODEL="no-such-model"` | 只对当前终端有效；`Remove-Item Env:RAG_LLM_MODEL` 删除 |

## 附录 C：提交记录

```
8a3a155  feat(week8): rerank latency experiment; deploy config pool10+len256 (test Hit@3 87.5->81.2, 10.4s->3.9s)
5c5eec0  feat(rag_app): standalone project - config, Retriever class with lazy loading, cli
7d72996  chore: convert requirements.txt to UTF-8, pin sentence-transformers, add requests; dedupe .gitignore   ← Claude Code，PR #1
5776b0e  docs: rewrite README with 16-week roadmap, directory guide, project 1 metrics and tech stack      ← Claude Code，PR #1
18b279e  Merge pull request #1 from Ruiwen-ZHANG/claude/update-readme-568lqg
93cec80  fix(rag_app): remove duplicate import in chunker
bf79b47  Merge branch 'main' of https://github.com/Ruiwen-ZHANG/ai-agent-learning
7f31fc7  feat(rag_app): FastAPI service with /health and /ask, lifespan model loading, 502 on LLM failure
2f0abe3  feat(week8): chat web page - GET / serves static/index.html; fetch /ask with markdown rendering, sources and error handling
e4733b2  feat(week8): Dockerize rag_app - CPU torch, models baked into image, chroma_db copied, key via --env-file
58d6bc7  fix(week8): neutral error message in catch - show err.message instead of assuming network failure   ← 实际只补了文件末尾换行（错误 29）
d7323b7  docs(week8): add full project 1 (Hello-Agents RAG) introduction to README                        ← Claude Code，PR #2
3ef31a7  docs(week8): add chat page screenshot                                                             ← 网页上传
7d7a722  docs(week8): fix chat page screenshot                                                             ← 网页覆盖
3089b98  docs(week8): corpus download steps, pinned torch install, unify DEEPSEEK_API_KEY                  ← Claude Code，PR #2
7fb7754  docs: note in .env.example that week1/demo_env.py reads API_KEY                                  ← Claude Code，PR #2
a46341c  Merge pull request #2 from Ruiwen-ZHANG/docs/week8-readme
1e7e93b  docs: week8 summary - project 1 deployment
```

（来自仓库 `git log`，从旧到新。）

---

## 遗留任务

- **catch 提示文字**：index.html 第 144 行改成中性提示，`git diff` 确认后提交（错误 29）
- **/health 多余的一行**：api.py 第 36 行单独的 `hasattr(app.state,"retriever")` 还在，可以删掉；loading 分支也执行不到
- **部署到云服务器**：拿到公网地址（至少 2 核 4 GB，安全组放行端口）。上线前先做防刷：DeepSeek 少充值、IP 限流、每日上限，必要时加访问口令
- **流式输出**：现在要等 3~4 秒整段显示；第 3 周学过 SSE，可以让回答一个字一个字出来
- **CDN 本地化**：把 marked、DOMPurify 下载到 static/，国内访问更稳定，也能消除 Edge 的跟踪防护警告
- **页面显示耗时**（§3 可选小练习）：`performance.now()` 前后相减
- **cli.py 依赖 common/**：只复制 rag_app 跑不起来，可以把 CostTracker 移进 rag_app，或在 README 里说明
- **.env.example 前三行**：`APP_NAME`、`MODEL_NAME`、`MAX_TURNS` 是第 1 周的，可以加注释说明
- **截图下方的空白**：以后重新截一张只包含聊天内容的
- **提交邮箱公开**：GitHub 设置隐藏邮箱，本地改用 noreply 邮箱
- **前端学习支线**：另建 Project 和 frontend-learning 仓库，无固定时间安排
- **第 7 周遗留**：答案层评测（LLM-as-a-Judge）、一题多答案、评测集扩充、Query 改写、更强的 embedding 模型
- **第 4~6 周遗留**：滑动窗口、few-shot、工具参数预校验、tools 声明与 tool_map 统一

---

## 下周预告

项目一完成了：有代码、有评测数据、有延迟优化数据、有能用的网页、有 Docker 镜像、有完整的 README。路线里说，**第 8 周就该开始投第一批日常实习**，面试反馈会告诉你后面该补什么。

第 9 周进入阶段四 **Agent 核心**：**纯手写一个 ReAct Agent**，不用任何框架。一个 while 循环 + 工具注册表 + 消息列表，接 3~4 个工具，加上最大轮次、重复动作检测、超时熔断这些防护，把每一轮的 Thought / Action / Observation 都打印出来。

有意思的是，本周测试时一直问的那个问题——"ReAct 智能体为什么要设置最大步数？"——答案"防止无限循环"，下周就要自己亲手实现了。**用自己写的 RAG 检索一本讲 Agent 的书，再照着书去写 Agent。**
