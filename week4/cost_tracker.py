
class CostTracker:
    def __init__(self):
        self.price={"prompt":0.15/1000000,"completion":0.60/1000000}
        self.calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def record(self,model,usage):
        self.calls += 1
        self.total_prompt_tokens += usage["prompt_tokens"]
        self.total_completion_tokens += usage["completion_tokens"]


    def cost(self):
        cost_prompt = self.price["prompt"] * self.total_prompt_tokens
        cost_completion = self.price["completion"] * self.total_completion_tokens
        cost_total = cost_prompt + cost_completion
        return cost_total

    def report(self):
        total_calls = self.calls
        print("总调用次数：",total_calls)
        total_prompt_tokens = self.total_prompt_tokens
        print("总输入token：",total_prompt_tokens)
        total_completion_tokens = self.total_completion_tokens
        print("总输出token:",total_completion_tokens)
        total_cost = self.cost()
        print(f"总花费: ${total_cost:.6f}")


if __name__ == "__main__":
    # 造一个假的 usage 字典测试，不用真的调 API
    fake_usage = {"prompt_tokens": 18, "completion_tokens": 21, "total_tokens": 39}

    tracker = CostTracker()           # 创建对象
    tracker.record("deepseek-flash", fake_usage)
    tracker.record("deepseek-flash", fake_usage)   # 记两次
    print(tracker.total_prompt_tokens)  # 应该是 36
    tracker.report()