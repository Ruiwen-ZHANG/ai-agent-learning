# 第 7 周技术总结：检索优化与评测

> 16 周 AI Agent 应用开发学习记录 · 第 7 周
> 关键词：评测集、Hit@K、MRR、dev/test 划分、语料清洗、BM25、jieba、RRF、召回与重排、bge-reranker、bad case 分析、检索延迟

---

## 本周概览

第 6 周做出了一个能跑的 RAG，但"效果好不好"只能靠测几个问题、凭感觉判断。第 7 周要解决两件事：

1. **把"好不好"变成数字**：自建评测集，用 Hit@K 和 MRR 给检索打分
2. **用数字证明每一次改进**：BM25、RRF 混合、两阶段重排，每加一项就跑一次评测

> **比方**：第 6 周是学会了做菜，第 7 周是请评委打分，再根据分数改菜谱。

| 小节 | 内容 | 产出文件 |
|---|---|---|
| 0 | 接入项目一语料 Hello-Agents：清洗、拆分超长代码块、修复嵌套代码块、建新库 | `week7/chunker.py`、`week7/build_index.py` |
| 1 | 评测方法：评测集结构、Hit@K、MRR、dev/test 划分 | 无代码 |
| 2 | 用大模型批量造评测集、人工复核、跑出基线 | `week7/make_eval_set.py`、`week7/eval_retrieval.py`，修改 `week7/rag.py` |
| 3 | BM25 关键词检索，RRF 融合 | 修改 `week7/search.py` |
| 4 | 两阶段检索：并集召回 + bge-reranker 重排；bad case 分析；test 集最终验证 | 修改 `week7/search.py`、`week7/eval_retrieval.py`、`week7/rag.py` |

**本周最有分量的产出**：一组在独立测试集上验证过的检索指标。

| test 集（32 题） | Hit@3 | MRR | 平均每题耗时 |
|---|---|---|---|
| 纯语义检索（基线） | 59.4% | 51.3% | 0.01 秒 |
| **并集召回 + 重排（最终）** | **87.5%** | **82.1%** | **10.40 秒** |

> 说明：test 集只有 32 题，1 题约等于 3.1 个百分点，具体数值有误差；dev 集（91 题）上的结果和它基本一致（Hit@3 85.7%、MRR 82.5%）。

**代码仓库**：`https://github.com/Ruiwen-ZHANG/ai-agent-learning`

### 本周文件一览

```
week7/
├── chunker.py          切块：清洗 → 拆段落 → 拆超长代码 → 装卡片
├── build_index.py      建库：切块 → bge 向量 → 存进 hello_agents 集合
├── search.py           检索：语义 search、bm25_search、rrf_search、candidates、rerank_search
├── rag.py              问答：ask_llm（JSON 模式、重试）+ RAG 主流程（已切换到重排）
├── make_eval_set.py    出卷：分层抽样 → DeepSeek 出题 → 程序校验 → 切分保存
└── eval_retrieval.py   考试：可达性检查 → 检索 → Hit@K / MRR / 召回率 / 耗时

data/（不提交）
├── hello-agents-zh/    项目一语料（CC BY-NC-SA 4.0）
└── eval_set.json       评测集 123 题（dev 91 / test 32）
```

week7 的这几个文件是从 week6 复制过来再修改的，week6 保持原样，方便和第 6 周总结对照、做新旧对比。复制后第一件事是把 import 里的 `week6.` 改成 `week7.`，否则改了 week7 的 chunker，build_index 用的仍是 week6 那份，**不报错，只是"改了没效果"**。

---

## 第一章 接入项目一语料

### 1.1 语料选择

项目一语料选的是 Datawhale 开源教程 **Hello-Agents 中文版**：正文 16 章 + 扩展 14 篇，约 115 万字符。

| 考虑因素 | 理由 |
|---|---|
| 主题 | 正是 AI Agent：ReAct、框架、记忆与检索、上下文工程、MCP、Agentic RL、评估 |
| 语言 | 中文，和 bge-small-zh 匹配 |
| 格式 | Markdown，标题层级清晰，chunker 基本可直接用 |
| 许可 | CC BY-NC-SA 4.0：个人学习可用，**不把原文提交到公开仓库**，放在 `data/` 并加入 `.gitignore` |

### 1.2 用第 6 周的 chunker 先跑一遍

只把文件匹配改成递归查找，其余不动：

```
2716 块  最长 12423 字  平均 498 字  超过 500 字：826 块  超过 1500 字：84 块
最长：12423 第九章 9.6.3 核心实现 / 7452 第十一章 11.6.1 / 6041 第十五章 15.5.3
```

发现了第 6 周笔记里没有的三个问题：

| 问题 | 规模 | 危害 |
|---|---|---|
| 超长代码块 | 最长一块 12423 字 | bge 只读前 512 token，后 95% 等于没索引；命中后六七千 token，又贵又挤占其他资料 |
| HTML 噪音 | 约 200 个图片块、9201 个 `<strong>`、表格对齐空格 | 浪费 token、稀释向量；`<strong>` 甚至出现在标题里 |
| 文献编号 `[1]` | 72 处 `<sup>[1]</sup>`，全文共 223 处 `[数字]` | 和 RAG 的引用编号 `[1]` 撞车 |

**文献编号为什么危险**：资料里正文的 `[3]` 是书的文献编号，外层 `[1]` 是 build_context 加的资料编号，两者长得一样。

- **生成环节**：模型可能把正文的 `[3]` 抄进回答，读者去看资料 [3]，内容完全无关，而且看起来像是对的
- **检查环节**：`check_citations` 只认 `\[(\d+)\]`。抄进来的是 `[7]` 会误报；更糟的是抄进来的 `[3]` 恰好在 1~5 之间，**直接通过检查**

> 经验：**设计引用格式前，先检查语料里有没有同样的格式。**

### 1.3 `load_all_chunks` 通用化

```python
def load_all_chunks(root, pattern="week*.md"):
    """读取 root 目录下所有匹配 pattern 的 md 文件，切块后合并返回"""
    all_chunks = []
    for f in sorted(root.glob(pattern)):
        if f.name == "SOURCE.md":          # 语料说明文件，不是正文，跳过
            continue
        text = f.read_text(encoding="utf-8")
        all_chunks.extend(chunk_markdown(text, f.relative_to(root).as_posix()))   # 相对路径，统一正斜杠
    return all_chunks
```

| 改动 | 原因 |
|---|---|
| `pattern` 默认 `"week*.md"` | 笔记库的旧调用不用改；语料传 `"**/*.md"` 递归查找 |
| source 用相对路径 `main/第八章 记忆与检索.md` | 原仓库里光 `README.md` 就有十几个，只记文件名分不清；还可以按 `main/` / `extra/` 做元数据过滤 |
| `.as_posix()` | Windows 的 `\` 换成 `/`，部署到 Linux 时同一个出处还是同一个字符串 |

### 1.4 `clean_text`：切块前清洗（6 步）

```python
def clean_text(text):
    """切块前清洗语料：
    ① 图片块 <div><img><p>图注</p></div> → [图注]
    ② 删除零散 <img>
    ③ <sup>[1][2]</sup> → （文献1,2），避免和 RAG 引用编号 [1] 混淆
    ④ 删除 <strong>，<br> 换成空格
    ⑤ 表格行压缩连续空格和横线
    ⑥ 参考文献列表行首 [1] → 文献1.
    """
    # ① 图片块整体换成 [图注]；DOTALL 让 . 能跨行匹配
    text = re.sub(r'<div align="center">.*?<p>(.*?)</p>.*?</div>', r'[\1]', text, flags=re.DOTALL)
    # ② 删掉图片块之外剩下的零散 <img>
    text = re.sub(r'<img[^>]*>', '', text)
    # ③ 只在 <sup> 内部取数字拼成（文献1,2）；<sup> 外面的 matrix[0][1] 不受影响
    text = re.sub(r'<sup>(.*?)</sup>',
                  lambda m: "（文献" + ",".join(re.findall(r"\d+", m.group(1))) + "）",
                  text)
    # ④ <strong> 和 </strong> 都删掉，<br> 各种写法换成空格
    text = re.sub(r'</?strong>', '', text)
    text = re.sub(r'<br\s*/?>', ' ', text)
    # ⑤ 只处理表格行（以 | 开头），代码里的缩进空格不能动
    new_lines = []
    for line in text.split("\n"):
        if line.lstrip().startswith("|"):
            line = re.sub(r' {2,}', ' ', line)      # 连续空格 → 1 个
            line = re.sub(r'-{3,}', '---', line)    # 连续横线 → 3 个（表格分隔行至少要 3 个）
        new_lines.append(line)
    text = "\n".join(new_lines)
    # ⑥ 参考文献列表：行首 [1] → 文献1.；MULTILINE 让 ^ 匹配每一行的开头
    text = re.sub(r'^\[(\d+)\]', r'文献\1.', text, flags=re.MULTILINE)
    return text
