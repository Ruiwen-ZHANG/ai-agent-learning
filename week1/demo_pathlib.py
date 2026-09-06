from pathlib import Path
# pathlib 是标准库，Path 是里面处理路径的类。
# 从此所有路径操作都用它，不再用字符串拼接。


# ==================== 第 1 步：定位脚本自己在哪 ====================

BASE_DIR = Path(__file__).resolve().parent
# 这一行是整个文件的地基，拆成三步理解：
#
# __file__          Python 自动提供的变量，值是当前这个 .py 文件的路径。
#                   注意它可能是相对路径，取决于你怎么启动程序。
#
# Path(__file__)    把那段文本变成 Path 对象，之后才能用 / 拼接、
#                   才能调用 .parent、.exists() 这些方法。
#
# .resolve()        转成绝对路径。它会把 "." ".." 这类相对成分展开，
#                   得到一条从盘符开始的完整路径。
#                   这一步是关键 —— 没有它，后面的路径依然可能受
#                   "从哪运行" 影响。
#
# .parent           取所在目录。demo_pathlib.py 的 parent 就是 week1 文件夹。
#
# 全大写是 PEP 8 的约定：表示这是常量，程序运行期间不会改变。

print("脚本自己:", Path(__file__))
print("绝对路径:", Path(__file__).resolve())
print("脚本目录:", BASE_DIR)
print("-" * 50)
# "-" * 50 把字符串重复 50 次，打印一条分隔线，让输出更好读。


# ==================== 第 2 步：创建 data 目录 ====================

DATA_DIR = BASE_DIR / "data"
# 用 / 运算符拼接路径。左边必须是 Path 对象，右边可以是字符串。
#
# 为什么用 / 而不是字符串加号：
#   1. 自动适配系统 —— Windows 输出反斜杠，Linux 输出正斜杠，你不用管
#   2. 自动处理多余的分隔符 —— 不会拼出 "data//file.txt"
#   3. 不受转义字符影响 —— 不用担心 \n \t 的问题
#
# 因为基于 BASE_DIR，所以 DATA_DIR 永远是 week1/data，
# 不管你从哪个目录启动程序。

DATA_DIR.mkdir(parents=True, exist_ok=True)
# 创建目录。两个参数都是必备的：
#
# parents=True     缺失的上级目录一并创建。
#                  比如要建 a/b/c，而 a 和 b 都不存在，
#                  不加这个参数会报 FileNotFoundError。
#
# exist_ok=True    目录已存在时不报错，当作成功。
#                  不加的话第二次运行就崩 FileExistsError。
#
# 记住：这两个参数基本上永远都要带。

print("data 目录:", DATA_DIR)
print("目录存在吗:", DATA_DIR.exists())
print("-" * 50)


# ==================== 第 3 步：写入三个文件 ====================

file_a = DATA_DIR / "a.txt"
file_b = DATA_DIR / "b.txt"
file_note = DATA_DIR / "note.md"
# 三个文件路径都从 DATA_DIR 拼出来，确保它们落在 data 目录里面。
#
# 对比错误写法：Path("a.txt") 是相对路径，
# 文件会掉在"运行时的当前目录"，而不是 data 里。

file_a.write_text("这是 a 文件的内容\n第二行内容", encoding="utf-8")
file_b.write_text("这是 b 文件的内容", encoding="utf-8")
file_note.write_text("# 笔记标题\n\n这是一份 Markdown 笔记。", encoding="utf-8")
# write_text 一次性写入整个文件，会【覆盖】原有内容。
#
# encoding="utf-8" 必须写！
# 不写的话 Windows 用系统默认编码（中文系统是 GBK），
# 后果：文件在其他系统上打开乱码，或者你自己用 utf-8 读时报错。
#
# 这个坑很隐蔽 —— 纯英文内容不会出问题，
# 只有出现中文时才暴露，所以要靠规则而不是靠观察。
#
# \n 是换行符，写进文件后就是真正的换行。

print("三个文件已写入")
print("-" * 50)


# ==================== 第 4 步：遍历目录，打印每个文件信息 ====================

print("遍历 data 目录:")
for item in DATA_DIR.iterdir():
    # iterdir() 列出目录下所有【直接子项】，不递归进子目录。
    # 每次循环拿到的 item 是一个 Path 对象，不是字符串。

    print(f"  文件名: {item.name}")
    # .name 完整文件名，含后缀，比如 "a.txt"

    print(f"  不带后缀: {item.stem}")
    # .stem 去掉后缀的名字，比如 "a"

    print(f"  后缀: {item.suffix}")
    # .suffix 后缀，【带点】，比如 ".txt"
    # 注意是 ".txt" 不是 "txt"，判断时别写错

    print(f"  是文件吗: {item.is_file()}")
    # is_file() 判断是不是普通文件（目录返回 False）

    print()
    # 空的 print() 输出一个空行，分隔每个文件的信息

print("-" * 50)


# ==================== 第 5 步：只列出 .txt 文件 ====================

print("只看 txt 文件:")
for txt_file in DATA_DIR.glob("*.txt"):
    # glob(模式) 按通配符匹配【当前层】的文件。
    # * 表示"任意多个任意字符"，所以 *.txt 匹配所有 txt 文件。
    #
    # 对比 rglob：会递归进所有子目录。
    # 这里 data 是平的没有子目录，用 glob 就够了。
    #
    # 其他常见模式：
    #   "*"          所有文件
    #   "test_*.py"  以 test_ 开头的 py 文件
    #   "*.md"       所有 markdown 文件

    print(f"  {txt_file.name}")
    # 只打印文件名，不打印完整路径，输出更清爽

print("-" * 50)


# ==================== 第 6 步：读取文件内容 ====================

content = file_a.read_text(encoding="utf-8")
# read_text 一次性把整个文件读成字符串。
# encoding 同样必须写，理由和写入时一样。
#
# 适合小文件。文件很大时应该用 open() 逐行读，
# 否则会一次性占用大量内存。

print("a.txt 的内容:")
print(content)
print("-" * 50)


# ==================== 第 7 步：读取前先检查（好习惯） ====================

missing = DATA_DIR / "不存在的文件.txt"

if missing.exists():
    print(missing.read_text(encoding="utf-8"))
else:
    print(f"文件不存在: {missing.name}")
    # 先检查再读，避免 FileNotFoundError 让程序崩掉。
    #
    # 这里用 print 而不是 raise，因为"文件可能不存在"
    # 在这个场景里是预期内的情况。
    # 如果这个文件是程序必需的配置，那就该 raise。