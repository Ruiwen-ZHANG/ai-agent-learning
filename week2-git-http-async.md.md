# 从零学 AI Agent 开发：第 2 周技术总结（Git + HTTP + 异步）

> 16 周 AI Agent 学习计划的第二周记录。
> 上周补完了 Python 工程基础（类、类型注解、异常、pathlib/json/logging、环境管理），
> 这周解决三件事：代码怎么管、网络怎么通、怎么让请求并发起来。
>
> **本文最有价值的是第七章「典型错误合集」**——全是我自己撞出来的坑，
> 包括上周犯过、这周又犯了一遍的那几个。

---

## 目录

- 一、本周学了什么
- 二、Git 三区模型与本地操作
- 三、Git 远程与 GitHub
- 四、HTTP 基础
- 五、httpx 实战
- 六、async / await
- 七、⚠️ 典型错误合集（重点）
- 八、可复制模板库
- 九、本周规则清单
- 十、实测数据汇总

---

# 一、本周学了什么

| 模块 | 核心内容 | 后面用在哪 |
|---|---|---|
| Git 本地 | 三区模型、提交、diff、历史 | 代码有后悔药，改崩了能回退 |
| Git 远程 | 关联 GitHub、push/pull、合并 | 项目上线、给面试官看 |
| HTTP | 方法、状态码、请求/响应结构 | 调 API 的地基，看得懂报错 |
| httpx | 同步请求、超时、重试、连接复用 | 第 4 周直接用它调大模型 |
| async/await | 协程、事件循环、gather 并发 | Agent 并发调工具、流式返回 |

**学习方式和第 1 周一样**：讲完出题，然后独立写代码。这周有八项 httpx 练习和五个异步实验。

---

# 二、Git 三区模型与本地操作

## 2.1 Git 解决什么问题

在用 Git 之前，保留一个"能跑的版本"只能靠复制文件夹：`week1_备份`、`week1_备份2`、`week1_最终版`、`week1_最终版_真的最终`。

Git 解决五件事：

1. **时光机**——任何一次提交都能回退
2. **变更记录**——每一行代码何时改的、为什么改
3. **分支**——开个分支随便折腾，搞砸了删掉，主线不受影响
4. **协作**——多人改同一个项目，Git 负责合并
5. **学习证据**——GitHub 上连续的提交记录，比简历上任何一句话都有说服力

## 2.2 核心心智模型：三个区域

**理解 Git 的关键。你的文件同时存在于三个地方：**

```
工作区 (Working Directory)     你的书桌，摊着正在写的稿纸
   ↓  git add
暂存区 (Staging Area)          一个信封，你把要寄的几页挑进去
   ↓  git commit
本地仓库 (Repository)          寄出后的存档，每封都有编号和日期
   ↓  git push
远程仓库 (GitHub)              云端备份
```

### 为什么要有暂存区这个中间层

这是新手最困惑的地方——为什么不能一步到位？

假设你今天改了五个文件：三个是"实现新功能"，两个是"修复一个 bug"。

一次性全提交，历史记录里就是一坨"修改了一些东西"。以后想回退那个 bug 修复，会连新功能一起退掉。

有了暂存区，可以分两次提交：

```bash
git add 文件1 文件2 文件3
git commit -m "实现工具注册功能"

git add 文件4 文件5
git commit -m "修复 token 统计负数校验"
```

**暂存区让你控制"这一次提交包含哪些改动"。**

还有个实际好处：调试时加了一堆 `print`，同时也修了个真 bug。提交时只 `git add` 修 bug 的文件，调试代码留在工作区继续用，不污染历史。

## 2.3 核心命令

```bash
git init                    # 初始化仓库，生成 .git 文件夹
git status                  # 查看当前状态（最常用）
git add 文件名               # 添加单个文件到暂存区
git add .                   # 添加所有改动
git commit -m "说明"         # 提交
git log                     # 查看历史
git log --oneline           # 每次提交一行，更清爽
git diff                    # 工作区 vs 暂存区，看具体改了什么
git diff --staged           # 暂存区 vs 上次提交
```

**`.git` 文件夹里存着这个项目从第一次提交到现在的全部历史。** 删了它，所有记录就没了。

**养成习惯：不确定当前状态时就敲一遍 `git status`。** 它还会提示你下一步能做什么。

## 2.4 提交说明怎么写

这是面试官会看的细节。

```bash
# ❌ 无效的提交说明
git commit -m "修改"
git commit -m "update"
git commit -m "fix bug"

# ✅ 有效的提交说明
git commit -m "实现 ToolRegistry 工具注册与调用"
git commit -m "修复 _trim 未被调用导致历史不裁剪的问题"
git commit -m "为 call 方法添加 ToolExecutionError 异常包装"
```

**标准：看到这句话，能不能知道这次提交做了什么？**

这和第 1 周学的"错误信息必须带具体值"是同一个道理——**信息要能让人做判断**。

业界常用格式是加类型前缀（不强制，但显得专业）：

```
feat: 新增 token 统计功能
fix: 修复空列表求平均时的除零错误
docs: 补充 README 安装说明
refactor: 将 add_user/add_assistant 重构为统一的 add 方法
```

## 2.5 提交粒度

新手常见的两个极端：

```
❌ 太细：每改一行提交一次    → 历史被噪音淹没，找不到关键节点
❌ 太粗：一周的工作提交一次   → 想回退时只能整周退掉
```

**合理粒度是"一个完整的、可描述的改动"。**

**判断方法：如果你没法用一句话说清这次提交做了什么，粒度就有问题**——要么太杂（该拆开），要么太碎（该合并）。

## 2.6 读懂 git diff

一次实际的 diff 输出：

```
diff --git a/week1/token_counter.py b/week1/token_counter.py
index 70bd448..34babb4 100644
--- a/week1/token_counter.py
+++ b/week1/token_counter.py
@@ -109,4 +109,6 @@
 try:
     c.record("test", -1, 100)
 except ValueError as e:
-    print("捕获:", e)
\ No newline at end of file
+    print("捕获:", e)
+
+# 第 2 周复习：这个类用于统计 Agent 的 token 消耗
\ No newline at end of file
```

| 符号 | 含义 |
|---|---|
| `---` / `+++` | 旧版本 / 新版本的文件 |
| `@@ -109,4 +109,6 @@` | 从第 109 行开始，旧版 4 行、新版 6 行 |
| `-` 开头 | 删掉的行 |
| `+` 开头 | 新增的行 |
| 无符号 | 未改动的上下文，帮你定位 |

**这里有个值得注意的现象**：只加了一行注释，diff 却显示"删了一行又加了一行一模一样的"，提交结果是 `3 insertions(+), 1 deletion(-)`。

原因是 `\ No newline at end of file`——原文件最后一行末尾没有换行符，追加内容等于给那一行补上了换行。对 Git 来说，"末尾有换行"和"末尾没换行"是两个不同的行。

**良好实践：文件末尾留一个空行。** PyCharm 可以设置自动加：`设置` → `编辑器` → `常规` → 勾选"保存时确保文件末尾有换行符"。

## 2.7 .gitignore 的实战验证

第 1 周写了 `.gitignore` 但没法验证（项目还不是 Git 仓库）。这周终于用上了。

**验证方法**：`git init` 之后敲 `git status`，看该忽略的东西有没有出现。

我的实际输出：

```
Untracked files:
        .env.example        ✅ 模板，不含真实密钥，该提交
        .gitignore          ✅ 团队共享的规则，该提交
        requirements.txt    ✅ 依赖清单，该提交
        week1/              ✅ 代码
```

**`.env`、`.venv/`、`data/`、`__pycache__/` 一个都没出现——规则生效了。**

`week1/` 后面的斜杠表示整个目录。Git 在目录里所有文件都未跟踪时会折叠成一行，`add` 之后就展开成具体文件了。

## 2.8 PyCharm 的 Git 颜色标识

| 颜色 | 含义 |
|---|---|
| **红色** | 未被 Git 跟踪（新文件，从没 add 过） |
| **绿色** | 已 add 到暂存区，未 commit |
| **蓝色/青色** | 已跟踪，有未提交的修改 |
| **白色/默认** | 已提交，和仓库版本一致 |
| **灰色** | 被 `.gitignore` 忽略 |