```

| 正则写法 | 含义 |
|---|---|
| `.*?` | 非贪婪：遇到第一个能结束的位置就停。用 `.*` 会一直吞到全文最后一个 `</div>` |
| `[^>]*` | 任意多个"不是 `>`"的字符，匹配到标签自己的 `>` 为止 |
| `</?strong>` | `/?` 表示斜杠可有可无，一个模式匹配开始和结束标签 |
| `re.DOTALL` | 让 `.` 也匹配换行（跨行的图片块） |
| `re.MULTILINE` | 让 `^` 匹配每一行开头（行首的文献编号） |
| `re.sub(模式, 函数, 文本)` | 第二个参数可以是函数：每找到一处，用函数返回值替换 |

**检查点**（不读语料，用一段样例测试）：

```
输入：理论框架<sup>[1]</sup> … <div align="center"><img …/><p>图 8.1 人类记忆系统的层次结构</p></div>
      参见<sup>[1][2]</sup>。代码 matrix[0][1] 不能被改。
      ### <strong>2.7 对比两种架构</strong>
      | <strong>范式</strong>    | 说明        |
      | ---------------- | ----------- |
          x = outputs[0]
      [1] Anthropic. Building effective agents.

输出：理论框架（文献1），如图8.1所示。
      [图 8.1 人类记忆系统的层次结构]
      参见（文献1,2）。代码 matrix[0][1] 不能被改。
      ### 2.7 对比两种架构
      | 范式 | 说明 |
      | --- | --- |
          x = outputs[0]
      文献1. Anthropic. Building effective agents.
```

最后几行专门检验副作用：代码缩进还在、`matrix[0][1]` 和 `outputs[0]` 没被改。

> **清洗规则是针对某一份语料设计的。** 这套规则对 week 笔记也生效，第 6 周总结里的 `[1] 出处：…` 示例会被 ⑥ 改成 `文献1. 出处：…`。以后可以给 `chunk_markdown` 加一个开关参数决定要不要清洗。

### 1.5 拆分超长代码块

还是第 6 周"扫描 → 遇到边界就打包 → 收尾"的骨架：**元素是代码行，边界是"已经够长并且遇到空行"**。

```python
MAX_CODE = 1500   # 代码块的字数上限：超过就在内部拆开


def split_long_code(para, max_chars):
    """超长代码块在内部空行处拆开，每段补回开头行和结尾行；其他段落原样返回 [para]"""
    # 不是代码块，或者没超长：原样返回只有一个元素的列表
    if not para[0].lstrip().startswith("```") or len("\n".join(para)) <= max_chars:
        return [para]

    head = para[0]       # 开头行，如 ```python
    tail = para[-1]      # 结尾行 ```
    body = para[1:-1]    # 中间的代码行

    pieces = []          # 结果：拆出来的每一段
    piece = []           # 当前这一段的代码行
    size = 0             # 当前这一段的字数
    for line in body:
        # 边界：够长了，并且（是空行，或者已经到 2 倍上限：没有空行也强制切）
        if size >= max_chars and (line.strip() == "" or size >= 2 * max_chars):
            pieces.append([head] + piece + [tail])     # 补上开头和结尾，成为完整代码块
            piece = []
            size = 0
            if line.strip() == "":                     # 软边界：空行丢掉
                continue                               # 硬边界：这一行放进下一段，不能 continue
        piece.append(line)
        size += len(line) + 1                          # +1 是换行符
    if piece:                                          # 收尾：最后一段也要补开头和结尾
        pieces.append([head] + piece + [tail])
    return pieces


def make_paras(buf):
    """一节的行 → 段落列表：先按空行拆段，再把超长代码块拆开"""
    paras = []
    for p in split_paragraphs(buf):
        paras.extend(split_long_code(p, MAX_CODE))     # 拆成几段就逐个加进来
    return paras
```

`chunk_markdown` 里两处 `pack(split_paragraphs(buf), MAX_CHARS)` 都换成 `pack(make_paras(buf), MAX_CHARS)`。

| 设计点 | 原因 |
|---|---|
| 没超长也返回 `[para]` 而不是 `para` | 调用方拿到的永远是"段落列表"，用 `extend` 统一处理 |
| 软边界 + 硬边界 | 优先在空行（函数、逻辑块之间）切；一大段没有空行时 2 倍上限强制切，避免仍然超长 |
| 每段补 head 和 tail | 每段都是完整代码块；否则代码里的 `# 注释` 在 Markdown 里会变成一级标题 |
| `and (… or …)` 的括号 | `and` 优先级比 `or` 高，不加括号意思就变了 |

### 1.6 嵌套代码块：一次修复引发的新 bug

**发现**：复核评测集时，q063 的 heading 是 `git clone https://github.com/yourname/my-skill.git`，明显是代码注释被当成了标题。

**原因**：`Extra05-AgentSkills解读.md` 里一个 ```` ```markdown ```` 代码块演示 SKILL.md 的写法，里面又嵌了一个 ```` ```python ````。原规则"遇到 ``` 就切换开关"在第 432 行把开关关掉，此后正文当代码、代码注释当标题，一直错到文件末尾。全部 30 个文件里只有它的 ``` 数量是奇数（33 个）。

**第一次修复（我给的，错的）**：在代码块里，只有单独一行 ```` ``` ```` 才算结束。Extra05 修好了，总块数却从 2512 掉到 **2456**。原因是第四、七、八、十二章作者用了标准写法：**外层 4 个反引号，里面放 3 个反引号的代码块**：

