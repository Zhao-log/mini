"""
测试 ContextManager.

覆盖场景:
  ✓ 过滤掉 thought 字段
  ✓ 截断过长的 tool result
  ✓ 轮次截断（保留最近 N 轮）
  ✓ 超限压缩生成 summary
  ✓ 前插 system prompt
"""

from src.memory import ContextManager


def _make_messages(n: int, with_tool: bool = False) -> list[dict]:
    """生成 n 轮 user + assistant 消息."""
    msgs = []
    for i in range(n):
        msgs.append({"role": "user", "content": f"user question {i}"})
        msgs.append({
            "role": "assistant",
            "content": f"assistant answer {i}",
            "thought": f"我在思考问题{i}（这个应该被过滤掉）",
        })
        if with_tool:
            msgs.append({
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "content": f"tool result {i}",
            })
    return msgs


class TestContextFilter:
    def test_thought_removed(self):
        cm = ContextManager()
        msgs = [{
            "role": "assistant",
            "content": "回答",
            "thought": "思考过程（不该进 context）",
        }]
        filtered = cm._filter_messages(msgs)
        assert "thought" not in filtered[0]
        assert filtered[0]["content"] == "回答"

    def test_tool_result_truncated(self):
        cm = ContextManager()
        cm.TOOL_RESULT_MAX_LEN = 50
        long_result = "A" * 200
        msgs = [{"role": "tool", "content": long_result, "tool_call_id": "x"}]
        filtered = cm._filter_messages(msgs)
        assert len(filtered[0]["content"]) < 200
        assert "(截断" in filtered[0]["content"]

    def test_normal_messages_preserved(self):
        cm = ContextManager()
        msgs = _make_messages(3)
        filtered = cm._filter_messages(msgs)
        # thought 去掉了，但 role / content 保留
        for f in filtered:
            assert "role" in f
            assert "content" in f
            assert "thought" not in f


class TestContextTruncation:
    def test_round_truncation(self):
        cm = ContextManager()
        cm.MAX_ROUNDS = 3
        msgs = _make_messages(10)  # 10 轮 = 20 条
        truncated = cm._truncate_by_rounds(msgs)

        # 应该只保留最后 3 轮，远少于原始 20 条
        assert len(truncated) <= 8
        assert len(truncated) < len(msgs)

    def test_short_messages_not_truncated(self):
        cm = ContextManager()
        cm.MAX_ROUNDS = 20
        msgs = _make_messages(3)
        truncated = cm._truncate_by_rounds(msgs)
        assert len(truncated) == len(msgs)


class TestContextCompression:
    def test_compression_generates_summary(self):
        cm = ContextManager()
        # 造一堆消息让它压缩
        cm.MAX_CHARS = 500
        cm.COMPRESS_THRESHOLD = 400

        msgs = _make_messages(20)
        filtered = cm._filter_messages(msgs)
        truncated = cm._truncate_by_rounds(filtered)

        # 强制压缩
        compressed = cm._compress_early_messages(truncated)

        # 应该有一条 system summary
        assert any(m["role"] == "system" and "历史对话概要" in m["content"] for m in compressed)
        # 消息总数应该减少
        assert len(compressed) < len(truncated)


class TestBuildContext:
    def test_system_prompt_prepended(self):
        cm = ContextManager()
        msgs = [{"role": "user", "content": "hi"}]
        result = cm.build_context(msgs, system_prompt="You are a helpful assistant.")

        assert result[0]["role"] == "system"
        assert "helpful assistant" in result[0]["content"]

    def test_empty_messages(self):
        cm = ContextManager()
        result = cm.build_context([], system_prompt="sys")
        assert result == [{"role": "system", "content": "sys"}]

    def test_full_pipeline(self):
        """全流程: build_context 跑一遍，不抛异常."""
        cm = ContextManager()
        msgs = _make_messages(5, with_tool=True)
        result = cm.build_context(msgs, system_prompt="You are helpful.")

        # 前插了 system + 原始消息经过过滤/截断
        assert len(result) > 0
        assert result[0]["role"] == "system"
        # thought 都被过滤了
        for m in result[1:]:
            assert "thought" not in m


class TestTokenEstimation:
    def test_estimate_chars(self):
        cm = ContextManager()
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        chars = cm._estimate_chars(msgs)
        assert chars > 0
        assert chars < 1000