**可以对照看一眼 `.env` 是不是灰色的**——直观确认忽略规则生效。

---

# 三、Git 远程与 GitHub

## 3.1 分布式意味着什么

这是最容易误解的概念。**"分布式"指的是每个人的电脑上都有一份完整的仓库，包含全部历史。**

**集中式（SVN）：**

```
服务器  ← 唯一的完整仓库，所有历史都在这里
  ↑
  ├── 你的电脑     ← 只有当前版本的文件，没有历史
  ├── 同事A        ← 同上
```

**分布式（Git）：**

```
GitHub  ← 一份完整仓库
  ↕
  ├── 你的电脑     ← 也是【完整】仓库，含全部历史
  ├── 同事A        ← 同上
```

带来四个实际差别：

**1. 断网也能工作。** `git init`、`add`、`commit`、`log` 全程不需要网络。只有 `push` 才需要。SVN 里提交、查历史、看 diff 全都要连服务器。

**2. 快。** `git log` 是读本地文件，瞬间出结果。

**3. 服务器挂了不丢数据。** GitHub 明天倒闭，你电脑上的 `.git` 里有完整历史，换个平台推上去就行。SVN 服务器硬盘坏了没备份，所有历史全部消失。

**4. 可以自由本地实验。** 想试个大改动？本地开分支折腾，提交十几次都行，不用推给任何人。

## 3.2 常用命令

```bash
git remote add origin https://github.com/用户名/仓库名.git    # 关联远程
git remote -v                                                # 查看已关联的远程
git branch -M main                                           # 分支改名
git push -u origin main                                      # 推送并记住对应关系
git pull origin main                                         # 拉取
```

**`origin` 是给远程仓库起的名字**，约定俗成，叫别的也行。

**`-u` 的作用是"记住这个对应关系"**，之后直接 `git push` 就行，不用再写后面的参数。

## 3.3 master 和 main

Git 早期默认分支叫 `master`，2020 年后 GitHub 改成了 `main`。如果你装的 Git 版本较老，本地会是 master，和 GitHub 对不上。

```bash
git branch -M main      # -M 强制重命名当前分支
```

## 3.4 --allow-unrelated-histories

### 它解决什么

Git 合并两个分支时，会先找**共同祖先**——两条线是从哪个提交分岔的。

正常情况：

```
        ┌── C ── D  (你的分支)
A ── B ─┤
        └── E ── F  (别人的分支)
        ↑
      共同祖先
```

有了共同祖先，Git 才知道"从 B 开始，你改了什么、他改了什么"。

**但如果本地和远程各自独立发展过：**

```
本地：  A ── B          （初始化项目、补充注释）
远程：  X ── Y ── Z      （在网页上建的 README、上传的笔记）
```

**两条线毫无关系，没有任何共同祖先。** Git 直接拒绝：

```
fatal: refusing to merge unrelated histories
```

`--allow-unrelated-histories` 就是告诉 Git："我知道它们无关，我确认要缝在一起。"

### 为什么默认不允许

**因为这几乎总是操作失误的信号。**

想象你 `git pull` 时手滑把远程地址写成了另一个项目。如果默认允许，那个不相干项目的所有文件会被合并进你的仓库，清理起来非常痛苦。

**Git 的设计哲学：危险操作必须显式确认。** 同类的还有 `--force`（强推覆盖远程）、`-D`（删除未合并的分支）。

**这和第 1 周的 `mkdir(exist_ok=True)` 是同一个思路**——默认严格，需要宽松时你得明确说出来。

### 什么时候会遇到

只有一个场景：**本地已有仓库，才去关联一个已有内容的远程仓库。**

**避免办法**：先在 GitHub 建仓库，然后 `git clone` 下来，在克隆的文件夹里写代码。这样从一开始就是同一条历史。

## 3.5 身份验证

**GitHub 从 2021 年起停止支持账号密码认证。**

第一次 push 时会弹出 `Connect to GitHub` 窗口，选 `Sign in with your browser`，浏览器授权一次即可。凭据保存在 Windows 凭据管理器里，以后不用再输。

另外两个选项：`Sign in with a code`（浏览器失败时的备选）、`Token`（服务器环境用）。

## 3.6 配置身份

```bash
git config --global user.name "你的GitHub用户名"
git config --global user.email "你的GitHub邮箱"
git config --global --list          # 验证
```

**邮箱必须和 GitHub 账号一致**，否则 GitHub 不会把提交算到你的账号上——主页上那些绿色贡献格子不会亮。

## 3.7 关于 Star / Watch / Fork

| 按钮 | 含义 |
|---|---|
| **Star** | 收藏 + 点赞。既是书签，也是项目影响力指标 |
| **Watch** | 关注更新，有新提交/issue 时收到通知 |
| **Fork** | 复制整个仓库到自己账号下，想改别人的项目时用 |

**新仓库 star 数是 0 很正常**——没有外部链接，不会有人偶然发现。学习记录类仓库的价值在于面试时能拿出来，和 star 数无关。

---

# 四、HTTP 基础

## 4.1 为什么必须懂

第 4 周调大模型 API 会遇到 `401`、`429`、`400`、`500` 这些数字。**不懂 HTTP，它们就是天书**，只能盲目试错。

而且 Agent 的工具调用大量是网络请求——搜索、查天气、调数据库 API，全走 HTTP。

## 4.2 无状态

```
客户端（你的代码）              服务器
      │  ── 请求 Request ──────────> │
      │  <───────── 响应 Response ── │
```

**一问一答，每次独立。服务器不记得你上一次问了什么。**

**这直接解释了一个现象**：为什么每次调用大模型都要把完整的 `messages` 历史重发一遍？因为 HTTP 无状态，服务器根本不记得你们之前聊过什么。

**`Conversation` 类存在的意义，就是在客户端维护这个"记忆"。**

## 4.3 请求的四个部分

```
POST /v1/chat/completions HTTP/1.1        ← ① 方法 + 路径
Host: api.deepseek.com                     ← ② 请求头
Authorization: Bearer sk-xxxxx
Content-Type: application/json
                                           ← 空行分隔
{"model": "deepseek-chat", ...}            ← ③ 请求体
```

### 请求方法

| 方法 | 语义 | 有请求体吗 | 数据放哪 |
|---|---|---|---|
| **GET** | **读取**数据 | 没有 | URL 的查询参数 |
| **POST** | **提交**数据 | 有 | 请求体 |
| PUT | 完整更新 | 有 | 请求体 |
| DELETE | 删除 | 通常没有 | — |

**GET 发的是"查询条件"，POST 发的是"要处理的内容"。** 两者都会有响应回来。

| 你发出去的 | 服务器返回 |
|---|---|
| GET `/user?id=123` | 123 号用户的信息 |
| GET `/search?q=python` | 搜索结果 |
| POST `/chat` + 对话历史 | 模型的回答 |

**为什么调大模型用 POST**：`messages` 可能有几千字，URL 塞不下；而且这是"提交一个任务"，不是"读取一个资源"。

### URL 结构

```
https://api.deepseek.com/v1/chat/completions?stream=true
└─┬─┘   └────────┬────────┘└───────┬───────┘ └────┬────┘
 协议         域名              路径          查询参数
 怎么传     哪台服务器      服务器上哪个功能    附加条件
```

**域名**决定去哪台机器（会被 DNS 解析成 IP 地址）。
**路径**决定用那台机器上的哪个功能。同一服务器可以有很多接口：

```
/v1/chat/completions    → 对话
/v1/embeddings          → 生成向量
/v1/models              → 列出可用模型
```

**这就是为什么路径写错返回 404**——服务器上没有那个功能。

### 查询参数的格式

`?键=值`，多个用 `&` 连接。**第一个用 `?`，后面全用 `&`。**

```
?city=北京&days=3&unit=celsius
```

### 请求头

```
Authorization: Bearer sk-xxxxx     ← 身份凭证，API Key 放这里
Content-Type: application/json     ← 告诉服务器"我发的是 JSON"
Accept: text/event-stream          ← 告诉服务器"我要流式响应"
```

**`Authorization: Bearer xxx` 这个格式要记住**，几乎所有 API 都用它传密钥。`Bearer` 是固定单词。