~~~
643  ````python                                  ← 外层：4 个反引号开始
...      请严格按照以下格式输出你的计划：
652  ```python                                   ← 内层，属于代码内容
653  ["步骤1", "步骤2", "步骤3", ...]
654  ```                                         ← 第一次修复的规则在这里判定外层结束 ✗
...  """
656  ````                                        ← 被当成新代码块的开始，此后整章开关反了
~~~

| 文件 | 原规则 | 第一次修复 | 最终规则 |
|---|---|---|---|
| Extra05 | 54 | 48 ✓ | 48 |
| 第四章 | 87 | **64** ✗ | 86 |
| 第七章 | 120 | **113** ✗ | 120 |
| 第八章 | 114 | **103** ✗ | 114 |
| 第十二章 | 160 | **151** ✗ | 160 |

（表中是讲解方用参考代码复现的数字，基数和实际运行差 3 块，变化量一致。）

**最终规则（Markdown 规范）**：结束行必须**整行只有反引号**，并且**个数不少于开头**。所以开关从 True/False 改成整数，记住开头用了几个反引号：

```python
def update_fence(line, fence):
    """根据这一行更新代码块状态。fence 是当前代码块开头的反引号个数，0 表示不在代码块里"""
    s = line.strip()
    n = len(s) - len(s.lstrip("`"))             # 这一行开头有几个连续的反引号
    if fence == 0 and n >= 3:                   # 不在代码块里，遇到 3 个以上反引号：开始
        return n
    if fence and n >= fence and s == "`" * n:   # 在代码块里，整行只有反引号且个数不少于开头：结束
        return 0
    return fence                                # 其他情况：状态不变
```

`split_paragraphs` 和 `chunk_markdown` 两处都改成：

```python
        new_fence = update_fence(line, fence)
        if new_fence != fence:          # 状态变了：这一行是代码块的开头或结尾
            fence = new_fence
            buf.append(line)            # split_paragraphs 里是 para.append(line)
            continue
```

其余所有 `not in_code` 改成 `not fence`（fence 为 0 时是 False）。

> **教训**：修 bug 时要**在整份数据上验证修复结果**，而不是只看出问题的那个文件。第一次修复只看了 Extra05 变好了，没检查别的文件有没有变坏。

同一个判断写在两个函数里，改一处漏一处的风险很大；抽成 `update_fence` 一个函数，两处调用。

### 1.7 最终切块统计与建库

| | 第 6 周 chunker | 清洗 + 拆代码 | + 嵌套代码块修复（最终） |
|---|---|---|---|
| 总块数 | 2716 | 2512 | **2505** |
| 最长 | 12423 字 | 2492 字 | — |
| 平均 | 498 字 | 485 字 | — |

块数变少，是因为清洗删掉了大量噪音，pack 能把更多段落装进一张卡片；超过 1500 字的块变多（84 → 103），是因为原来上万字的代码块被拆成了几段 1500~2500 字的，块数多了但每块都不再离谱。

`build_index.py` 参数化：

```python
CORPUS_DIR = ROOT / "data" / "hello-agents-zh"   # 语料目录
PATTERN = "**/*.md"                               # 递归匹配所有 md
COLLECTION = "hello_agents"                       # 新集合名；week6 的 "notes" 不要动
```

```
共 2505 块
Batches: 100%|██████████| 79/79 [02:26<00:00,  1.85s/it]
向量形状：(2505, 512)
集合里共有 2505 条记录
```

一个 Chroma 数据库里可以放多个集合，`notes`（笔记库）和 `hello_agents`（项目一）互不影响。

---

## 第二章 评测方法

### 2.1 为什么要先建评测集

第 6 周靠 5 个问题加肉眼判断，有三个问题：样本太少；改了一处不知道别处有没有变差；说不出数字。

**评测集 = 一套固定的题目，每题标好正确答案在哪里。** 每做一次改进就整套重跑，分数涨了说明有效，跌了说明改坏了。

| 层面 | 评什么 | 怎么判断 | 本周 |
|---|---|---|---|
| 检索 | 正确资料有没有被找回来 | 程序自动判断 | **主要做** |
| 答案 | 最终回答对不对 | 人工或 LLM-as-a-Judge | 遗留 |

先评检索：检索没找到，生成再好也没用；而且检索评测不调大模型，不花钱，可以反复跑。

### 2.2 每题记录 evidence，不记录 chunk id

```python
{
    "question": "ReActAgent 初始化时，哪个参数用来限制循环最多跑多少步？",
    "evidence": "`max_steps`： ReAct循环的最大执行步数，防止无限循环。",   # 答案所在的一句原文
    "source": "main/第七章 构建你的Agent框架.md",
    "heading": "7.4.2 ReActAgent",
    "id": "q027",
    "split": "dev",
}
```

**命中规则**：检索回来的某一块，和题目同一个文件，并且 text 包含 evidence。

**为什么不记 chunk id**：切块一改编号全变（第 6 周 chunker 2716 块、清洗后 2512 块、修复后 2505 块，同一段内容在三个版本里编号都不同）。记 id 的话，每改一次切块都要重新标注，不同切块方案之间也没法比较。evidence 不受切块影响。

evidence 要短（15~60 字）：太长容易被切块切成两半，两块都不完整包含它，被误判为没找到。

### 2.3 三个指标

| 指标 | 含义 |
|---|---|
| **Hit@K** | 前 K 块里有没有正确答案，有记 1 没有记 0，对所有题取平均 |
| **MRR** | 正确答案排第几：第 1 记 1，第 2 记 1/2……没找到记 0，取平均 |
| Recall@K | 一题答案分散在多块时"找回了几块"；本评测集每题一句 evidence，和 Hit@K 相同，不单独算 |

检验题算例：4 题正确答案分别排第 2、第 1、没找到、第 5：

| 题 | 排名 | Hit@1 | Hit@3 | Hit@5 | 倒数排名 |
|---|---|---|---|---|---|
| 1 | 2 | 0 | 1 | 1 | 0.5 |
| 2 | 1 | 1 | 1 | 1 | 1 |
| 3 | 没找到 | 0 | 0 | 0 | 0 |
| 4 | 5 | 0 | 0 | 1 | 0.2 |
| **平均** | | **25%** | **50%** | **75%** | **MRR = 42.5%** |

指标描述的是整套评测集，最后要**对所有题取平均**，报一个数字。

**排名为什么重要**：RAG 只把前 3 块交给模型，正确答案排第 4 就等于没找到；排得越靠前，模型越容易注意到。

### 2.4 dev / test 划分

| | 开发集 dev（练习题） | 测试集 test（期末考卷） |
|---|---|---|
| 用途 | 比较方法、调参数，随便跑 | 最后只跑一次，报到简历上的是这个 |

在同一套题上反复调参数，挑出分数最高的方案，分数会虚高。**"记住"这套题的不是模型**（embedding 和 Chroma 不会学习），**而是我们自己**：挑出的方案有一部分好处来自"恰好适合这些题"，换成新问题就没了。

流程：

```
第 1 步：在 dev 上反复比较语义、BM25、RRF、重排…… → 挑出最好的方案
第 2 步：在 test 上只跑一次：基线 vs 最终方案 → 看提升是不是真的
```

目的不是"证明某方法更好"，而是**测出哪个更好**，测出来是什么就报什么。

---

## 第三章 造评测集，跑出基线

### 3.1 流程

```
2505 块 ──① 筛选 + 分层抽样──▶ 178 块
       ──② 每块让 DeepSeek 出一道题──▶ {question, evidence}
       ──③ 程序校验 evidence 是原文──▶ 140 题
       ──④ 打乱，切成 dev / test──▶ data/eval_set.json
       ──⑤ 人工复核──▶ 123 题
```

（评测集是在嵌套代码块修复之前、2512 块的版本上生成的。修复后做了可达性检查，dev 91 题、test 32 题全部可达。）

### 3.2 出题 prompt

```python
GEN_PROMPT = """你是评测集出题人。根据下面这段【资料】，出一道检索评测题。

要求：
1. 问题要像真实用户提问：换一种说法，不要照抄资料里的原词，可以口语化
2. 问题必须能用资料中的某一句话回答
3. 问题必须能独立看懂：不能用"这种""上述""文中""该方法"等指代资料里的内容，要写出具体名称
4. evidence 必须从资料中【一字不差】地复制一句话，长度 15 到 60 字，这句话要能回答问题
5. 如果资料不适合出题（比如只有目录、链接、致谢，或者只有代码没有任何说明），返回 {"skip": true}

只输出 JSON，格式：{"question": "...", "evidence": "..."}

【资料】
"""
```

| 规则 | 用意 |
|---|---|
| 换说法 | 照抄原文的题目和原块向量几乎一样，检索太容易，分数虚高 |
| 一句话能回答 | 每题只有一个明确的答案位置 |
| 能独立看懂 | 第一次试跑出了"为什么**这种**位置编码……"，用户手里没有原文，题目本身不完整；这条是试跑后加的 |
| 一字不差、15~60 字 | 命中判断用 `in`，必须原样；太短易误匹配，太长易被切断 |
| 允许跳过 | 不给退路，模型会对着目录硬编题 |

### 3.3 改造 `ask_llm`：JSON 模式 + 重试

`make_eval_set.py` 不复制一份调用 API 的代码，而是 `from week7.rag import ask_llm`，所以先改造它：

```python
def ask_llm(messages, json_mode=False):
    """调用 DeepSeek，返回 (回答文本, usage)；json_mode=True 时要求模型只输出 JSON"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 1000,
        "thinking": {"type": "disabled"},
    }
    if json_mode:                                            # 按需往已建好的字典里加一个键
        payload["response_format"] = {"type": "json_object"}

    for attempt in range(3):                                 # 最多试 3 次
        try:
            response = httpx.post(URL, headers=HEADERS, json=payload, timeout=30)
            break                                            # 成功就跳出循环
        except (httpx.TimeoutException, httpx.RequestError) as e:
            if attempt == 2:                                 # 第 3 次还失败
                raise                                        # 原样抛给调用方，让它决定怎么办
            wait = 2 ** attempt                              # 1 秒、2 秒：指数退避
            print(f"网络错误，{wait} 秒后重试（第 {attempt + 1} 次）：{e}")
            time.sleep(wait)

    if response.status_code != 200:
        raise RuntimeError(f"API 返回 {response.status_code}：{response.text[:200]}")

    data = response.json()
    choice = data["choices"][0]
    if choice["finish_reason"] == "length":
        print("⚠ 回答被截断，可以调大 max_tokens")
    return choice["message"]["content"], data["usage"]
```

| 设计点 | 说明 |
|---|---|
| `json_mode=False` 默认值 | `rag()` 里原来的 `ask_llm(messages)` 不用改，行为不变。**加参数并保留旧默认行为**是给已有函数加功能的常用做法 |
| JSON 模式要求 prompt 里出现 "json" | 否则接口报错；GEN_PROMPT 里写了"只输出 JSON" |
| `sys.exit` 改成 `raise` | **工具函数不替调用方决定"程序要不要结束"**：rag.py 出错可以退出，批量出题时应该跳过这一块继续 |
| 指数退避重试 | 第 2 周学过；批量调用几百次，偶发断线很正常 |

### 3.4 `make_eval_set.py` 主程序

```python
CORPUS_DIR = Path(__file__).parent.parent / "data" / "hello-agents-zh"
OUT_PATH = Path(__file__).parent.parent / "data" / "eval_set.json"   # data/ 不提交（evidence 是语料原文）
PER_FILE = 6                                                          # 每个文件最多抽几块
random.seed(42)                                                       # 固定随机种子：评测集可复现

