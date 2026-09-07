import asyncio
import time
import httpx


# ========== 所有协程函数定义在上面 ==========

async def hello():
    print("开始")
    await asyncio.sleep(1)
    print("结束")


async def task(name, seconds):
    print(f"{name} 开始")
    await asyncio.sleep(seconds)
    print(f"{name} 结束")


async def run_serial():
    """串行执行三个任务"""
    start = time.time()
    await task("A", 2)
    await task("B", 2)
    await task("C", 2)
    print(f"串行耗时: {time.time() - start:.2f} 秒")


async def run_concurrent():
    """并发执行三个任务"""
    start = time.time()
    await asyncio.gather(
        task("A", 2),
        task("B", 2),
        task("C", 2),
    )
    print(f"并发耗时: {time.time() - start:.2f} 秒")

async def fetch(client, url):
    r = await client.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


async def http_serial():
    start = time.time()
    async with httpx.AsyncClient() as client:
        await fetch(client, "https://httpbin.org/delay/2")
        await fetch(client, "https://httpbin.org/delay/2")
        await fetch(client, "https://httpbin.org/delay/2")
    print(f"HTTP 串行: {time.time() - start:.2f} 秒")


async def http_concurrent():
    start = time.time()
    async with httpx.AsyncClient() as client:
        await asyncio.gather(
            fetch(client, "https://httpbin.org/delay/2"),
            fetch(client, "https://httpbin.org/delay/2"),
            fetch(client, "https://httpbin.org/delay/2"),
        )
    print(f"HTTP 并发: {time.time() - start:.2f} 秒")


async def forget_await():
    print("调用但不 await:")
    asyncio.sleep(2)
    print("立刻就到这里了，根本没等")


async def bad_task(name, seconds):
    print(f"{name} 开始")
    time.sleep(seconds)
    print(f"{name} 结束")


async def blocking_demo():
    start = time.time()
    await asyncio.gather(
        bad_task("X", 2),
        bad_task("Y", 2),
        bad_task("Z", 2),
    )
    print(f"用了 time.sleep 的并发: {time.time() - start:.2f} 秒")

async def main():
    """总入口，按顺序跑各个演示"""
    await hello()
    print("-" * 30)
    await run_serial()
    print("-" * 30)
    await run_concurrent()
    await http_serial()  # ← 新增
    print("-" * 30)
    await http_concurrent()  # ← 新增
    print("-" * 30)
    await forget_await()  # ← 新增
    print("-" * 30)
    await blocking_demo()  # ← 新增


# ========== 唯一的入口放最后 ==========
asyncio.run(main())

