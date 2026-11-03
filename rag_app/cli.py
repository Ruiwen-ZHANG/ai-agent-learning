"""命令行问答：在终端里连续提问，直接回车退出"""
from rag_app.retriever import Retriever
from rag_app.rag import answer
from common.cost_tracker import CostTracker

if __name__ == "__main__":
    print("正在加载模型……")
    retriever = Retriever()                         # 只创建一次，后面所有问题共用
    tracker = CostTracker()

    while True:
        q = input("\n问题（直接回车退出）：").strip()
        if not q:
            break
        result = answer(q, retriever, tracker)

        print("\n【回答】")
        print(result["answer"])
        print("\n【出处】")
        for i, s in enumerate(result["sources"], 1):
            print(f"[{i}] {s['source']} > {s['heading']}（重排分数 {s['score']:.4f}）")
        if result["bad_citations"]:
            print(f"⚠ 回答中出现了不存在的编号：{result['bad_citations']}")

    tracker.report()