## 4.4 状态码

**按首位数字分类：**

| 首位 | 含义 | 记忆法 |
|---|---|---|
| 2xx | 成功 | 一切正常 |
| 3xx | 重定向 | 换个地址再试 |
| 4xx | **客户端错误** | **你的锅** |
| 5xx | **服务器错误** | **服务器的锅** |

**4xx 和 5xx 的区分极其重要**，它决定了处理方式：

- **4xx** → 重试没用，请求本身有问题，得改代码
- **5xx** → 可以重试，服务器可能只是临时抽风

### 高频状态码

| 码 | 名称 | 调 API 时的含义 | 重试有用吗 |
|---|---|---|---|
| **200** | OK | 成功 | — |
| **400** | Bad Request | **请求体**格式错（少字段、类型不对） | ❌ |
| **401** | Unauthorized | 密钥无效或没传 | ❌ |
| **403** | Forbidden | 密钥对，但没权限/余额 | ❌ |
| **404** | Not Found | **URL 路径**写错 | ❌ |
| **429** | Too Many Requests | **限流**，请求太频繁 | ✅ |
| **500** | Internal Server Error | 服务器内部错误 | ✅ |
| **502/503** | Bad Gateway / 不可用 | 服务器过载或维护 | ✅ |
| **504** | Gateway Timeout | 服务器处理超时 | ✅ |

**必须分清的两组：**

- **400 vs 404**：400 是**请求体**内容不对（少了 model 字段），404 是 **URL 路径**不对（`/completion` 少了个 s）
- **401 vs 403**：401 是"你是谁？"（没认证），403 是"我知道你是谁，但你不能干这个"（没授权）

**429 是 4xx 里的特例**——它的含义不是"你的请求错了"，而是"你请求太频繁了"。请求本身完全合法，只是时机不对，**所以等一等再发同样的请求会成功**。

### 遇到 4xx 一定要看响应体

光看状态码只知道"我错了"，不知道错在哪：

```json
{
  "error": {
    "message": "'model' is a required property",
    "type": "invalid_request_error",
    "param": "model"
  }
}
```

```python
if response.status_code != 200:
    print(f"状态码: {response.status_code}")
    print(f"响应体: {response.text}")     # 关键在这行
```

## 4.5 响应结构

大模型 API 的典型响应：

```json
{
  "choices": [
    {
      "message": {"role": "assistant", "content": "你好！有什么可以帮你的？"},
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
}
```

**取出回答要剥三层**：

```python
data["choices"][0]["message"]["content"]
#      ↑列表      ↑第0个  ↑字典      ↑最终内容
```

从左往右读：字典取 → 列表取 → 字典取 → 字典取。**第 1 周练的嵌套取值，这里就是实战。**

**为什么 `choices` 是列表**：可以让模型一次生成多个候选答案（参数 `n=3`）。默认只生成一个，所以永远取 `[0]`。

**`usage` 字段正是 `TokenCounter.record()` 需要的**：

```python
counter.record(
    "deepseek-chat",
    data["usage"]["prompt_tokens"],
    data["usage"]["completion_tokens"],
)
```

**第 1 周写的类，第 4 周就接上了。**

**原则：能直接读的字段，不要自己推算。** `total_tokens` 直接取，别用 prompt + completion 自己加——万一模型有额外的系统开销 token，你算的就是错的。

## 4.6 流式响应（SSE）

请求里加 `"stream": true`，服务器会持续推送数据块：

```
data: {"choices":[{"delta":{"content":"你"}}]}

data: {"choices":[{"delta":{"content":"好"}}]}

data: [DONE]
```

特点：每块以 `data: ` 开头，块之间空行分隔；内容在 `delta` 里而不是 `message` 里（delta = 增量）；最后一块是固定的 `data: [DONE]`。

你需要自己把碎片拼起来。第 4 周会写这个逻辑。

## 4.7 HTTP 与 TCP 的关系

**HTTP 是"说什么"，TCP 是"怎么把话送到"。**

```
你的代码          httpx.get(url)
   ↓
HTTP 层      "GET /data HTTP/1.1\r\nHost: ..."   ← 一段文本
   ↓
TCP 层       切成小包、编号、可靠传输
   ↓
IP 层        决定走哪条路由
```

**注意时间顺序和分层顺序不是一回事：**

```
1. TCP 握手（三次往返）      ← 此时还没有任何 HTTP 内容
2. 管道通了，才生成 HTTP 请求并发送
```

打电话的比喻：拨号、听到嘟嘟、对方接起 = TCP 握手（还没说话）；你开口说"我要订两份宫保鸡丁" = HTTP 请求。**你不可能在电话接通前说话。**

### TCP 负责的事

| 问题 | TCP 的处理 |
|---|---|
| 包丢了 | 没收到确认就重发 |
| 顺序乱了 | 每个包有编号，收方重排 |
| 发太快 | 流量控制，减速 |
| 数据损坏 | 校验和检测，丢弃重传 |

**这些 HTTP 完全不用操心**，它假定"我写出去的字节会原样到达"。

### 为什么这个知识有用

**1. 解释了连接复用的价值。** 三次握手要一来一回，跨国可能几百毫秒。HTTPS 还要多一层 TLS 握手（交换证书、协商密钥）。复用连接能省掉这些。

**2. 报错分层。**

```python
except httpx.ConnectError:
    # 网络不通、DNS 失败、服务器没开 —— 连 HTTP 请求都没发出去

except httpx.HTTPStatusError:
    # 请求发出去了，服务器也回了，只是回了个 404/500
```

**前者是"电话没打通"，后者是"打通了但对方说不行"。排查方向完全不同。**

---

# 五、httpx 实战

## 5.1 为什么用 httpx 不用 requests

`requests` 是最老牌的 HTTP 库，但**不支持异步**。而 Agent 要并发调工具、处理流式响应，异步是刚需。

httpx 的 API 和 requests 几乎一样，但同时支持同步和异步——**学一套用两处**。

## 5.2 基本用法

```python
import httpx

r = httpx.get("https://httpbin.org/get")

r.status_code      # 200
r.text             # 响应体（字符串）
r.json()           # 响应体解析成 Python 对象
r.headers          # 响应头
r.url              # 实际请求的完整 URL
```

`.json()` 内部就是 `json.loads(r.text)`——**第 1 周学的东西**。

**注意**：如果响应不是合法 JSON（比如返回了 HTML 错误页），`.json()` 会抛 `JSONDecodeError`。所以要么先检查状态码，要么用 try/except。

## 5.3 查询参数与 URL 编码

```python
r = httpx.get("https://httpbin.org/get",
              params={"city": "北京", "keyword": "AI Agent"})

print(r.url)
# https://httpbin.org/get?city=%E5%8C%97%E4%BA%AC&keyword=AI+Agent
```

**两个观察点：**

- 中文 `北京` → `%E5%8C%97%E4%BA%AC`（UTF-8 的 6 个字节，每个写成 `%十六进制`）
- 空格 → `+`（也可以是 `%20`，两种都合法）

**为什么必须转义**：假设你要搜索 `a&b`，不转义的话 URL 变成 `?q=a&b`，服务器会理解成"两个参数"。

而服务器解码后拿到的还是原文：

```python
'args': {'city': '北京', 'keyword': 'AI Agent'}
```

**这就是 `params=` 的价值**——手动拼字符串很容易在这里翻车。

## 5.4 json= 和 data= 的区别

```python
payload = {"model": "deepseek-chat", "temperature": 0.7}

httpx.post(url, json=payload)
# 请求体：{"model": "deepseek-chat", "temperature": 0.7}     ← JSON
# 自动加：Content-Type: application/json

httpx.post(url, data=payload)
# 请求体：model=deepseek-chat&temperature=0.7                ← 表单
# 自动加：Content-Type: application/x-www-form-urlencoded
```

**注意 `data=` 编码出来的格式和查询参数一模一样**，只是位置从 URL 挪到了请求体里。这是网页表单提交的传统格式。

**调大模型必须用 `json=`**，因为 `messages` 是**嵌套结构**（列表套字典）：

```python
"messages": [
    {"role": "system", "content": "你是助手"},
    {"role": "user", "content": "你好"},
]
```

