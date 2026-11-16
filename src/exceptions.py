"""自定义异常."""


class AgentError(Exception):
    """Agent 运行时通用错误."""


class ToolNotFoundError(AgentError):
    """工具不存在."""


class ToolExecutionError(AgentError):
    """工具执行失败."""


class LLMParseError(AgentError):
    """LLM 输出解析失败."""


class SessionNotFoundError(AgentError):
    """Session 不存在."""