if __name__ == "__main__":
    tracker = CostTracker()
    chunks = load_all_chunks(CORPUS_DIR, "**/*.md")
    # 正文（去掉第一行标题路径）至少 150 字才留下
    candidates = [c for c in chunks if len(c["text"].split("\n", 1)[1]) >= 150]
    groups = {}                                                   # source → 这个文件的块列表
    for c in candidates:
        groups.setdefault(c["source"], []).append(c)
    picked = []
    for source, cs in groups.items():
        picked.extend(random.sample(cs, min(PER_FILE, len(cs))))  # 分层抽样：每个文件都有题
    print(f"共 {len(chunks)} 块，筛选后 {len(candidates)} 块，分成 {len(groups)} 组，抽到 {len(picked)} 块")

    items, n_skip, n_bad = [], 0, 0
    LIMIT = None                                     # None 表示跑全部；调试时改成 5 先小批量试跑
    if LIMIT:
        picked = picked[:LIMIT]

    for i, c in enumerate(picked, 1):
        body = c["text"].split("\n", 1)[1]
        msgs = [{"role": "user", "content": GEN_PROMPT + body}]
        try:                                         # ① 调用 API：重试后仍失败，跳过这一块
            content, usage = ask_llm(msgs, json_mode=True)
        except (httpx.HTTPError, RuntimeError) as e:
            n_bad += 1
            print(f"[{i}] ✗ 调用失败：{e}")
            continue
        tracker.record("deepseek-flash", usage)      # 调用成功才记账
        try:                                         # ② 解析 JSON：不合法就跳过
            item = json.loads(content)
        except json.JSONDecodeError:
            n_bad += 1
            print(f"[{i}] ✗ JSON 解析失败：{content[:50]}")
            continue
        if item.get("skip"):                         # 正常出题时没有这个键，用 .get
            n_skip += 1
            print(f"[{i}] - 跳过：{c['heading']}")
            continue
        q = item.get("question", "").strip()
        ev = item.get("evidence", "").strip()
        # 问题不为空、evidence 是原文、长度 15~60；长度检查同时堵住了 "" in body 恒为 True 的漏洞
        if not q or ev not in body or not 15 <= len(ev) <= 60:
            n_bad += 1
            print(f"[{i}] ✗ 校验失败：{ev[:40]}")
            continue
        items.append({"question": q, "evidence": ev, "source": c["source"], "heading": c["heading"]})
        print(f"[{i}] ✓ {q}")

    random.shuffle(items)                            # 打乱：不让 dev 全是前几章
    for n, it in enumerate(items, 1):
        it["id"] = f"q{n:03d}"
        it["split"] = "dev" if n <= 100 else "test"
    OUT_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"出题 {len(picked)} 块：合格 {len(items)} 题，跳过 {n_skip}，不合格 {n_bad}")
    tracker.report()
```

几个值得记住的点：

- **分层抽样**：块多的章节直接随机抽会被抽很多次，小章节可能一题没有。`setdefault(键, [])` 一行完成"没有就建空列表再追加"
- **随机种子**：相同的种子生成相同的"随机数"序列，评测集可以重新生成，别人也能复现
- **先小批量试跑**：178 次调用要几分钟，有 bug 先在 5 块上暴露
- **不要相信模型，自己校验**：和第 6 周 `check_citations` 一个思路
- **空字符串陷阱**：`"" in "任何字符串"` 是 True。只检查 `ev in body`，空 evidence 会混进来，之后每题都"命中"，分数虚高到 100%；长度检查顺带堵上了这个漏洞

### 3.5 运行结果

```
共 2512 块，筛选后 2008 块，分成 30 组，抽到 178 块
…
出题 178 块：合格 140 题（dev 100 / test 40），跳过 9，不合格 29
总调用次数： 178
总输入token： 70420
总输出token： 8013
缓存命中token： 28543
缓存命中率：40.5%
总花费：$0.011175
```

178 = 29 × 6 + 4：29 个文件各抽 6 块，Extra13 筛选后只剩 4 块，全部抽走。

### 3.6 人工复核：140 → 123 题

| 问题类型 | 题数 | 处理 |
|---|---|---|
| **题干就是 evidence**：出题的块本身是"习题"或"面试题列表"，原文里没有答案 | 6 | 删除 |
| **evidence 不含答案**：只是引子或总结（"下面是……的列表："） | 10 | 删除 |
| **依赖上下文**："这个智能客服""这段代码"之类，不看原文不知道问什么 | 17 | 改写，补上具体名称 |
| **照抄原文** | 2 | 改写 |
| **dev/test 泄漏**：两题出自同一节、问同一件事，一个在 dev 一个在 test | 1 | 删除 |

结果：**123 题（dev 91 / test 32）**。改写的题保留 `question_orig` 字段存原问题。

两个启示：

- **加了"必须能独立看懂"规则，仍有 17 题用了指代**：光靠 prompt 约束不住，人工复核必不可少
- **"题干就是 evidence"最隐蔽**：题目看起来很正常，检索时一定能命中（题目和原文几乎一样），会把分数虚抬高

### 3.7 `eval_retrieval.py`

```python
def find_rank(hits, item, section=False):
    """返回正确答案排第几（从 1 开始），没找到返回 None。
    section=False（严格）：必须同文件、并且包含 evidence 原句
    section=True（同节）：同文件同小节的块也算命中
    """
    for rank, h in enumerate(hits, 1):
        if h["source"] != item["source"]:
            continue
        if item["evidence"] in h["text"]:
            return rank
        if section and h["heading"] == item["heading"]:
            return rank
    return None                                       # 和 for 对齐：10 块都检查完才返回 None


def evaluate(search_fn, items, k, section=False):
    """用 search_fn 检索每道题，返回 (指标字典, 每题的排名列表)"""
    ranks = []
    for item in items:
        hits = search_fn(item["question"], k=k)        # 检索函数当参数传进来
        ranks.append(find_rank(hits, item, section))
    n = len(ranks)
    metrics = {}
    for cut in (1, 3, 5, 10):
        metrics[f"Hit@{cut}"] = sum(1 for r in ranks if r is not None and r <= cut) / n
    metrics["MRR"] = sum(1 / r for r in ranks if r is not None) / n
    return metrics, ranks
```

- **函数当参数**：以后每做一种新检索，评测代码一行不改，`evaluate(新函数, …)` 就行
- **`r is not None and r <= cut` 的顺序不能反**：r 是 None 时前一个条件不成立，`and` 短路，不会去算 `None <= cut`
- **可达性检查**：评测前确认每题 evidence 在当前切块里还找得到。切块每改一次都要重做；不可达的题不是检索的错，不计入分数

### 3.8 基线

```
dev 共 91 题，可达 91 题
语义（baseline）：Hit@1 31.9%  Hit@3 49.5%  Hit@5 59.3%  Hit@10 70.3%  MRR 43.1%
```

- **Hit@3 只有 49.5%**：RAG 默认取前 3 块，一半的问题正确资料根本没交到模型手里
- **Hit@10 比 Hit@3 高 21 个百分点**：五分之一的题找到了只是排在 4~10 名，这是重排的用武之地
- **27 题前 10 都没进**，大致分两类：答案是代码或标识符（`HF_ENDPOINT`、`input_schema`、`requires-python`、`self.history`），适合关键词检索；问法和原文用词差别大，适合重排或改写

---

## 第四章 BM25 与 RRF 融合

### 4.1 为什么要混合检索

| | 语义检索 | 关键词检索 |
|---|---|---|
| 擅长 | 问法和原文**用词不同、意思相同** | 问题里有**专有名词、代码、编号** |
| 不擅长 | 分不清长得像的标识符，读不懂代码 | 用词一换就找不到 |
| 例子 | "函数结果交还给大模型" 找到 "工具执行后回填" | 422 vs 400；`input_schema` |

单用任何一种都有一类问题必然找不到，混合的想法是两路都跑、互相补漏。

第 6 周的 `$contains` 关键词检索有三个缺点：要先用规则挑关键词（`MaxRetryError`、`NoteTool` 挑不出来）；不排序（422 只找到最先入库的 week3）；只看有没有，不看次数和稀有程度。

### 4.2 BM25

| 因素 | 含义 |
|---|---|
| 词频 | 问题的词在这块出现越多分越高 |
| **逆文档频率 IDF** | 越稀有的词命中了越值钱："的""智能体"几乎每块都有，`input_schema` 全书只出现几次 |
| 长度归一化 | 长块天然词多，扣一点分 |

IDF 自动挑出了专有标识符，不用再写规则。中文先用 jieba 分词，`lcut_for_search` 会把长词再拆出短词。

### 4.3 RRF 倒数排名融合

两路分数量纲不同（相似度 0.5~0.7，BM25 0~30），不能直接相加，否则等于只用 BM25。RRF 只看排名：

```
RRF 分数 = Σ  w / (60 + 在这一路的排名)
```

检验题：一块语义第 1、BM25 没找到 → 1/61 = 0.0164；另一块两路都第 4 → 2/64 = 0.0313，**后者排得更前**。两路都认可的块更可靠；60 让名次之间差距很小，"两路都有"的优势就显得很大。

### 4.4 代码（`search.py`）

```python
import re
import jieba                          # 中文分词
from rank_bm25 import BM25Okapi       # BM25 打分


def tokenize(text):
    """中文分词（搜索引擎模式），转小写，去掉标点和空白；建库和查询必须用同一个"""
    return [w.lower() for w in jieba.lcut_for_search(text) if re.search(r"\w", w)]


# 从 Chroma 取出全部块建 BM25 索引：保证和向量库是同一批块、编号一一对应
_all = col.get(include=["documents", "metadatas"])
BM25_IDS = _all["ids"]
BM25_DOCS = _all["documents"]
BM25_METAS = _all["metadatas"]
bm25 = BM25Okapi([tokenize(d) for d in BM25_DOCS])