**表单格式是扁平的 `key=value`，根本表达不了嵌套。** 用 `data=` 发过去，服务器会返回 400。

| 场景 | 用什么 |
|---|---|
| 调 API（现代 Web） | `json=` |
| 提交网页登录表单（传统 Web） | `data=` |

## 5.5 请求头与密钥

```python
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("API_KEY")

headers = {"Authorization": f"Bearer {api_key}"}
r = httpx.post(url, json=data, headers=headers)
```

**密钥绝不能放在 URL 里**：

```python
# ❌ 密钥会出现在浏览器历史、服务器日志、代理日志里
httpx.get(f"https://api.com/data?api_key={key}")

# ✅ 放在请求头
httpx.get("https://api.com/data", headers={"Authorization": f"Bearer {key}"})
```

**查询参数会被到处记录，请求体和请求头通常不会。**

## 5.6 超时

```python
r = httpx.get(url, timeout=10)
```

**不设的后果**：服务器不响应时程序会永远挂着。Agent 卡在某个工具调用上，整个任务停摆。

httpx 默认 5 秒，但**调大模型要设更长**（生成长文本可能几十秒）：

```python
timeout = httpx.Timeout(connect=5.0, read=60.0)
# connect: 建立连接最多等 5 秒（连不上就早点失败）
# read:    等响应最多等 60 秒（生成本来就久）
r = httpx.post(url, json=data, timeout=timeout)
```

**实测发现**：设 `timeout=2` 请求 `/delay/5`，实际耗时 3.44 秒而不是 2 秒。原因是 httpx 的 `timeout=2` 默认同时约束连接、读取、写入、连接池等待四个阶段，**各自 2 秒**。想精确控制就用 `httpx.Timeout(...)` 分别指定。

## 5.7 raise_for_status

**httpx 默认不会因为 404、500 抛异常**——它认为"我成功拿到了响应，只是内容是个错误"。

实测：

```python
r = httpx.get("https://httpbin.org/status/404", timeout=10)
print("状态码:", r.status_code)          # 404
print("程序还在跑，没有抛异常")            # 正常打印
```

`raise_for_status()` 的作用是：**如果状态码是 4xx 或 5xx，就抛出 `HTTPStatusError`**。

**这个设计是合理的**，因为有些场景 404 确实不是错误：

```python
r = httpx.get(f"https://api.com/user/{uid}")
if r.status_code == 404:
    return None        # 用户不存在，是正常的查询结果
```

**这正好对应第 1 周那道题**——"查询用户，用户不存在"该返回 None 而不是 raise。如果 httpx 强制把 404 变成异常，你就没法这么写了。

## 5.8 异常层次

```
httpx.HTTPError
├── httpx.RequestError          （请求发不出去）
│   ├── httpx.TimeoutException
│   ├── httpx.ConnectError      （连不上）
│   └── ...
└── httpx.HTTPStatusError       （请求成功了，但状态码是错误）
```

**捕获父类能接住所有子类**——第 1 周学的继承分层，第三方库也是这么设计的。

## 5.9 Client 复用连接

**实测数据（三次请求 httpbin.org）：**

```
独立请求 3 次: 5.35 秒
复用连接 3 次: 2.85 秒
```

**快了将近一倍。** 省下的 2.5 秒就是两次 TCP + TLS 握手的时间。

```python
with httpx.Client(
    base_url="https://api.deepseek.com",
    headers={"Authorization": f"Bearer {api_key}"},
    timeout=60,
) as client:
    r = client.post("/v1/chat/completions", json=data)
    #                ↑ 只写路径，base_url 自动拼上
```

**`httpx.get()` 内部其实是"创建临时 Client → 发请求 → 销毁"**，等价于：

```python
with httpx.Client() as tmp:
    tmp.get(url)
```

所以每次都要握手。**Agent 一个任务可能连续调十几次 API，每次省半秒，累积起来很可观。**

## 5.10 重试与指数退避

```python
import time
import httpx


def request_with_retry(url: str, max_retries: int = 3) -> dict:
    """带指数退避的请求。429 和 5xx 会重试，其他 4xx 直接抛出。"""

    for attempt in range(max_retries):
        try:
            r = httpx.get(url, timeout=10)

            # ① 可重试的错误：等一等，进入下一轮
            if r.status_code == 429 or r.status_code >= 500:
                wait = 2 ** attempt
                print(f"第 {attempt + 1} 次失败({r.status_code})，{wait} 秒后重试")
                time.sleep(wait)
                continue

            # ② 走到这里，说明不是可重试错误
            r.raise_for_status()      # 4xx 在这里抛出，【不重试】
            return r.json()           # 2xx 才能到这里

        except httpx.TimeoutException:
            wait = 2 ** attempt
            print(f"第 {attempt + 1} 次超时，{wait} 秒后重试")
            time.sleep(wait)
            # except 块执行完，本轮循环体自然结束，不用写 continue

    raise RuntimeError(f"重试 {max_retries} 次后仍失败: {url}")
```

**实测输出：**

```
第 1 次失败(503)，1 秒后重试
第 2 次失败(503)，2 秒后重试
第 3 次失败(503)，4 秒后重试
最终失败: 重试 3 次后仍失败: https://httpbin.org/status/503
```

### 三个设计要点

**1. 顺序：先判断可重试，再 raise_for_status。**

如果反过来，`raise_for_status()` 遇到 503 会立刻抛异常，下面的 `if` 判断永远执行不到。

**2. `2 ** attempt` 让等待时间翻倍（1、2、4 秒）。**

如果所有客户端都固定等 1 秒重试，会在同一时刻再次涌向服务器，把它压得更死。递增等待能分散压力。

**3. 只有 429 和 5xx 重试。** 其他 4xx 请求本身有问题，重试一万次也是同样的错。

### 一个可优化点

最后一次重试后还等了 4 秒才放弃——**这 4 秒是白等的**。真实项目里会加：

```python
if attempt < max_retries - 1:      # 不是最后一次才等
    time.sleep(wait)
```

---

# 六、async / await

本周最难的一节。

## 6.1 要解决的问题

Agent 要同时查三个工具：搜索、天气、数据库。

```python
result1 = search("Python")       # 等 2 秒
result2 = weather("北京")         # 等 2 秒
result3 = query_db("SELECT...")  # 等 2 秒
# 总共 6 秒
```

**但这三件事互不依赖，为什么要排队？**

## 6.2 关键认知：等待时 CPU 在干什么

同步代码执行 `httpx.get(url)` 时：

```
0.00s  发出请求
0.01s  ─┐
       │  等待服务器响应
       │  CPU 什么都没干，就在这儿干等
2.00s  ─┘
2.01s  收到响应，继续
```

**中间那 2 秒，CPU 完全空闲。** 它不是在计算，是在等网络。

**异步的核心思想：既然在等，为什么不去干别的？**

## 6.3 异步不是多线程

最容易误解的地方。**异步是单线程的，从头到尾只有一个线程在跑。**

用餐厅比喻：

| | 做法 |
|---|---|
| **同步** | 一个服务员：给 A 桌点单 → 站着等 A 吃完 → 给 B 桌点单 |
| **异步** | 一个服务员：给 A 点单 → 转身给 B 点单 → 再给 C 点单 → 谁吃完了去收谁的盘子 |
| **多线程** | 雇三个服务员，每人负责一桌 |

**异步始终只有一个服务员。它快，是因为不在等待上浪费时间，而不是因为人多。**

### 异步 vs 多线程的真正区别

| | 异步 | 多线程 |
|---|---|---|
| 线程数 | **1 个** | 多个 |
| 谁决定切换 | **你的代码**（`await` 处主动让出） | **操作系统**（随时可能打断） |
| 切换成本 | 极低（就是个函数跳转） | 较高（保存/恢复线程上下文） |
| 数据竞争 | 几乎没有 | 需要加锁，容易出 bug |

**核心差异是"协作式" vs "抢占式"：**

- **异步是协作式**：任务主动说"我要等了，你先去忙"（这就是 `await`）。不写 `await` 的地方绝不会被打断。
- **多线程是抢占式**：操作系统随时可能在任何一行代码中间切走。

