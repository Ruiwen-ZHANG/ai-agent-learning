class CostTracker:
    """统计多次 API 调用的 token 消耗与累计花费（区分缓存命中）"""

    def __init__(self):
        # 价格表：直接写成「每 token 的价格」，用的时候不用再除一百万
        # 按 deepseek-flash 低谷价计算，高峰期（工作日北京时间 9-12 点、14-18 点）实际价格翻倍
        self.price = {
            "prompt_hit": 0.003 / 1000000,     # 输入，缓存命中
            "prompt_miss": 0.15 / 1000000,     # 输入，缓存未命中
            "completion": 0.60 / 1000000,      # 输出
        }
        # 累计计数器：挂在 self 上，所有方法共享
        self.calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cache_hit_tokens = 0
        # 未命中数不单独存：未命中 = 总输入 - 命中，用减法现算，少一个对不上的可能

    def record(self, model, usage):
        """记录一次调用，usage 直接传响应里的那个字典"""
        self.calls += 1
        # 标准字段，各家 API 都有，用方括号取
        self.total_prompt_tokens += usage["prompt_tokens"]
        self.total_completion_tokens += usage["completion_tokens"]
        # DeepSeek 特有字段，换别家 API 时可能不存在，取不到按 0 算
        self.total_cache_hit_tokens += usage.get("prompt_cache_hit_tokens", 0)

    def cost(self):
        """返回累计花费（美元）"""
        miss_tokens = self.total_prompt_tokens - self.total_cache_hit_tokens
        cost_hit = self.price["prompt_hit"] * self.total_cache_hit_tokens
        cost_miss = self.price["prompt_miss"] * miss_tokens
        cost_completion = self.price["completion"] * self.total_completion_tokens
        return cost_hit + cost_miss + cost_completion

    def report(self):
        """打印统计报告"""
        print("总调用次数：", self.calls)
        print("总输入token：", self.total_prompt_tokens)
        print("总输出token：", self.total_completion_tokens)
        print("缓存命中token：", self.total_cache_hit_tokens)
        # 一次都没调用时总输入是 0，先判断再除，避免 ZeroDivisionError
        if self.total_prompt_tokens > 0:
            hit_rate = self.total_cache_hit_tokens / self.total_prompt_tokens
            print(f"缓存命中率：{hit_rate:.1%}")
        print(f"总花费：${self.cost():.6f}")


if __name__ == "__main__":
    # 用第 5 周第 1 节两次请求的真实 usage 验证，不调 API、不花钱
    u1 = {"prompt_tokens": 295, "completion_tokens": 38,
          "prompt_cache_hit_tokens": 128, "prompt_cache_miss_tokens": 167}
    u2 = {"prompt_tokens": 351, "completion_tokens": 8,
          "prompt_cache_hit_tokens": 128, "prompt_cache_miss_tokens": 223}

    tracker = CostTracker()
    tracker.record("deepseek-flash", u1)
    tracker.record("deepseek-flash", u2)
    tracker.report()
    # 期望：2 次 / 646 / 46 / 256 / 39.6% / $0.000087