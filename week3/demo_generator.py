def counter():
    print(">>> 开始")
    yield 1
    print(">>> 中间")
    yield 2
    print(">>> 结束")


g = counter()
print("创建生成器后，还没执行任何代码")
print("第一次 next:", next(g))
print("第二次 next:", next(g))