**这解释了为什么异步几乎不需要加锁**：你能确定"两个 `await` 之间的代码是原子的"。多线程做不到这个保证。

> 注意：多线程也不会"傻等"——一个线程等网络时，操作系统会把 CPU 分给别的线程。所以多线程同样能提高 I/O 效率，只是开销更大、更容易出错。

### 为什么异步只对等待型任务有效

```python
async def compute():
    total = 0
    for i in range(100_000_000):     # 纯计算，没有 await
        total += i
    return total
```

这个函数**没有任何让出控制权的机会**，事件循环被它独占，其他任务全部冻结。用 `gather` 跑三个，总时间是三者相加。

**多线程能加速吗？** 也不能——Python 有 GIL，同一时刻只有一个线程能执行 Python 字节码。

| 任务类型 | 用什么 |
|---|---|
| 大量网络请求 | **异步**（最优） |
| 少量 I/O + 需要用同步库 | 多线程 |
| 纯计算（图像处理、大量数学运算） | 多进程 |

**Agent 的工作几乎全是网络等待**——等模型返回、等工具执行、等数据库查询。所以异步是最优解。

## 6.4 语法

### async def 定义协程函数

```python
def normal():
    return 1

async def coro():
    return 1

print(normal())      # 1
print(coro())        # <coroutine object coro at 0x...>  ← 不是 1！
```

**调用协程函数不会执行它**，只是创建一个"协程对象"——相当于一张写着"要做什么"的待办卡片，还没开始做。

### await 等待协程完成

`await` 有两层含义：

1. "我要等这个操作完成"
2. **"等待期间，你可以去执行别的任务"**

**第 2 点是关键。`await` 不是傻等，是主动让出控制权。**

### 三条硬规则

```python
# 规则 1：await 只能出现在 async def 里面
def normal():
    result = await fetch(url)     # ❌ SyntaxError

# 规则 2：调用协程函数必须加 await，否则什么也不会发生
async def main():
    fetch(url)                    # ❌ 创建了协程对象就扔了，请求根本没发
    await fetch(url)              # ✅

# 规则 3：最外层需要 asyncio.run() 启动
asyncio.run(main())
```

**`asyncio.run()` 是同步世界和异步世界的唯一入口。** 它创建事件循环、跑完 main、关闭循环。一个程序里通常只调用一次，在最外层。

### 什么时候加 await

```python
await client.get(url)        # ✅ 网络等待
await asyncio.sleep(2)       # ✅ 时间等待
await asyncio.gather(...)    # ✅ 等一批任务

r.raise_for_status()         # ❌ 不加，纯本地检查
r.json()                     # ❌ 不加，纯本地解析
len(results)                 # ❌ 不加
```

**标准：这个操作要不要等外部（网络、磁盘、时间）？** 要等就 await，纯计算就不用。

## 6.5 事件循环

可以把它想象成一个**调度员**：

```
事件循环手上有一堆任务：
  任务A：等网络响应
  任务B：等网络响应
  任务C：等网络响应

它不停轮询：
  A 好了吗？没有 → 看下一个
  B 好了吗？没有 → 看下一个
  A 好了！→ 执行 A 后面的代码
```

**`await` 就是任务对调度员说："我要等了，你先去忙别的，好了叫我。"**

## 6.6 只写 await 不会带来并发

```python
async def main():
    r1 = await fetch(url1)      # 等 2 秒
    r2 = await fetch(url2)      # 再等 2 秒
    r3 = await fetch(url3)      # 再等 2 秒
    # 总共还是 6 秒！
```

**每个 `await` 都在等上一个完成才开始下一个。** 这只是"用异步语法写同步逻辑"。

要并发，用 `asyncio.gather`：

```python
async def main():
    r1, r2, r3 = await asyncio.gather(
        fetch(url1),
        fetch(url2),
        fetch(url3),
    )
    # 总共 2 秒
```

**三个要点：**

1. **gather 里面的协程不加 `await`**——它们在这里只是被"创建"成协程对象，gather 负责等待
2. **返回值顺序和传入顺序一致**，不是谁先完成谁在前
3. gather 前面要加 `await`——等这一整批全部完成

```python
# ❌ 错误：加了 await 会先跑完再传进去，退化成串行
await asyncio.gather(
    await fetch(url1),
    await fetch(url2),
)
```

**并发多个同类任务时可以用解包：**

```python
await asyncio.gather(*[task(f"T{i}", 2) for i in range(10)])
```

`*[...]` 把列表里的 10 个协程展开成 10 个参数。**总时间还是 2 秒左右**——并发数几乎不增加耗时。

## 6.7 httpx 的异步用法

```python
import asyncio
import httpx


async def fetch(client: httpx.AsyncClient, url: str) -> dict:
    r = await client.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


async def main():
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            fetch(client, "https://httpbin.org/delay/2"),
            fetch(client, "https://httpbin.org/delay/2"),
            fetch(client, "https://httpbin.org/delay/2"),
        )
    print(f"拿到 {len(results)} 个结果")


asyncio.run(main())
```

三处变化：

| 同步 | 异步 |
|---|---|
| `httpx.Client()` | `httpx.AsyncClient()` |
| `with ... as client:` | `async with ... as client:` |
| `client.get(url)` | `await client.get(url)` |

**`async with` 是异步版的 with**，因为关闭连接本身也是可能要等待的操作（要等 TCP 挥手完成）。

### 为什么 client 从外面传进来

```python
# ❌ 每个 fetch 自己建 client
async def fetch(url):
    async with httpx.AsyncClient() as client:
        return (await client.get(url)).json()
# 三次调用 = 三个独立连接池 = 三次握手

# ✅ 共用一个
async def fetch(client, url):
    return (await client.get(url)).json()
```

**这叫"依赖注入"**——把函数需要的资源从外部传进来。好处是资源可以共享、测试时能传假对象、谁创建谁负责关闭职责清晰。

**注意 `client` 是形式参数，不需要提前定义。** 它的含义是"调用我的时候请给我一个 client"，真正的对象在调用时才传进来——和 `def add(a, b)` 里的 `a`、`b` 是一回事。

## 6.8 执行时间线

```
t=0.00  asyncio.run 启动事件循环
t=0.01  main 开始，创建 client
t=0.02  gather 提交三个协程
t=0.03  协程1 发出请求 → await，让出控制权
t=0.04  协程2 发出请求 → await，让出控制权
t=0.05  协程3 发出请求 → await，让出控制权
        （此刻三个请求都在路上，事件循环空闲轮询）
t=2.05  协程1 收到响应 → 继续执行
t=2.06  协程2 收到响应
t=2.07  协程3 收到响应
t=2.08  gather 收齐结果，返回
```

## 6.9 实测：打印顺序是最直观的证据

```
串行                    并发
A 开始                  A 开始
A 结束    ← 等 2 秒     B 开始    ← 没等，立刻
B 开始                  C 开始    ← 没等，立刻
B 结束    ← 等 2 秒     A 结束
C 开始                  B 结束
C 结束    ← 等 2 秒     C 结束
6.03 秒                 2.01 秒
```

**并发那组的三个"开始"挤在一起，就是因为 `await` 让出了控制权。**

而且 2.01 秒**恰好等于单个任务的时间**，不是 6 秒的三分之一——因为三个任务是**同时**在等的，总时间 = 最慢那个的时间。

## 6.10 陷阱：同步阻塞函数

**这是异步编程最常见的性能陷阱。**

```python
async def bad_task(name, seconds):
    print(f"{name} 开始")
    time.sleep(seconds)       # ❌ 同步阻塞
    print(f"{name} 结束")

await asyncio.gather(
    bad_task("X", 2),
    bad_task("Y", 2),
    bad_task("Z", 2),
)
```

**实测输出：**

```
X 开始
X 结束        ← X 完全跑完，Y 才开始
Y 开始
Y 结束
Z 开始
Z 结束
约 6 秒
```

**同样是 `asyncio.gather`，结果和串行一样。**

原因：`time.sleep(2)` 把整个线程钉死 2 秒。而异步只有一个线程，X 睡着的时候事件循环也跟着瘫痪，Y 和 Z 根本没机会启动。

