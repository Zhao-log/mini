"""
测试 SessionManager.

覆盖场景:
  ✓ get_or_create 自动创建
  ✓ 不同 session 独立 messages
  ✓ 同 session 追加消息
  ✓ reset 清空但保留 trace
  ✓ delete 删除
"""

from src.sessions import SessionManager


def test_get_or_create():
    sm = SessionManager()
    s = sm.get_or_create("s1")
    assert s.session_id == "s1"
    assert sm.exists("s1")


def test_sessions_independent():
    sm = SessionManager()
    s1 = sm.get_or_create("window_1")
    s2 = sm.get_or_create("window_2")

    s1.add_message({"role": "user", "content": "窗口1的问题"})
    s2.add_message({"role": "user", "content": "窗口2的问题"})

    # 确认隔离
    assert len(s1.get_messages()) == 1
    assert len(s2.get_messages()) == 1
    assert "窗口1" in s1.get_messages()[0]["content"]
    assert "窗口2" in s2.get_messages()[0]["content"]


def test_same_session_accumulates():
    sm = SessionManager()
    s = sm.get_or_create("persistent")

    s.add_message({"role": "user", "content": "第一句"})
    s.add_message({"role": "assistant", "content": "第一次回答"})
    s.add_message({"role": "user", "content": "第二句"})

    assert len(s.get_messages()) == 3


def test_reset_clears_messages_keeps_trace():
    sm = SessionManager()
    s = sm.get_or_create("resettable")

    s.add_message({"role": "user", "content": "要清空的消息"})
    s.add_trace("这条 trace 应该保留")

    s.reset()

    assert len(s.get_messages()) == 0
    assert len(s.trace) >= 1  # reset 本身也会加 trace


def test_list_and_delete():
    sm = SessionManager()
    sm.get_or_create("a")
    sm.get_or_create("b")
    sm.get_or_create("c")

    assert sorted(sm.list_sessions()) == ["a", "b", "c"]

    sm.delete("b")
    assert sm.list_sessions() == ["a", "c"]
    assert not sm.exists("b")


def test_list_all():
    sm = SessionManager()
    info = sm.session_info()
    assert isinstance(info, list)
