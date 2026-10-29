from pathlib import Path   # pathlib：用"对象"的方式处理路径，比拼字符串可靠
from pathlib import Path
import re

MAX_CHARS = 450   # 每块正文的字数上限；加上标题路径约几十字，总长控制在 500 左右
MAX_CODE = 1500

def clean_text(text):
    """切块前清洗语料：图片块换成[图注]，删除零散 <img>，<sup> 文献标注改写为（文献n）"""
    text = re.sub(r'<div align="center">.*?<p>(.*?)</p>.*?</div>', r'[\1]', text, flags=re.DOTALL)
    text = re.sub(r'<img[^>]*>', '', text)  # 删掉图片块之外剩下的零散 <img> 标签
    # 找到每个 <sup>…</sup>，取出里面所有数字，拼成（文献1,2）；<sup> 外面的内容完全不受影响
    text = re.sub(r'<sup>(.*?)</sup>',
                  lambda m: "（文献" + ",".join(re.findall(r"\d+", m.group(1))) + "）",
                  text)
    text = re.sub(r'</?strong>', '', text)  # <strong> 和 </strong> 都删掉，中间的文字保留
    text = re.sub(r'<br\s*/?>', ' ', text)  # <br>、<br/>、<br /> 换成空格
    lines = text.split("\n")  # 先拆成行
    new_lines = []
    for line in lines:
        if line.lstrip().startswith("|"):  # 表格行
            line = re.sub(r' {2,}', ' ', line)  # 连续 2 个以上空格 → 1 个
            line = re.sub(r'-{3,}', '---', line)  # 连续 3 个以上横线 → 3 个（表格分隔行至少要 3 个）
        new_lines.append(line)
    text = "\n".join(new_lines)  # 再拼回去
    text = re.sub(r'^\[(\d+)\]', r'文献\1.', text, flags=re.MULTILINE)
    return text


def make_chunk(path,lines,source):
    body = "\n".join(lines).strip()  # 拼接并去掉首尾空白，只做一次
    if body == "":
        return None
    else:
        return {
            "text": source + " > " + " > ".join(path) + "\n" + body,   # 文件名放在最前面，补上被章节标题覆盖的文档标题
            "source": source,
            "heading": path[-1] if path else "",
        }

def split_paragraphs(lines):
    """把一节的行按空行拆成段落；代码块内部的空行不拆"""
    in_code = False      # 这个函数自己的"引号模式"开关
    para = []            # 当前段落：正在积累的行
    paras = []           # 所有段落：每个元素是一个段落（行列表）

    for line in lines:
        # 遇到 ``` 切换开关，这一行属于当前段落
        if line.lstrip().startswith("```"):
            in_code = not in_code
            para.append(line)
            continue

        # 不在代码块里的空行：当前段落结束
        if not in_code and line.strip() == "":
            if para:                # 当前段落有内容才保存（连续两个空行时 para 是空的）
                paras.append(para)
            para = []               # 开始新段落
            continue                # 空行本身不保留

        # 其他行（正文，或者代码块内部的任何行，包括空行）：加进当前段落
        para.append(line)

    # 循环结束：最后一个段落后面可能没有空行，要手动保存
    if para:
        paras.append(para)

    return paras

def split_long_code(para, max_chars):
    """超长代码块在内部空行处拆开，每段补回开头行和结尾行；其他段落原样返回 [para]"""
    # 1. 不是代码块，或者没超长：原样返回只有一个元素的列表
    if not para[0].lstrip().startswith("```") or len("\n".join(para)) <= max_chars:
        return [para]

    # 2. 取出三部分
    head = para[0]       # 开头行，如 ```python
    tail = para[-1]      # 结尾行 ```
    body = para[1:-1]    # 中间的代码行
    # 3. 骨架的三个变量
    pieces = []          # 结果：拆出来的每一段
    piece = []           # 当前这一段的代码行
    size = 0             # 当前这一段的字数
    for line in body:
        # 4. 判断边界：size 达到上限，并且（这一行是空行，或者 size 达到 2 倍上限）
        if size >= max_chars and (line.strip() == "" or size >= 2 * max_chars):
            pieces.append([head] + piece + [tail])
            piece = []
            size = 0
            if line.strip() == "":
                continue

        # 5. 这一行放进当前段，size 加上这一行的长度 + 1（+1 是换行符）
        piece.append(line)
        size += len(line) + 1

    # 6. 收尾：最后一段不为空，也补上 head 和 tail 放进 pieces
    if piece:
        pieces.append([head] + piece + [tail])
    return pieces

