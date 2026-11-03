# ai-agent-learning

> 我学习 AI Agent / 大模型应用开发的记录仓库：每周一篇技术总结和对应的练习代码。

## 📖 项目简介

这个仓库记录我按 **16 周计划**（2026.09.01 – 2026.12.21）从零学习 AI Agent / 大模型应用开发的过程。起点是只会 Python 基础语法，目标是产出 3 个能写进简历的项目，并具备应用开发方向实习的面试能力。

- 每周一篇技术总结（根目录的 `weekN-*.md`），重点记录**自己踩过的坑**和**实测数据**
- 每周的练习代码放在对应的 `weekN/` 文件夹
- 项目一（RAG 问答）的独立应用放在 [`rag_app/`](rag_app/)

**关注的研究方向：记忆冲突与时间一致性。** 第 5、6 周的笔记里提出过这个问题：RAG 默认"检索回来的资料都是对的"，但当几块资料**互相矛盾，或者有新有旧**时，模型会怎么选？这是后面想继续研究的问题。

## 🗺️ 学习路线

状态说明：✅ 已完成 · 🚧 进行中 · ⬜ 未开始 · ❔ 待定

"实际完成"一列取自 git 提交记录。实际进度比计划晚一些，以下按实际情况标注。

| 周 | 计划时间 | 主题 | 状态 | 实际完成 | 笔记 | 代码 |
|---|---|---|---|---|---|---|
| **阶段一：工程地基** | | | | | | |
| 1 | 9/1 – 9/7 | Python 进阶（类、类型注解、异常、标准库、环境管理） | ✅ | 9/5 – 9/7 | [笔记](week1-python-basics.md) | [week1/](week1/) |
| 2 | 9/8 – 9/14 | Git + HTTP + 异步 | ✅ | 9/7 | [笔记](week2-git-http-async.md) | [week2/](week2/) |
| 3 | 9/15 – 9/21 | FastAPI + SSE + Docker + Linux | ✅ | 9/23 | [笔记](week3-fastapi-docker.md) | [week3/](week3/) |
| **阶段二：LLM 基础** | | | | | | |
| 4 | 9/22 – 9/28 | 裸调 LLM API 与 Prompt 工程 | ✅ | 10/12 – 10/14 | [笔记](week4-llm-api-prompt.md) | [week4/](week4/) |
| 5 | 9/29 – 10/5 | Function Calling 与 Agent 循环 | ✅ | 10/21 – 10/24 | [笔记](week5-function-calling.md) | [week5/](week5/) |
| **阶段三：RAG + 项目一** | | | | | | |
| 6 | 10/6 – 10/12 | RAG 基础链路 | ✅ | 10/25 – 10/26 | [笔记](week6-rag-basics.md) | [week6/](week6/) |
| 7 | 10/13 – 10/19 | 检索优化与评测 | ✅ | 10/29 – 11/2 | [笔记](week7-retrieval-eval.md) | [week7/](week7/) |
| 8 | 10/20 – 10/26 | 项目一收尾上线 | ❔ 待定 | 已做：重排延迟实验、`rag_app` 命令行版 | — | [week8/](week8/)、[rag_app/](rag_app/) |
| **阶段四：Agent 核心 + 项目二** | | | | | | |
| 9 | 10/27 – 11/2 | 手写 ReAct（不用框架） | ⬜ | | | |
| 10 | 11/3 – 11/9 | MCP 协议 | ⬜ | | | |
| 11 | 11/10 – 11/16 | Memory + 沙箱 + 可观测 | ⬜ | | | |
| 12 | 11/17 – 11/23 | 项目二收尾 | ⬜ | | | |
| **阶段五：多 Agent + 评测体系 + 项目三** | | | | | | |
| 13 | 11/24 – 11/30 | LangGraph | ⬜ | | | |
| 14 | 12/1 – 12/7 | 多 Agent 协作 | ⬜ | | | |
| 15 | 12/8 – 12/14 | 自动化评测平台（项目三） | ⬜ | | | |
| 16 | 12/15 – 12/21 | 简历打磨 + 面试冲刺 | ⬜ | | | |

