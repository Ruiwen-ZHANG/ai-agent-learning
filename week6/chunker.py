from pathlib import Path   # pathlib：用"对象"的方式处理路径，比拼字符串可靠

def make_chunk(path,lines,source):
    body = "\n".join(lines).strip()  # 拼接并去掉首尾空白，只做一次
    if body == "":
        return None
    else:
        return {
            "text": " > ".join(path) + "\n" + body,
            "source": source,
            "heading": path[-1] if path else "",
        }

def chunk_markdown(text, source):
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

            chunk = make_chunk(path, buf, source)
            if chunk is not None:
                chunks.append(chunk)
            buf = []

            path = path[:level - 1] + [title]
            continue

        buf.append(line)

    chunk = make_chunk(path, buf, source)
    if chunk is not None:
        chunks.append(chunk)
    return chunks

if __name__ == "__main__":
    root = Path(__file__).parent.parent        # __file__ 是 chunker.py 本身；parent 是 week6/，再一个 parent 是项目根目录
    md_files = sorted(root.glob("week*.md"))   # 匹配所有 week 开头、.md 结尾的文件，排序后按周次顺序处理

    # 4.1 先确认找到了文件
    print(f"找到 {len(md_files)} 个文件：")
    for f in md_files:
        print("  ", f.name)                    # .name 只取文件名，不要完整路径
    if not md_files:                           # 一个都没找到：后面的 max/min 会对空列表报错，直接退出
        print("没有找到 md 文件，检查文件是否在项目根目录")
        raise SystemExit

    # 4.2 逐个文件切块，合并到总列表
    all_chunks = []                            # 总卡片盒：所有文件的块都放这里
    for f in md_files:
        text = f.read_text(encoding="utf-8")   # 读出整篇文本，中文必须指定 utf-8
        chunks = chunk_markdown(text, f.name)  # 切块，source 传文件名
        print(f"{f.name}: {len(chunks)} 块")
        all_chunks.extend(chunks)              # extend：把块逐个倒进总列表（append 会把整个列表当一个元素）

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