**这个实验证明了：`gather` 本身不产生并发，并发来自协程内部的 `await` 让出控制权。** 如果协程里全是阻塞操作，gather 就是个摆设。

### 必须记死的对照表

| ❌ 同步阻塞 | ✅ 异步版本 |
|---|---|
| `time.sleep()` | `await asyncio.sleep()` |
| `requests.get()` | `await client.get()`（AsyncClient） |
| `open()` 读大文件 | `aiofiles` |
| 普通数据库驱动 | `asyncpg`、`aiomysql` |

**混用一个，整个事件循环就废了。** 代码看起来是异步的，实际跑起来还是串行。

## 6.11 陷阱：忘记 await

```python
async def forget_await():
    print("调用但不 await:")
    asyncio.sleep(2)          # 故意不加 await
    print("立刻就到这里了，根本没等")
```

Python 会给一个警告：

```
RuntimeWarning: coroutine 'sleep' was never awaited
```

**但有两个坑：**

**1. 是 Warning 不是 Error。** 程序照常跑完，退出码 0。日志刷得快的话你可能根本注意不到。

**2. 警告出现的位置和真正的错误位置对不上。** 实测中，这个警告延后了好几行才出现，混在下一个实验的输出中间。

原因：Python 是在**垃圾回收那个协程对象时**才发现"这玩意儿从来没被 await 过"，而垃圾回收时机不确定。

**教训：看到任何 `was never awaited` 警告都要立刻处理。**

---

# 七、⚠️ 典型错误合集

> **本章所有标注 ❌ 的代码都是错误示范，请勿复制。**
> 正确写法紧跟在每个错误之后，用 ✅ 标注。

这周的错误有个新特征：**术语混淆和望文生义**占了很大比例。上周的"缩进层级"和"顺序问题"也又犯了一遍。

## 7.1 【第 1 周犯 3 次，本周又犯】缩进与层级

### 现场：raise_for_status 和 return 跑进了 if 里

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
if r.status_code == 429 or r.status_code >= 500:
    wait = 2 ** attempt
    print(...)
        r.raise_for_status()      # ← 错误：在 if 内部
        return r.json()           # ← 错误：在 if 内部
```

后果：只有"可重试错误"才会执行 `raise_for_status` 和 `return`——正常的 200 响应反而什么都不做，直接进入下一轮循环。

```python
# ✅ 正确写法
if r.status_code == 429 or r.status_code >= 500:
    wait = 2 ** attempt
    print(...)
    time.sleep(wait)
    continue

r.raise_for_status()      # 和 if 平齐
return r.json()           # 和 if 平齐
```

### 现场：except 块内容没缩进

```python
# ❌❌❌ 错误示范 ❌❌❌
except httpx.TimeoutException:
wait = 2 ** attempt          # ← 没缩进，语法错误
print(...)
```

### 缩进层级图

写完一段嵌套代码，对着这张图核对一遍：

```
def request_with_retry(...):
    for attempt in ...:
        try:
            r = httpx.get(...)
            if 可重试:
                wait = ...
                continue
            r.raise_for_status()      ← 和 if 平齐
            return r.json()           ← 和 if 平齐
        except ...:                   ← 和 try 平齐
            wait = ...                ← 在 except 里面
    raise RuntimeError(...)           ← 和 for 平齐（循环外）
```

**四个层级：函数体 → for 体 → try 体 → if 体。**

## 7.2 【第 1 周犯 3 次，本周变形再犯】顺序问题

第 1 周是"配置在前，使用在后"（`basicConfig` 必须在第一条日志前、`load_dotenv` 必须在 `getenv` 前）。这周是同一个思维盲区的另一种表现。

```python
# ❌❌❌ 错误示范，请勿复制 ❌❌❌
r = httpx.post(...)
r.raise_for_status()                              # ← 503 在这里就抛异常了
data = r.json()
if r.status_code == 429 or r.status_code >= 500:  # ← 永远执行不到
    重试...
```

**`raise_for_status()` 遇到 503 会立刻抛出 `HTTPStatusError`，函数从这行跳走。**

```python
# ✅ 正确写法：先分流，再检查
r = httpx.post(...)

if r.status_code == 429 or r.status_code >= 500:   # ① 先看是不是可重试
    重试...
    continue

r.raise_for_status()                                # ② 不可重试的才抛
return r.json()                                     # ③ 成功才返回
```

**这三段的逻辑是"分流"**：可重试的走重试路径，不可重试的抛异常，成功的返回数据。**顺序不能颠倒。**

## 7.3 【犯了 2 次】400 判断成"地址错"

同一节课里犯了两次，第二次是在我纠正之后。

```
400 Bad Request: 'model' is a required property
```

**我的判断**：地址错了，服务器根本没这个功能。
**实际**：请求体里少了 `model` 这个必填字段，和地址无关。

| 码 | 问题在哪 | 例子 |
|---|---|---|
| **400** | **请求体**的内容 | 少必填字段、值类型不对、JSON 语法错 |
| **404** | **URL 路径** | `/v1/chat/completion` 少了个 s |

**根因是望文生义**——"Bad Request"听起来像"请求错了"，就联想成"地址请求错了"。

**教训：报错信息本身已经说清楚了（`'model' is a required property`），先读信息再下判断。**

## 7.4 术语混淆：async vs await

```
我的说法：gather 内部不加 async
正确说法：gather 内部不加 await
```

**两个关键字位置和作用完全不同：**

| 关键字 | 用在哪 | 作用 |
|---|---|---|
| `async` | **定义**函数时 | 声明这是协程函数 |
| `await` | **调用**时 | 等待协程完成，并让出控制权 |

```python
async def fetch(...):        # ← 定义用 async
    r = await client.get(url)  # ← 调用用 await
```

## 7.5 看错代码：以为少了 async，实际少了 await

```python
# ❌❌❌ 错误示范 ❌❌❌
async def fetch_all():
    r1 = client.get(url1)      # ← 少了 await
    r2 = client.get(url2)      # ← 少了 await
    return r1, r2
```

**我的判断**：定义异步函数前没加 async。
**实际**：`async def` 明明有，问题是调用时少了 `await`。

后果比"变成同步"更严重——**请求根本没有发出去**。返回的 `r1`、`r2` 是两个协程对象，不是响应。调用方写 `r1.json()` 会报：

```
AttributeError: 'coroutine' object has no attribute 'json'
```

```python
# ✅ 正确写法
async def fetch_all():
    r1, r2 = await asyncio.gather(
        client.get(url1),
        client.get(url2),
    )
    return r1, r2
```

## 7.6 答反：json= 和 data=

```
我的答案：调大模型 API 应该用 data
正确答案：必须用 json=
```

**根因也是望文生义**——`data` 听起来像"数据"，而 messages 就是数据，所以选了它。

实际上 `data=` 是发**表单**（`key=value&key=value`），`json=` 才是发 JSON。**嵌套的 messages 结构只有 JSON 能表达。**

## 7.7 多线程的错误理解

```
我的说法：多线程是多个 CPU 共同同步，各自干各自的，
         即使 CPU 空闲也直接继续等待，不会去干别的
```

**两处都错了：**

**1. 线程 ≠ CPU 核心。** 线程是操作系统的调度单位。你的电脑可能只有 8 个核心，但能同时跑几百个线程。

**2. 多线程也不会傻等。** 一个线程等网络时，操作系统会把 CPU 分给别的线程。多线程同样能提高等待型任务的效率。

**真正的区别是"谁来决定切换"**——异步是协作式（代码主动让出），多线程是抢占式（操作系统随时打断）。详见第 6.3 节。

## 7.8 用变量赋值代替 continue

```python
# ❌❌❌ 错误示范 ❌❌❌
for attempt in range(max_retries):
    if 需要重试:
        attempt = attempt + 1     # ← 想"跳到下一轮"，但这行毫无作用