def bm25_search(query, k=10):
    """BM25 检索，返回分数最高的 k 块（格式和 search 一致）"""
    scores = bm25.get_scores(tokenize(query))       # 对每一块的分数，长度 2505
    top = scores.argsort()[::-1][:k]                # 从高到低，取前 k 个下标
    return [{"id": BM25_IDS[i], "text": BM25_DOCS[i],
             "source": BM25_METAS[i]["source"], "heading": BM25_METAS[i]["heading"],
             "score": float(scores[i]), "via": "BM25"} for i in top]


def rrf_search(question, k=10, pool=20, w_sem=1.0, w_bm25=1.0):
    """语义 + BM25 各取 pool 块，加权 RRF 融合，返回前 k 块"""
    rrf, by_id = {}, {}
    for w, hits in ((w_sem, search(question, pool)), (w_bm25, bm25_search(question, pool))):
        for rank, h in enumerate(hits, 1):
            rrf[h["id"]] = rrf.get(h["id"], 0) + w / (60 + rank)   # 两路都有就累加
            by_id.setdefault(h["id"], h)
    top_ids = sorted(rrf, key=rrf.get, reverse=True)[:k]           # 按分数排字典的键
    return [{**by_id[i], "score": rrf[i], "via": "RRF"} for i in top_ids]
```

| 写法 | 说明 |
|---|---|
| `re.search(r"\w", w)` | 一个字母、数字、汉字都没有的就是纯标点，去掉 |
| `scores.argsort()[::-1][:k]` | argsort 返回排序后各位置原来的下标；`[::-1]` 倒序；`[:k]` 取前 k |
| `sorted(rrf, key=rrf.get, reverse=True)` | 排序字典时遍历的是键，按键对应的值排 |
| `{**by_id[i], "score": …}` | 展开字典再覆盖两个键，创建新字典，不改原数据 |
| 模块顶层代码的顺序 | `bm25 = BM25Okapi([tokenize(d) …])` 在导入时立即执行，`def tokenize` 必须写在它上面 |
| `lambda q, k: rrf_search(q, k, w_bm25=2)` | 把权重"固定"进去，造出 evaluate 需要的两参数检索函数 |

### 4.5 dev 结果

| 方法 | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |
|---|---|---|---|---|---|
| 语义（基线） | 31.9% | 49.5% | 59.3% | 70.3% | 43.1% |
| **BM25** | **57.1%** | **76.9%** | **79.1%** | **87.9%** | **68.0%** |
| RRF 1:1 | 46.2% | 71.4% | 75.8% | 86.8% | 59.9% |
| RRF 1:2 | 50.5% | 71.4% | 76.9% | 85.7% | 63.3% |
| RRF 1:3 | 53.8% | 71.4% | 76.9% | 85.7% | 65.0% |

**两个意外**：

1. **BM25 单独用就大幅领先语义检索**
2. **RRF 怎么调权重都超不过 BM25**：权重越偏 BM25，越逼近 BM25，但始终在它下面；权重无穷大时 RRF 就等于纯 BM25

"两路都认可更可靠"的前提是**两路水平差不多**。语义这一路明显弱，同等权重等于让差的意见把好的往下拉。

**语义检索为什么这么弱**（三条都要如实写）：

1. bge-small 只读前 512 token，块平均 485 字加上标题路径，后半部分进不了向量；BM25 整块每个词都参与
2. 技术教程块里混着大量代码，小 embedding 模型对代码的理解很差
3. **评测集本身偏向 BM25**：大模型看着原文出题，"Plan-and-Solve""MCP""ContextBuilder"这类专有名词换不了说法，原样出现在问题里，正是 BM25 的强项。真实用户也会带这些名词，所以不全是偏差，但分数里有一部分来自出题方式

> "混合检索一定比单路好"是常见说法，在本周的数据上**不成立**。写进总结和简历的应该是测出来的结论。

---

## 第五章 两阶段检索：召回 + 重排

### 5.1 思路

```
阶段一 召回（快、粗）                    阶段二 重排（慢、准）
2505 块 ──BM25 前20 ∪ 语义前20──▶ 约 30~40 块 ──reranker 逐块打分──▶ 前 k 块
```

> **招聘的比方**：先看简历筛掉大部分人（快，看关键词），剩下二三十人逐个面试（慢，但准）。不可能给几千人都面试，也不能只凭简历关键词录用。

### 5.2 两种模型结构

| | Embedding（bge-small，双塔） | Reranker（bge-reranker-base，交叉编码器） |
|---|---|---|
| 怎么算 | 问题和块**分别**变成向量，再算余弦 | 问题和块**拼在一起**输入，直接输出相关度 |
| 能否提前算 | 能，建库时算好 | 不能，每个问题和每块都要重算 |
| 速度 | 极快 | 慢 |
| 准确度 | 一般：块被压成向量时还不知道用户会问什么 | 高：带着问题去读这块内容 |

sentence-transformers 里分别对应 `SentenceTransformer.encode`（一段文字 → 一个向量）和 `CrossEncoder.predict`（一对 (问题, 块) → 一个分数）。

### 5.3 检验题要点

1. **为什么不给 2505 块全部重排**：每块都要跑一次完整模型，CPU 上一个问题要好几分钟
2. **召回决定上限**：正确答案没被召回，重排再准也拿不出来。召回是"把人请进面试间"，重排是"面试"
3. **为什么取并集**：语义单独 Hit@10 也有 70%，其中一部分 BM25 找不到；并集包含正确答案的比例一定不低于任何一路。高多少，要测

### 5.4 代码

```python
from sentence_transformers import CrossEncoder

reranker = CrossEncoder("BAAI/bge-reranker-base", max_length=512)   # 首次运行下载约 1.1GB


def candidates(question, pool=20):
    """召回：BM25 前 pool 块 + 语义前 pool 块，按 id 去重后合并（并集）"""
    seen = set()
    result = []
    for h in bm25_search(question, pool) + search(question, pool):
        if h["id"] not in seen:
            seen.add(h["id"])
            result.append(h)
    return result


def rerank_search(question, k=10, pool=20):
    """两阶段检索：先召回并集，再用 reranker 给每块打分，取前 k"""
    cands = candidates(question, pool)
    pairs = [(question, h["text"]) for h in cands]       # 每块和问题配成一对
    scores = reranker.predict(pairs, batch_size=16)      # 每对一个相关度分数
    order = scores.argsort()[::-1][:k]
    return [{**cands[i], "score": float(scores[i]), "via": "rerank"} for i in order]