def make_paras(buf):
    """一节的行 → 段落列表：先按空行拆段，再把超长代码块拆开"""
    paras = []
    for p in split_paragraphs(buf):
        paras.extend(split_long_code(p, MAX_CODE))   # extend：拆成几段就逐个加进来
    return paras

def pack(paras, max_chars):
    """把段落依次装进卡片，每张不超过 max_chars 字；单段超长就独占一张"""
    groups = []      # 结果：每个元素是一张卡片的所有行
    group = []       # 当前卡片
    size = 0         # 当前卡片已有的字数

    for para in paras:
        para_size = len("\n".join(para))     # 这一段的字数（把行拼回文本再数）

        # 当前卡片已经有内容，并且再加这一段就超了：换一张新卡片
        if group and size + para_size > max_chars:
            groups.append(group)
            group = []
            size = 0

        # 这一段装进当前卡片
        group.extend(para)      # extend：把这段的行逐个加进去
        group.append("")        # 段落之间补回一个空行，保持 Markdown 格式
        size += para_size

    # 最后一张卡片
    if group:
        groups.append(group)

    return groups

def chunk_markdown(text, source):
    text = clean_text(text)
    in_code = False
    path = []
    buf = []
    chunks = []

    lines = text.splitlines()
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
            buf.append(line)
            continue

        stripped = line.lstrip("#")
        if not in_code and line.startswith("#") and stripped.startswith(" "):
            level = len(line) - len(stripped)  # 去掉了几个 #，就是几级标题 → 2
            title = stripped.strip()  # 去掉空格 → "6.1 错误"

            # 先把这一节拆成段落，再装成卡片；一节可能变成好几块，标题路径都相同
            for group in pack(make_paras(buf), MAX_CHARS):
                chunk = make_chunk(path, group, source)
                if chunk is not None:
                    chunks.append(chunk)
            buf = []

            path = path[:level - 1] + [title]
            continue
        if not in_code and line.strip() == "---":
            continue

        buf.append(line)

    for group in pack(make_paras(buf), MAX_CHARS):
        chunk = make_chunk(path, group, source)
        if chunk is not None:
            chunks.append(chunk)
    return chunks

def load_all_chunks(root, pattern="week*.md"):
    """读取 root 目录下所有 week*.md 笔记，切块后合并返回"""
    all_chunks = []
    for f in sorted(root.glob(pattern)):
        if f.name == "SOURCE.md":
            continue
        text = f.read_text(encoding="utf-8")
        all_chunks.extend(chunk_markdown(text, f.relative_to(root).as_posix()))
    return all_chunks


if __name__ == "__main__":
    root = Path(__file__).parent.parent / "data" / "hello-agents-zh"   # 改成语料目录
    all_chunks = load_all_chunks(root, "**/*.md")  # 用 load_all_chunks 一次读完

    # 4.3 每块的长度（列表推导式）
    lengths = [len(c["text"]) for c in all_chunks]

    # 4.4 统计数字
    print("=" * 40)
    print(f"总块数：{len(all_chunks)}")
    print(f"最长：{max(lengths)} 字")
    print(f"最短：{min(lengths)} 字")
    print(f"平均：{sum(lengths) / len(lengths):.0f} 字")
    print(f"超过 500 字的块：{len([n for n in lengths if n > 500])} 个")   # 挑出大于 500 的再数个数

    # 4.5 最长的 5 块
    # 排序的是字典，Python 不知道字典怎么比大小，所以用 key 指定"按 text 的长度比"
    top5 = sorted(all_chunks, key=lambda c: len(c["text"]), reverse=True)[:5]
    print("=" * 40)
    print("最长的 5 块：")
    for c in top5:
        print(f"  {len(c['text'])} 字 | {c['source']} | {c['heading']}")   # f-string 里面用单引号，避免和外层双引号冲突

    # 4.6 打印一块样例，检查标题路径拼得对不对
    sample = all_chunks[min(10, len(all_chunks) - 1)]   # 取第 11 块；总块数不到 11 时取最后一块，防止越界
    print("=" * 40)
    print(f"样例（{sample['source']}）：")
    print(sample["text"])
    print("=" * 40)