```

**`for attempt in range(...)` 会自动管理 attempt 的值。** 每轮开始时 Python 把 0、1、2 依次赋给它，你手动改会被下一轮覆盖。

```python
# ✅ 正确写法
continue      # 立刻结束本轮，跳到下一轮
```

**`continue` vs `break`：** `continue` 是"这一轮结束，还有下一轮"，`break` 是"整个循环结束"。

## 7.9 算出等待时间却没等待

```python
# ❌❌❌ 错误示范 ❌❌❌
wait = 2 ** attempt
print(f"{wait} 秒后重试")
continue                  # ← 少了 time.sleep(wait)
```

**`wait = 2 ** attempt` 只是算出一个数字存进变量，程序不会因此暂停。** 要暂停必须调用 `time.sleep(wait)`。

**这和第 1 周"记录 ≠ 中断"是同一类问题**——把"描述一件事"当成了"做这件事"。

## 7.10 asyncio.run 位置在文件中间

```python
# ❌❌❌ 错误示范 ❌❌❌
async def hello():
    ...

asyncio.run(hello())      # ← 写在中间了

async def task(...):      # 后面还有函数定义
    ...
```

**`asyncio.run` 是程序的最终入口，应该放在文件最底部**——所有函数定义完之后。

而且不该每个演示都单独 `asyncio.run` 一次（技术上可以，但每次都要创建和销毁事件循环）。

```python
# ✅ 正确结构
# ===== 所有协程定义在上面 =====
async def hello(): ...
async def task(...): ...

async def main():
    """总入口，按顺序跑各个演示"""
    await hello()
    await task(...)

# ===== 唯一的入口放最后 =====
asyncio.run(main())
```

## 7.11 调用了未定义的函数

`main` 里写了五个 `await xxx()`，但那五个函数还没定义。PyCharm 全部标红。

**Python 的规则**：`def` 只是"记住这个函数"，不检查函数体里调用的东西存不存在；真正检查在**调用发生时**。

所以函数定义顺序不重要，但 **`asyncio.run(main())` 必须在最后**——执行到那一行时，所有函数都得已经定义好。

**惯例是"被调用的写在前面"**，因为读代码的人从上往下读。

## 7.12 URL 写死，没用函数参数

```python
# ❌❌❌ 错误示范 ❌❌❌
def request_with_retry(url: str, max_retries: int = 3) -> dict:
    r = httpx.post("https://httpbin.org/post", json=payload)
    #               ↑ 写死了，url 参数没用上
    #                                    ↑ payload 是外部变量，函数里不该直接用
```

**函数签名声明了 `url` 参数就要用它**，否则这个函数只能请求那一个固定地址，失去了通用性。

**而且 `payload` 是模块级变量**——函数能访问到，但这是坏习惯。函数应该只依赖自己的参数，不依赖外部环境。

## 7.13 环境类错误

### Git 没装就敲命令

```
git : 无法将"git"项识别为 cmdlet、函数、脚本文件或可运行程序的名称
```

**`CommandNotFoundException` 的三种原因，按顺序排查：**

| 原因 | 怎么判断 |
|---|---|
| 程序没装 | 最常见，装上就行 |
| 装了但不在 PATH 里 | 安装时选项选错，重装并注意 PATH 选项 |
| 装了但终端没重启 | 关掉终端重开，或重启整个 IDE |

**GitHub 账号和 Git 软件是两回事**——账号在网站上，Git 是装在你电脑上的工具。

**安装时唯一要注意的选项**是 `Adjusting your PATH environment`，保持默认的中间项（`Git from the command line and also from 3rd-party software`）。选第一项的话只能在 Git Bash 里用，IDE 终端里用不了。

### pip 装不上包

```
ERROR: Could not find a version that satisfies the requirement uv (from versions: none)
```

**`from versions: none` 说明"包索引里一个版本都没找到"**——uv 是成熟的包，PyPI 上肯定有，所以是网络问题。

一次性配好国内镜像：

```bash
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
pip config list      # 验证
```

之后所有 `pip install` 自动走清华源。

### Vim 退不出去

`git pull` 合并时会打开 Vim 让你写合并说明。

**退出方法**：按 `Esc` → 按 `Shift + ;` 打出冒号 → 输入 `wq` → 回车。

**几个坑：**

- **`Esc` 没有任何可见反应**——它只是切换内部模式，屏幕不会变。这是正常的
- 冒号要用 `Shift + ;`，直接按分号键出来的是 `;` 不是 `:`
- **输入法必须是英文**，中文的全角冒号 `：` Vim 不认

**万能逃生**：`:q!` 不保存强制退出。或者直接关掉终端标签页重开，然后 `git commit --no-edit`（用默认说明，不打开编辑器）。

**一劳永逸换掉编辑器**：

```bash
git config --global core.editor notepad
```

但 `:wq` 和 `:q!` 还是建议记住——**Linux 服务器上很多机器只装了 Vim**。

### PyCharm 运行了旧文件

改了代码，运行结果还是上一次的。看输出第一行的路径就知道跑的是哪个文件。

**原因**：绿色三角和 `Shift+F10` 执行的是**运行配置下拉框里当前选中的那个**，与你正在编辑哪个文件无关。

| 方式 | 操作 |
|---|---|
| 推荐 | 编辑区右键 → `运行 '当前文件名'` |
| 快捷键 | `Ctrl + Shift + F10`（运行当前文件） |

**`Shift + F10` 是"运行上次的配置"，`Ctrl + Shift + F10` 是"运行当前文件"。**

## 7.14 其他小错误

| 错误 | 说明 |
|---|---|
| `import time` 写在文件中间 | PEP 8 要求所有 import 集中在顶部 |
| 请求没设 `timeout` | httpx 默认 5 秒，国内访问国外服务常常不够 |
| `task` 函数缺打印 | 少了打印就观察不到串行/并发的顺序差异 |
| 文件名 `xxx.md.md` | 重命名时原文件已有后缀，又加了一次 |
| `git commit` 无内容 | 不是"发空包"，而是 Git 直接拒绝，提示 `no changes added to commit` |

---

# 八、可复制模板库

## 8.1 Git 日常四步

```bash
git status                          # 看看有哪些改动
git add .                           # 全部加入暂存区
git commit -m "描述这次改了什么"      # 提交到本地仓库
git push                            # 推送到 GitHub
```

⚠️ `-u` 参数设置过一次后，`push` 后面不用再写 `origin main`。
⚠️ 提交说明要能让人知道这次做了什么，"更新"、"修改"等于没写。

## 8.2 首次关联远程仓库

```bash
git init
git config --global user.name "用户名"
git config --global user.email "邮箱"

# 【先确认 .gitignore 已就位，再 add】
git status                          # 确认 .env、.venv 没出现

git add .
git commit -m "初始化项目"

git remote add origin https://github.com/用户名/仓库名.git
git branch -M main

# 只有远程已有内容时才需要这一步
git pull origin main --allow-unrelated-histories

git push -u origin main
```

⚠️ **`.gitignore` 必须在第一次 `git add` 之前就位**，它对已跟踪的文件无效。
⚠️ 邮箱要和 GitHub 账号一致，否则贡献格子不亮。

## 8.3 .gitignore（Python 项目）

```
# 环境变量（含密钥，绝不提交）
.env

# 虚拟环境
.venv/
venv/

# Python 缓存
__pycache__/
*.pyc

# IDE 配置
.idea/
.vscode/

# 日志和数据
*.log
data/
```

⚠️ 项目建好的第一件事就写它。
⚠️ `.gitignore` 和 `.env.example` 要提交，`.env` 不提交。
⚠️ 如果密钥已经提交过，唯一正确的补救是**去平台重新生成密钥，作废旧的**——历史提交里那份永远都在。

## 8.4 同步 HTTP 请求（完整防护）

```python
import httpx