```

下载新模型期间要先注释掉 `HF_HUB_OFFLINE`，下载完再恢复。

### 5.5 dev 结果

| 方法 | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |
|---|---|---|---|---|---|
| 语义（基线） | 31.9% | 49.5% | 59.3% | 70.3% | 43.1% |
| BM25 | 57.1% | 76.9% | 79.1% | 87.9% | 68.0% |
| **并集召回 + 重排** | **75.8%** | **85.7%** | **92.3%** | **94.5%** | **82.5%** |

| 召回 | 前 20 里有正确答案的比例 |
|---|---|
| BM25 前 20 | 91.2% |
| 语义 前 20 | 76.9% |
| **并集** | **95.6%** |

- **互补是真的**：并集比 BM25 前 20 多召回 4.4 个百分点（4 题），这 4 题是语义检索补上的。RRF 没把这个优势发挥出来，重排做到了
- **召回决定上限得到验证**：并集召回 95.6% 是天花板，重排 Hit@10 94.5% 几乎碰到天花板
- **离天花板还差多少**：Hit@3 85.7% 离 95.6% 差 10 个百分点，这是排序问题；剩下 4.4%（4 题）连召回都没进，重排帮不上

> **混合检索负责"多找到"，重排负责"排对顺序"。** RRF 想用一个公式同时做好两件事，在这份数据上没做到；拆成两个阶段分别处理，是目前 RAG 系统最常用的做法。

---

## 第六章 Bad case 分析

### 6.1 重排后没进前 3 的 13 题

```
q009 | 排名 4    | 这门课里有没有专门讲智能体性能评估的内容？
q025 | 排名 8    | 做那种容易出错、要求很严格的任务时，为什么不能让AI随便发挥，而要用脚本把格式固定住？
q026 | 排名 None | 为什么用AI做旅游攻略时，它给出的预算可能不太靠谱？
q041 | 排名 None | 第十章发布到 MCP 平台的天气查询 MCP 服务器，要求 Python 最低是什么版本？
q048 | 排名 4    | 在强化学习里，PBRFT 和 Agentic RL 的状态表示有什么不同？
q058 | 排名 5    | 第六章 AI 科普电子书案例里，描述要写哪本电子书的任务内容存在哪个变量里？
q059 | 排名 4    | 什么情况下用知识图谱比用向量数据库更合适？
q068 | 排名 None | 在给AI的提示里，用来定义它扮演什么角色、该怎么说话的那部分内容叫什么？
q071 | 排名 7    | 那种只靠解码器的模型，生成文字时是怎么一步步往下写的？
q075 | 排名 None | Transformer 架构里的自注意力机制到底有什么重要作用？
q081 | 排名 None | 在安卓手机上用程序模拟点屏幕和滑屏幕，一般是怎么发指令的？
q091 | 排名 4    | 大语言模型回答不确定的问题时容易瞎编，RAG是怎么减少这种情况的？
q097 | 排名 4    | 为什么用正弦余弦函数做位置编码，模型能更容易学到词和词之间的相对距离？
```

8 题已召回但排在 4~8 名（排序问题），5 题前 10 都没进。

### 6.2 逐题查看前 3 块

| 题 | 前 3 块 | 能否回答 | 结论 |
|---|---|---|---|
| q059 知识图谱 vs 向量库 | 3 块**全是标注的同一节**（Extra01 · 5.8），evidence 恰好在第 4 块 | "多跳推理""数据有强结构和关联"都在回答"什么场景用知识图谱" | **被冤枉** |
| q075 自注意力的作用 | Extra01 · 1.1"自注意力如何工作"，直接写着"并行计算能力……" | 和标注答案（第三章小结）讲同一件事，还更详细 | **被冤枉** |
| q091 RAG 怎么减少瞎编 | [1] 和标注**同一节**（Extra01 · 5.1），但这块讲知识更新、可追溯性 | 同节但没直说"减少幻觉" | 一半一半 |
| q097 正弦余弦位置编码 | [1] 和标注**同一节**（Extra01 · 1.2），[2] 第三章位置编码 | 都讲位置编码，关键点没看到 | 一半一半 |
| q068 定义角色的那部分叫什么 | prompt 示例、CAMEL 角色扮演、Coze 角色设定 | 沾边，没说出"系统提示词" | **真的没找好** |

### 6.3 原因：评测规则太严

评测集每题只标一句 evidence，但能回答问题的地方往往不止一处：

1. **同一节被切成几块**（q059、q091、q097）：evidence 只在其中一块，其他块也在回答同一个问题，却被判没找到
2. **不同章节讲同一话题**（q075）：面试题参考答案（Extra01）和正文经常讲同样的内容，讲得更详细的那块排在前面反而被判错

其他几类：

- **题目太宽泛**（q068、q075）：全书讲系统提示词、自注意力的地方很多
- **配置项难区分**（q041）：evidence 是 `requires-python = ">=3.10"`，书里好几个项目的 pyproject 几乎一样
- **真正的召回失败**（q026、q081）：问法和原文差别大

### 6.4 加一个"同节"指标，两个一起报

`find_rank` 的 `section=True`：和标注答案同文件同小节的块也算命中（代码见 3.7）。检索只跑一次，两种规则在同一份结果上打分。

| dev（91 题） | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |
|---|---|---|---|---|---|
| 重排（严格） | 75.8% | 85.7% | 92.3% | 94.5% | 82.5% |
| 重排（同节） | 83.5% | 93.4% | 95.6% | 96.7% | 88.7% |

- 严格那一行和之前完全一样，说明改 find_rank 没改坏
- Hit@3 多出的 7.7 个百分点（7 题），就是"同节别的块也能回答"被严格规则冤枉的
- **真实效果在两行之间**：严格偏低（冤枉了一些），同节偏高（同一节里也可能有不相关的块）。只报宽松的等于给自己放水，**两个一起报最诚实**
- 情况 2（不同章节讲同一话题）规则解决不了，要人工补充多个正确答案或用 LLM-as-a-Judge，列入遗留任务

### 6.5 Query 改写：本周不做

1. 并集只漏了 4 题，Query 改写主要改善召回，**最多只能救回这 4 题**
2. 剩下的大部分"错误"是评测规则造成的，改写查询解决不了
3. 每题多一次 DeepSeek 调用，增加 1~2 秒，叠加重排的延迟

写清楚"为什么没做"，本身就是有依据的工程决策。

---

## 第七章 test 集最终验证

### 7.1 结果

方案在 dev 上选定：**BM25 前 20 ∪ 语义前 20，再 bge-reranker 重排**。最后把基线和最终方案拿到 test 上各跑一次，并计时（`time.perf_counter()` 前后相减除以题数）。

```
test 共 32 题，可达 32 题
语义（基线）  严格  Hit@1 37.5%  Hit@3 59.4%  Hit@5 71.9%  Hit@10 78.1%  MRR 51.3%
语义（基线）  同节  Hit@1 56.2%  Hit@3 65.6%  Hit@5 81.2%  Hit@10 81.2%  MRR 63.5%
语义（基线）  平均每题 0.01 秒
BM25          严格  Hit@1 62.5%  Hit@3 75.0%  Hit@5 78.1%  Hit@10 84.4%  MRR 68.8%
BM25          同节  Hit@1 75.0%  Hit@3 78.1%  Hit@5 81.2%  Hit@10 87.5%  MRR 77.6%
BM25          平均每题 0.01 秒
重排（最终）  严格  Hit@1 75.0%  Hit@3 87.5%  Hit@5 93.8%  Hit@10 93.8%  MRR 82.1%
重排（最终）  同节  Hit@1 81.2%  Hit@3 90.6%  Hit@5 93.8%  Hit@10 96.9%  MRR 86.6%
重排（最终）  平均每题 10.40 秒
```

### 7.2 结论

**① 提升是真实的，不是碰巧适合 dev**

| 重排（严格） | dev | test |
|---|---|---|
| Hit@3 | 85.7% | 87.5% |
| MRR | 82.5% | 82.1% |

test 没参与任何选择，分数和 dev 几乎一样。

**② 方法之间的排序和 dev 一致**：BM25 明显好于语义，重排明显好于 BM25。

**③ 小样本要说明**：test 只有 32 题，1 题约 3.1 个百分点。语义基线在 test 上 Hit@3 是 59.4%，比 dev 的 49.5% 高 10 个百分点，就是小样本波动。比较时看**方法之间的差距**，不看绝对值。

**④ 延迟是严重问题**：重排每题 10.40 秒，是 BM25 的一千倍。再加上 DeepSeek 生成，用户要等 15 秒以上。原因：每题让 reranker 读三十多块、每块最多 512 token，且只在 CPU 上跑。

| 可选方向 | 代价 |
|---|---|
| 缩小候选池（每路前 10） | 召回率可能下降 |
| `max_length` 512 → 256 | 只读每块开头，准确度可能下降 |
| 换更小的 reranker | 准确度可能下降 |
| 用 GPU | 花钱 |

有了评测集，每个方向都能量化"省几秒、掉几分"，这是下周的第一件事。

### 7.3 简历写法

> 基于 Hello-Agents 教程（30 篇、2505 块）构建 RAG 问答。用 DeepSeek 批量出题并人工复核，自建 123 题检索评测集（dev 91 / test 32）。针对语义检索对代码与专有名词召回差的问题，设计 BM25 + 向量并集召回、bge-reranker 二阶段重排；test 集 Hit@3 59.4% → 87.5%，MRR 51.3% → 82.1%（test 仅 32 题）。实测 RRF 融合在该数据上不如单路 BM25，并定位重排带来 10 秒级 CPU 延迟作为后续优化目标。

---

## 第八章 RAG 切换到最终检索

`rag.py` 改两处：

```python
from week7.search import rerank_search      # 第 7 周评测最好的检索：并集召回 + 重排
...
    hits = rerank_search(question, k=3)      # 重排后取前 3 块交给模型
```

```
问题（直接回车退出）：ReAct 智能体为什么要设置最大步数？

【回答】
ReAct 智能体设置最大步数（`max_steps`）是为了防止无限循环 [3]。其核心循环会不断"格式化提示词 -> 调用LLM -> 执行动作 -> 整合结果"，直到任务完成或达到最大步数限制 [1]。

【出处】
[1] main/第四章 智能体经典范式构建.md > 4.2.3 ReAct 智能体的编码实现（相似度 0.9804）
[2] main/第四章 智能体经典范式构建.md > 4.2.4 ReAct 的特点、局限性与调试技巧（相似度 0.9141）
[3] main/第七章 构建你的Agent框架.md > 7.4.2 ReActAgent（相似度 0.8858）

总调用次数： 1
总输入token： 704
总输出token： 58
缓存命中token： 0
缓存命中率：0.0%
总花费：$0.000140
```

出处准确，引用编号和内容对得上。打印里的"相似度"应改为"重排分数"：sentence-transformers 的 `CrossEncoder` 对单分数模型默认加了 sigmoid，所以落在 0~1 之间，但它是 reranker 判断"这块能回答问题的可能性"，**不是余弦相似度**。

---

## 第九章 典型错误合集

> ⚠️ **本章所有标记 ❌ 的代码都是错误示范，请勿复制使用。**
> 按根因分类。标注"审查时发现"的是运行前看截图改掉的，写的是按代码推断的后果；有运行输出的照实收录。

### 根因一：缩进决定了代码属于哪一块（本周最高频）

---

**错误 1：跳过判断写在 for 循环外面**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def load_all_chunks(root, pattern="week*.md"):
    all_chunks = []
    if f.name == "SOURCE.md":          # f 还不存在
        continue                       # 不在循环里
    for f in sorted(root.glob(pattern)):
        ...
```