## 📁 目录说明

| 路径 | 内容 |
|---|---|
| [`week1-python-basics.md`](week1-python-basics.md) | 第 1 周总结：类与对象、类型注解、异常处理、pathlib/json/logging、环境管理、典型错误合集 |
| [`week1/`](week1/) | 对话类、`.env` 读取、json/pathlib 练习、Token 计数器、工具注册表 `ToolRegistry` |
| [`week2-git-http-async.md`](week2-git-http-async.md) | 第 2 周总结：Git 三区模型、远程协作、HTTP 基础、httpx、async/await |
| [`week2/`](week2/) | httpx 实战练习、async/await 实验 |
| [`week3-fastapi-docker.md`](week3-fastapi-docker.md) | 第 3 周总结：FastAPI、Pydantic、SSE 流式返回、Docker、Linux 命令行 |
| [`week3/`](week3/) | FastAPI 服务（`POST /chat/stream` SSE 接口）、数据模型、生成器演示、测试客户端 |
| [`week4-llm-api-prompt.md`](week4-llm-api-prompt.md) | 第 4 周总结：DeepSeek API、Token 与计费、流式输出、多轮对话、Prompt 工程、JSON Mode |
| [`week4/`](week4/) | 第一次调用、流式调用（TTFT 统计）、多轮对话、JSON 信息抽取 |
| [`week5-function-calling.md`](week5-function-calling.md) | 第 5 周总结：Function Calling 五步流程、工具描述消融实验、多轮 Agent 循环、并行调用、错误回填 |
| [`week5/`](week5/) | Function Calling 循环、工具描述消融实验、Agent 循环 |
| [`week6-rag-basics.md`](week6-rag-basics.md) | 第 6 周总结：Embedding、切块、Chroma、向量检索、出处标注、混合检索 |
| [`week6/`](week6/) | Embedding 演示、Markdown 切块器、建库、语义检索、带引用的 RAG |
| [`week7-retrieval-eval.md`](week7-retrieval-eval.md) | 第 7 周总结：评测集、Hit@K / MRR、BM25、RRF、bge-reranker 重排、bad case 分析 |
| [`week7/`](week7/) | Hello-Agents 语料清洗与切块、评测集生成、检索评测、混合检索与重排 |
| [`week8/`](week8/) | 重排延迟实验（候选池大小 × `max_length` 四组配置对比） |
| [`rag_app/`](rag_app/) | 项目一：独立的 RAG 问答应用（配置、切块、建库、`Retriever` 类、LLM 调用、命令行问答） |
| [`common/`](common/) | 各周共用模块：`CostTracker` 计费器（区分缓存命中计价） |
| [`Dockerfile`](Dockerfile) | 第 3 周 FastAPI 服务的示例镜像（只打包 `week3/`） |
| [`requirements.txt`](requirements.txt) | Python 依赖 |
| [`.env.example`](.env.example) | 环境变量模板（API Key 只放在本地 `.env`，不提交） |

## 🚀 项目展示

### 项目一：Hello-Agents 教程 RAG 问答（🚧 进行中）

代码：[`rag_app/`](rag_app/) · 过程记录：[第 6 周](week6-rag-basics.md)、[第 7 周](week7-retrieval-eval.md)、[`week8/`](week8/)

基于 Hello-Agents 中文教程（30 篇、2505 块）构建的 RAG 问答。目前完成了命令行版：提问 → 检索 → DeepSeek 生成带 `[编号]` 的回答 → 程序打印准确出处，并检查回答里有没有不存在的编号。

**检索方案**：BM25（jieba 分词）+ 向量（bge-small-zh-v1.5）并集召回，再用 bge-reranker-base 二阶段重排。

**评测集**：用 DeepSeek 批量出题并人工复核，共 123 题，分成 dev 91 题（用来选方案）和 test 32 题（只用来做最终验证）。

**dev 集（91 题）各方法对比**（严格命中）：