try:
    r = httpx.get(url, params=query, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()
except httpx.TimeoutException:
    print("请求超时")
except httpx.HTTPStatusError as e:
    print(f"HTTP {e.response.status_code}: {e.response.text}")
except httpx.RequestError as e:
    print(f"网络错误: {e}")
else:
    print(data.get("result", "响应中没有 result 字段"))
```

⚠️ `timeout` 必须设，否则程序可能永远挂着。
⚠️ 遇到 4xx 一定要打印 `e.response.text`，光看状态码不知道错在哪。
⚠️ `else` 让"可能出网络错的代码"和"处理成功结果的代码"分开——**try 块要尽可能小**。

## 8.5 带重试的请求

```python
import time
import httpx


def request_with_retry(url: str, max_retries: int = 3) -> dict:
    """带指数退避的请求。429 和 5xx 会重试，其他 4xx 直接抛出。"""
    for attempt in range(max_retries):
        try:
            r = httpx.get(url, timeout=10)

            if r.status_code == 429 or r.status_code >= 500:
                wait = 2 ** attempt
                print(f"第 {attempt + 1} 次失败({r.status_code})，{wait} 秒后重试")
                time.sleep(wait)
                continue

            r.raise_for_status()
            return r.json()

        except httpx.TimeoutException:
            wait = 2 ** attempt
            print(f"第 {attempt + 1} 次超时，{wait} 秒后重试")
            time.sleep(wait)

    raise RuntimeError(f"重试 {max_retries} 次后仍失败: {url}")
```

⚠️ **顺序不能变**：先判断可重试 → 再 `raise_for_status` → 最后 return。
⚠️ 4xx（除 429）不重试，重试一万次也是同样的错。

## 8.6 连接复用（同步）

```python
with httpx.Client(
    base_url="https://api.deepseek.com",
    headers={"Authorization": f"Bearer {api_key}"},
    timeout=60,
) as client:
    r = client.post("/v1/chat/completions", json=payload)
```

⚠️ 实测三次请求：独立 5.35 秒 vs 复用 2.85 秒。
⚠️ `base_url` 设了之后只写路径即可。

## 8.7 异步并发请求

```python
import asyncio
import httpx


async def fetch(client: httpx.AsyncClient, url: str) -> dict:
    r = await client.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


async def main():
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            fetch(client, url1),
            fetch(client, url2),
            fetch(client, url3),
        )
    return results


asyncio.run(main())
```

⚠️ gather 里面的协程**不加 await**。
⚠️ `client` 从外面传进来共享连接池，不要每个 fetch 自己建。
⚠️ 协程里**绝不能出现 `time.sleep()`、`requests.get()` 等同步阻塞操作**，否则整个事件循环瘫痪。
⚠️ `asyncio.run()` 放在文件最底部，全程只调用一次。

## 8.8 pip 国内镜像

```bash
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

⚠️ 报 `from versions: none` 时几乎都是网络问题，不是包不存在。

---

# 九、本周规则清单

## Git

1. `.gitignore` 在写第一行代码之前就建好——它对已跟踪的文件无效
2. 提交说明要能让人知道做了什么；说不清就是粒度有问题
3. 一次提交 = 一个完整的、可描述的改动
4. 提交前用 `git diff` 检查自己到底改了什么
5. 密钥一旦提交过，唯一正确的补救是重新生成新密钥
6. Git 邮箱要和 GitHub 账号一致

## HTTP

7. 4xx 是你的锅（改代码），5xx 是服务器的锅（可重试）
8. 429 是 4xx 里的特例，请求合法只是太频繁，该重试
9. 400 是请求体错，404 是 URL 路径错
10. 遇到 4xx 一定要打印响应体，光看状态码没用
11. 调 API 用 `json=`，不用 `data=`
12. 密钥放请求头，绝不放 URL 查询参数
13. 能直接读的字段不要自己推算（如 `total_tokens`）

## httpx

14. 每个请求都要设 `timeout`
15. `raise_for_status()` 不会自动调用，要你主动调
16. 多次请求用 `Client` 复用连接，实测快近一倍
17. 重试逻辑的顺序：先判断可重试 → 再 raise_for_status → 最后 return
18. 指数退避（1、2、4 秒），不要固定间隔

## 异步

19. `async` 用于定义，`await` 用于调用——别混
20. 调用协程必须 `await`，否则请求根本不会发出
21. 只写 `await` 不产生并发，要用 `gather`
22. gather 里面的协程不加 `await`
23. **异步函数里绝不能有同步阻塞操作**（`time.sleep`、`requests`）
24. 异步只对等待型任务有效，纯计算用多进程
25. `asyncio.run()` 放最外层，只调用一次
26. 看到 `was never awaited` 警告立刻处理——它是 Warning 不是 Error

## 通用（上周延续）

27. 缩进层级写完要对着结构核对一遍
28. 顺序问题：配置在前、判断在前、`return` 之后的代码永远到不了
29. 报错信息本身已经说清楚了，先读信息再下判断
30. 术语要记准确——很多术语的字面意思和实际含义不一致

---

# 十、实测数据汇总

这周所有实验的真实数据，都是在同一台机器、同一网络环境下测的。

## 连接复用（同步，httpbin.org）

| 方式 | 3 次请求耗时 |
|---|---|
| `httpx.get()` 独立请求 | **5.35 秒** |
| `httpx.Client()` 复用连接 | **2.85 秒** |

省下的时间就是两次 TCP + TLS 握手。

## 超时精度

| 设置 | 实际耗时 | 说明 |
|---|---|---|
| `timeout=2` 请求 `/delay/5` | **3.44 秒** | httpx 的 timeout 同时约束四个阶段，各自 2 秒 |
| `timeout=10` 请求 `/delay/5` | 约 5 秒 | 正常拿到响应 |

**想精确控制用 `httpx.Timeout(connect=5.0, read=60.0)`。**

## 指数退避

```
第 1 次失败(503)，1 秒后重试
第 2 次失败(503)，2 秒后重试
第 3 次失败(503)，4 秒后重试
最终失败: 重试 3 次后仍失败
```

## 异步并发（asyncio.sleep 版）

| 方式 | 3 个 2 秒任务 |
|---|---|
| 串行（连续 await） | **6.03 秒** |
| 并发（gather） | **2.01 秒** |

**并发耗时恰好等于单个任务的时间**，因为三个任务同时在等。

## 异步并发（真实 HTTP 版）

| 方式 | 3 次 `/delay/2` |
|---|---|
| 串行 | **10.01 秒** |
| 并发（gather） | **4.20 秒** |

数字比 sleep 版大是因为有真实网络往返，但规律一致。

## time.sleep 的灾难

| 用什么 sleep | gather 3 个 2 秒任务 | 打印顺序 |
|---|---|---|
| `await asyncio.sleep(2)` | **2.01 秒** | 开始×3 → 结束×3 |
| `time.sleep(2)` | **约 6 秒** | 开始-结束-开始-结束-开始-结束 |

**同样是 gather，结果天壤之别。** 这组数据证明了：并发来自协程内部的 `await` 让出控制权，而不是 gather 本身。

---

# 十一、写在最后

## 这周最大的收获

**1. Git 的三区模型解释了一切。** 一开始觉得 `add` 和 `commit` 是多余的两步，理解了"暂存区让你控制这次提交包含什么"之后，所有命令的设计都变得合理了。

**2. HTTP 的术语必须记准确，不能望文生义。** 我在 400 上栽了两次，`json=`/`data=` 答反，都是因为按字面意思猜。这些是约定，不是能推理出来的。

**3. 异步的心智模型和同步完全不同。** 最关键的一句话是"`await` 不是傻等，是主动让出控制权"。理解了这个，才明白为什么 `time.sleep` 会毁掉整个事件循环。

## 关于反复犯的错

对比第 1 周的错误清单，有两类完全重复了：

- **缩进层级**（第 1 周 3 次，这周 2 次）
- **顺序问题**（第 1 周 3 次，这周 1 次，变形出现）

**说明这两个不是"知识点没学会"，而是"写代码时的习惯没建立"。**

针对性的做法：

- 写完嵌套代码，对着层级图从上往下核对一遍
- 每写一段有先后依赖的逻辑，问自己"这一步的前提条件都满足了吗"

## 下周计划

第 3 周：FastAPI + Docker。

- FastAPI：路由、Pydantic 数据模型、SSE 流式返回
- Docker：镜像与容器、写 Dockerfile、docker-compose

**Pydantic 是重点**——它是整个 AI 生态的基础设施，第 5 周做 Function Calling 时要用它校验模型返回的工具参数。而且它会把第 1 周学的类型注解真正"用起来"——那时注解只是给 IDE 看的，到 Pydantic 这里就变成了运行时的校验规则。

---

*本文是我从零学 AI Agent 开发的第 2 周记录，持续更新中。*
*第 1 周：Python 工程基础（类与对象、类型注解、异常处理、pathlib/json/logging、环境管理）*