审查时发现：`f` 下面红线（变量未定义），`continue` 下面红线（continue 只能用在循环里，属于语法错误，整个文件跑不起来）。

**✅ 正确写法**：两行移到 for 里面的第一行。f 是每一轮取出来的那个文件，**只在循环里才有**。

---

**错误 2：`items.append` 缩进到了 for 外面**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
    for i, c in enumerate(picked, 1):
        ...
        if not q or ev not in body or not 15 <= len(ev) <= 60:
            ...
            continue

    items.append({"question": q, "evidence": ev, ...})   # ← 和 for 对齐，在循环外
    print(f"[{i}] ✓ {q}")
```

运行结果（试跑 5 块）：

```
[5] ✓ 处理高分辨率图像时，把大图切成小块分别编码再拼起来的方法有什么缺点？
出题 5 块：合格 1 题（dev 1 / test 0），跳过 0，不合格 0
```

**读输出**：5 块只打印了一行 `[5]`，合格 1、跳过 0、不合格 0，加起来不等于 5，4 块"凭空消失"。循环里每块都通过了校验，但结果没存，q、ev 被下一轮覆盖；循环结束后只 append 了一次，存的是最后一轮的值。

**线索**：`q`、`ev`、`c` 下面有小波浪线"可能在赋值前被引用"。**循环外用到了只在循环里定义的变量，几乎总是缩进错了。**

**✅ 正确写法**：整段按 Tab 缩进一级，和上面的 if 对齐。修好后 5 块全部 ✓，`合格 5 题，跳过 0，不合格 0`。

> 和第 6 周"收尾写进了 for 里面"正好相反：一个是不该在循环里的写进了循环，一个是该在循环里的写到了外面。

---

**错误 3：`if __name__` 缩进进了函数，排在 return 后面**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def evaluate(search_fn, items, k):
    ...
    return metrics, ranks

    if __name__ == "__main__":      # ← 多缩进一级，成了函数体的一部分
        items = ...
```

审查时发现：整个主程序显示成灰色（PyCharm 的"不可达代码"），`if __name__` 左边没有绿色运行三角。函数执行到 return 就结束，后面的代码永远不会运行。

**✅ 正确写法**：选中整段 `Shift+Tab`，让 `if` 顶格。

---

**错误 4：最后一段忘了补开头和结尾**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
    if piece:
        pieces.append(piece)          # 循环里是 [head] + piece + [tail]，收尾却没补
```

审查时发现。最后一段没有 ```` ``` ```` 包裹，模型分不清是代码还是正文，代码里的 `# 注释` 在 Markdown 里会变成一级标题，`in_code` 开关要防的问题又被放了出来。

**✅ 正确写法**：`pieces.append([head] + piece + [tail])`。**收尾要和循环里的打包做同样的事。**

---

**错误 5：`clean_text` 漏了一步，还没有 return**

审查时发现：第 ② 步删除零散 `<img>` 没写；函数末尾没有 `return text`。没有 return 的函数返回 None，`chunk_markdown` 里 `text = clean_text(text)` 拿到 None，下一行 `text.splitlines()` 会报 `AttributeError: 'NoneType' object has no attribute 'splitlines'`。

### 根因二：改代码时留下了旧代码

---

**错误 6：旧的检查拦住了新代码**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
    root = Path(__file__).parent.parent / "data" / "hello-agents-zh"   # 已改成语料目录
    md_files = sorted(root.glob("week*.md"))                            # 旧代码：在语料目录里找 week*.md
    ...
    if not md_files:
        print("没有找到 md 文件，检查文件是否在项目根目录")
        raise SystemExit                                                # 程序在这里就结束了
    all_chunks = load_all_chunks(root, "**/*.md")                       # 新代码永远走不到
```

运行结果：

```
找到 0 个文件：
没有找到 md 文件，检查文件是否在项目根目录

进程已结束，退出代码为 0
```

**✅ 正确写法**：删掉 md_files 和那段检查；要保留保护，就改成检查真正要用的东西 `if not all_chunks:`。

---

**错误 7：新 try 替换掉了旧 try，旧调用却没删**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
        msgs = [...]
        content, usage = ask_llm(msgs, json_mode=True)    # 旧的，没有保护
        tracker.record("deepseek-flash", usage)

        try:
            content, usage = ask_llm(msgs, json_mode=True)  # 新的，有保护
        except (httpx.HTTPError, RuntimeError) as e:
            ...
        tracker.record("deepseek-flash", usage)

        if item.get("skip"):        # item 红线：json.loads 那段 try 被整段替换掉了
```

审查时发现：每块调用两次 API，花费翻倍；第一次调用断网仍会崩溃，新加的保护等于没起作用；`item` 未定义。

**✅ 正确写法**：两段 try 都要有，顺序是先调用（保护"打电话"）、记账、再解析（保护"读答卷"）。

---

**错误 8：替换判断时把 for 也删了，还照抄了别的函数的变量名**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
def split_paragraphs(lines):
    ...
    paras = []
                                             # ← for line in lines: 被一起删掉了
        new_fence = update_fence(line, fence)
        if new_fence != fence:
            fence = new_fence
            buf.append(line)                 # split_paragraphs 里没有 buf，应该是 para
            continue
        if not in_code and line.strip() == "":   # in_code 已改名为 fence
```

审查时发现：满屏红线。`line` 和 `continue` 同时有红线，说明代码已经不在循环里。

**✅ 正确写法**：补回 `for line in lines:`；`buf` → `para`；`not in_code` → `not fence`。改完用 `Ctrl+F` 搜 `in_code`，整个文件一处不剩。

---

**错误 9：`ask_llm` 里残留的 `print(response.text)`**

把状态码检查改成 raise 时，原来 if 里的 `print(response.text)` 留了下来，还缩进到了 if 外面。审查时发现：每次调用成功都会打印整个原始 JSON，178 次调用会把进度行刷没。

---

**错误 10：改了字典键名，下面还在用旧名**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
    methods = {"语义": ..., "BM25": ..., "RRF 1:1": ..., "RRF 1:2": ..., "RRF 1:3": ...}
    ...
    for it, r in zip(reachable, all_ranks["RRF"]):
```

运行结果：

```
RRF 没找到的题：
Traceback (most recent call last):
  File "…\week7\eval_retrieval.py", line 63, in <module>
    for it, r in zip(reachable, all_ranks["RRF"]):
KeyError: 'RRF'
```

**✅ 正确写法**：改键名后搜一遍还有没有地方用着旧名字。

### 根因三：字符串和变量、导入和执行顺序

---

**错误 11：集合名写成了带引号的 `"COLLECTION"`**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
COLLECTION = "hello_agents"
client.delete_collection("COLLECTION")
col = client.create_collection(name="COLLECTION", metadata={"hnsw:space": "cosine"})
```

build_index 正常显示"集合里共有 2505 条记录"，评测脚本却报错：

```
chromadb.errors.NotFoundError: Collection [hello_agents] does not exist
```

临时打印集合列表：

```
数据库位置： D:\PythonProjects\ai-agent-learning\chroma_db
里面有这些集合： ['COLLECTION', 'notes']
```

**原因**：`"COLLECTION"` 带引号是一个字符串，内容就是这 10 个字母；不带引号才是变量。把写死的字符串换成常量时，最容易保留原来的引号（`"notes"` → `"COLLECTION"`）。**这个错误本身不报错**，只在另一个文件用正确的名字去找时才暴露。

**✅ 正确写法**：`client.create_collection(name=COLLECTION, …)`。更好的做法是集合名只定义一次，其他文件 import。

---

**错误 12：顶层代码调用了写在下面的函数**

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
bm25 = BM25Okapi([tokenize(d) for d in BM25_DOCS])   # 模块被导入时立即执行
...
def tokenize(text):                                    # 写在了下面
```

审查时发现：`tokenize` 红线，运行会报 `NameError`。函数之间互相调用不讲顺序（调用发生时都已定义好），但**顶层直接执行的代码，用到的东西必须写在它上面**。

---

**错误 13：两处同样的判断，只改了一处**

`chunk_markdown` 里一直是 `line.startswith("```")`，上周建议改成 `lstrip()` 兼容缩进代码块时只改了 split_paragraphs。两处同样的判断写了两遍，改一处漏一处；这次抽成 `update_fence` 函数统一。

### 根因四：程序的结构设计

---

**错误 14：批量任务里遇到网络错误直接 `sys.exit`**

全量出题跑到九十多块时：

```
网络错误： [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1082)

进程已结束，退出代码为 1
```

偶发断线，但 `ask_llm` 里 `sys.exit(1)` 终止了整个程序；保存文件在循环结束后才做，**前面已经出好的九十多道题全部丢失**。

**✅ 正确做法**：ask_llm 指数退避重试 3 次，仍失败就 `raise`；make_eval_set 里 try 包住调用，失败只跳过这一块。见 3.3、3.4。

---

**错误 15：同样的检索跑了两遍**