| 方法 | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |
|---|---|---|---|---|---|
| 语义检索（基线） | 31.9% | 49.5% | 59.3% | 70.3% | 43.1% |
| BM25 | 57.1% | 76.9% | 79.1% | 87.9% | 68.0% |
| RRF 1:1 | 46.2% | 71.4% | 75.8% | 86.8% | 59.9% |
| RRF 1:3 | 53.8% | 71.4% | 76.9% | 85.7% | 65.0% |
| **并集召回 + 重排** | **75.8%** | **85.7%** | **92.3%** | **94.5%** | **82.5%** |

> 实测：RRF 融合在这份数据上不如单路 BM25，最终方案没有用 RRF。

**test 集（32 题）最终验证**（严格命中）：

| 方法 | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR | 平均每题耗时 |
|---|---|---|---|---|---|---|
| 语义检索（基线） | 37.5% | 59.4% | 71.9% | 78.1% | 51.3% | 0.01 秒 |
| BM25 | 62.5% | 75.0% | 78.1% | 84.4% | 68.8% | 0.01 秒 |
| **并集召回 + 重排** | **75.0%** | **87.5%** | **93.8%** | **93.8%** | **82.1%** | 10.40 秒 |

> ⚠️ test 只有 32 题，1 题约 3.1 个百分点，比较时应看方法之间的差距，不看绝对值。

**延迟优化（第 8 周）**：重排在 CPU 上每题要 10 秒，所以对比了候选池大小（每路 20 / 10 块）和 reranker `max_length`（512 / 256）的四种组合。部署采用 **每路 10 块 + max_length 256**：

| | Hit@3（test） | 平均每题耗时（test） |
|---|---|---|
| 每路 20 块 + 512（第 7 周方案） | 87.5% | 10.4 秒 |
| **每路 10 块 + 256（部署配置）** | **81.2%** | **3.9 秒** |

在 dev 集上，部署配置比第 7 周方案快约 2.9 倍，Hit@3 少答对 2 题。有 GPU 时可以通过环境变量改回 20 / 512（见 [`rag_app/config.py`](rag_app/config.py)）。

**还没做**（第 8 周计划内）：FastAPI 服务、聊天界面、Docker 部署上线。

### 阶段性练习成果

| 周 | 成果 | 代码 |
|---|---|---|
| 3 | SSE 流式聊天接口：`POST /chat/stream` 逐字推送 JSON，末尾附 token 统计块；打包成 Docker 镜像 | [week3/](week3/)、[Dockerfile](Dockerfile) |
| 4 | 不用 SDK、用 httpx 直接调 DeepSeek；流式输出统计首 token 延迟（TTFT）；JSON Mode 信息抽取 | [week4/](week4/) |
| 5 | 工具描述消融实验：详细描述准确率 **100%**，模糊描述 **70%**（3 个困难负样本全部误调；样本量小，只作信号） | [week5/tool_ablation.py](week5/tool_ablation.py) |
| 5 | 多轮 Agent 循环：支持并行工具调用，工具出错时把报错回填给模型，不会崩溃 | [week5/agent_loop.py](week5/agent_loop.py) |
| 6 | 对 week1–5 笔记（591 块）做 RAG：语义检索 + 关键词检索，回答带出处并校验引用编号 | [week6/](week6/) |

## 🛠️ 技术栈

| 类别 | 技术 |
|---|---|
| 语言与工程 | Python、uv、python-dotenv、logging、Git |
| 网络与服务 | httpx、requests、asyncio、FastAPI、Pydantic、Uvicorn、SSE |
| 部署 | Docker |
| 大模型 | DeepSeek API（裸调 `/v1/chat/completions`，流式、多轮、JSON Mode、Function Calling） |
| RAG | sentence-transformers、bge-small-zh-v1.5（Embedding）、bge-reranker-base（重排）、Chroma、rank_bm25、jieba |
| 评测 | 自建评测集，Hit@K、MRR，dev / test 划分 |

## 🕒 最近更新

**2026-11-04**：`rag_app` 改为独立项目，集中管理配置，`Retriever` 类延迟加载模型，新增命令行问答。