```python
# ❌❌❌ 低效写法 ❌❌❌
    for label, sec in [("重排（严格）", False), ("重排（同节）", True)]:
        metrics, _ = evaluate(rerank_search, reachable, K, section=sec)   # 重排 91 题，跑两遍
```

运行时卡在 `dev 共 91 题，可达 91 题` 半小时以上不动（程序在跑，只是打印要等整轮结束）。严格和同节用的是**同一份检索结果**，只是判断规则不同。

**✅ 正确做法**：检索跑一次存起来，两种规则在同一份结果上打分（test 集最终验证就是这样写的）。长任务里加一行进度：`print(f"\r  进度 {i}/{len(items)}", end="")`。

---

**小问题：用三引号 `"""` "注释掉"代码**

能运行，但被包住的代码里若有 docstring 的 `"""`，字符串会提前结束；别人也看不出这是禁用的代码。用 `Ctrl+/` 逐行加 `#`。

### 讲解方的错误与更正

| 我当时说的 | 实际情况 |
|---|---|
| 修嵌套代码块：在代码块里只有单独的 ```` ``` ```` 才算结束 | 只看了 Extra05，没在全量数据上验证，把用 4 反引号的第四、七、八、十二章弄坏（2505 → 2456）。改为按反引号个数判断 |
| `clean_text` 第 ③ 步先用 `\]\[` 全局替换 | 我当时就提示了副作用，但给出的就是这个写法；全量统计显示 `<sup>` 外有 38 处 `][`，会改坏 `matrix[0][1]` 这类代码。改为只在 `<sup>` 内部用函数替换 |
| 讲 RRF 时说"两路都认可的块更可靠"，让猜"权重加多少能超过 BM25" | 前提是两路水平相当；本周数据上怎么调都超不过 BM25 |
| reranker 分数"不是 0~1，可能是 -8 或 5" | `CrossEncoder` 对单分数模型默认加 sigmoid，落在 0~1；原始输出才是任意实数 |
| 估计重排评测"3 到 6 分钟" | 实测每题约 10 秒，dev 91 题一遍要十几分钟 |

---

## 第十章 本周自检

- [x] 能说清为什么要先建评测集，以及检索评测和答案评测的区别
- [x] 能解释评测集为什么记录 evidence 而不是 chunk id
- [x] 能手算 Hit@K 和 MRR，知道最后要对所有题取平均
- [x] 能解释 dev/test 划分的意义，知道"记住题目"的是调参的人而不是模型
- [x] 能用大模型批量出题，并说出出题 prompt 每条规则的用意
- [x] 知道必须用程序校验模型输出，以及空字符串 `in` 恒为 True 的陷阱
- [x] 能说出人工复核发现的几类坏题，特别是"题干就是 evidence"
- [x] 知道批量调用要重试、要先小批量试跑、工具函数应 raise 而不是 sys.exit
- [x] 能用正则清洗语料：非贪婪、DOTALL、MULTILINE、用函数做替换
- [x] 能说清文献编号 `[1]` 为什么会破坏引用标注和引用检查
- [x] 能拆分超长代码块并保证每段是完整代码块
- [x] 能按反引号个数正确处理嵌套代码块，知道修 bug 要全量验证
- [x] 能说出 BM25 的三个因素，解释 IDF 为什么能自动挑出专有标识符
- [x] 能手算 RRF，并解释为什么两路水平悬殊时 RRF 会变差
- [x] 能说清双塔和交叉编码器的结构差异，以及为什么只对召回结果重排
- [x] 知道两阶段检索的上限由召回决定，能用召回率验证
- [x] 能通过逐题查看检索结果判断是"检索错了"还是"评测冤枉了"
- [x] 知道为什么严格和宽松两个指标要一起报
- [x] 能在 test 集上做一次最终验证，并正确解读小样本的波动
- [x] 能说出重排带来的延迟和几种权衡方向

---

## 附录 A：检索评测速查

```python
# 命中判断：同文件 + 包含 evidence（section=True 时同小节也算）
rank = find_rank(hits, item, section=False)

# 指标
Hit@K = 排名不为 None 且 ≤ K 的题数 / 总题数
MRR   = Σ(1/排名) / 总题数              # 没找到的题贡献 0

# 召回率（两阶段检索的上限）
recall = 召回结果里含正确答案的题数 / 总题数

# 计时
t0 = time.perf_counter(); …; avg = (time.perf_counter() - t0) / n
```

**流程**：可达性检查 → dev 上比较方法 → 选定方案 → test 上跑一次 → 严格和同节两个数字一起报 → 附上延迟。

## 附录 B：本周新语法

| 语法 | 例子 | 说明 |
|---|---|---|
| 非贪婪 `.*?` | `<p>(.*?)</p>` | 遇到第一个结束位置就停 |
| `re.DOTALL` | `re.sub(…, flags=re.DOTALL)` | `.` 也匹配换行 |
| `re.MULTILINE` | `re.sub(r'^\[(\d+)\]', …, flags=re.MULTILINE)` | `^` 匹配每一行开头 |
| `re.sub` 传函数 | `re.sub(p, lambda m: …, s)` | 每处匹配用函数返回值替换 |
| `m.group(1)` | | 第 1 个括号抠出的内容 |
| `Path.relative_to` / `as_posix` | `f.relative_to(root).as_posix()` | 相对路径，统一正斜杠 |
| `**/*.md` | `root.glob("**/*.md")` | 递归匹配所有子文件夹 |
| `random.seed` / `sample` / `shuffle` | `random.sample(cs, n)` | 固定种子；不重复抽样；原地打乱（返回 None） |
| `dict.setdefault` | `groups.setdefault(k, []).append(c)` | 没有这个键就先放默认值 |
| `f"{n:03d}"` | `q001` | 补零到 3 位 |
| `except (A, B) as e` | | 一次捕获几种异常 |
| 单独的 `raise` | | 把刚捕获的错误原样抛出 |
| `range` + `break` 重试 | `for attempt in range(3): try: …; break` | 成功就跳出 |
| `time.perf_counter()` | | 精确计时 |
| 函数作参数 | `evaluate(bm25_search, items, K)` | 评测代码不随检索方法改动 |
| `lambda` 固定参数 | `lambda q, k: rrf_search(q, k, w_bm25=2)` | 造出签名匹配的新函数 |
| `ndarray.argsort()[::-1][:k]` | | 分数从高到低的前 k 个下标 |
| `{**d, "k": v}` | | 展开字典并覆盖部分键 |
| `metrics, _ = f()` | | 不需要的返回值用 `_` 接 |
| `print(…, end="")` 与 `\r` | `print(f"\r进度 {i}", end="")` | 同一行刷新进度 |

## 附录 C：提交记录

```
feat(week7): ingest Hello-Agents corpus - text cleaning, long code splitting, new collection
fix(week7): fence-length-aware code block detection; eval set generator
feat(week7): retrieval eval script, baseline Hit@5 59.3% / MRR 43.1% on 91 dev questions
feat(week7): BM25 + RRF hybrid retrieval; BM25 best on dev (Hit@5 79.1%, MRR 68.0%)
feat(week7): union recall + bge-reranker; dev Hit@3 49.5% -> 85.7%, MRR 43.1% -> 82.5%
feat(week7): section-level hit metric; rerank dev Hit@3 85.7% strict / 93.4% section
feat(week7): final test eval - rerank Hit@3 59.4% -> 87.5%, MRR 51.3% -> 82.1% (32 test qs), 10.4s/query
feat(week7): switch RAG pipeline to union recall + rerank
```

（以实际提交为准。）

---

## 遗留任务

- **重排延迟**（第 8 周第一件事）：缩小候选池、缩短 `max_length`、换小模型、上 GPU，每种都用评测集量化"省几秒、掉几分"
- **一题多答案**：给宽泛题补充多个正确出处，或用 LLM-as-a-Judge 判断"这块能否回答"，解决跨章节讲同一话题被误判的问题
- **答案层评测**：现在只评了检索，还没评最终回答的正确率
- **Query 改写**：本周有依据地未做（最多救回 4 题、增加延迟），延迟问题解决后再评估
- **块大小对比实验**（256 / 450 / 800）：每种都要重建索引、重跑重排，CPU 上太耗时
- **更强的 embedding 模型**：bge-small 是语义检索弱的主因之一，可试 bge-base / bge-m3
- **评测集扩充**：test 只有 32 题，误差大；扩到 150~200 题
- **清洗开关**：`clean_text` 是针对 Hello-Agents 设计的，对笔记库会误伤
- **配置集中**：集合名、数据库路径、模型名只定义一次，其他文件 import
- **第 4~6 周遗留**：滑动窗口、few-shot、工具参数预校验、tools 声明与 tool_map 统一

---

## 下周预告

第 8 周：**项目一收尾上线**。先解决 10 秒的重排延迟，再用 FastAPI 把 RAG 包成服务、做一个简单的聊天界面、Docker 打包部署，README 写清楚架构、技术选型理由和本周这张评测对比表。

从这周开始，每一次改动都有评测集兜底：改完跑一遍，就知道是变好还是变坏。
