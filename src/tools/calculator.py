"""
Calculator — 数学计算器工具。

安全实现: 用 ast.parse 解析表达式到 AST，只允许白名单节点类型，
避免 eval() 的任意代码执行风险。
同时限制递归深度和幂运算规模，防止恶意表达式造成 DoS。
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any

from . import Tool


# 允许的 AST 节点类型
_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,        # a + b, a - b, a * b, a / b, a // b, a % b, a ** b
    ast.UnaryOp,      # -a, +a
    ast.Constant,     # 常量（Python 3.8+，包含数字和字符串）
    ast.Name,         # 变量名（仅允许白名单变量）
    ast.Load,
    ast.Call,         # 函数调用（仅允许白名单函数）
)

# 允许的一元运算符
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# 允许的二元运算符
_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

# 允许的函数
_ALLOWED_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "sqrt": math.sqrt,
    "pow": pow,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
}

# 允许的常量
_ALLOWED_VARS = {
    "pi": math.pi,
    "e": math.e,
}

# 幂运算上限：防止 9**9**9 这类表达式造成 CPU/内存 DoS
_MAX_POW_EXPONENT = 1000
_MAX_POW_BASE = 10 ** 6

# AST 递归深度上限：防止超长链式表达式耗尽调用栈
_MAX_DEPTH = 200


def _safe_eval(node: ast.AST, depth: int = 0) -> Any:
    """递归求值 AST 节点."""
    if depth > _MAX_DEPTH:
        raise ValueError(f"表达式嵌套过深（上限 {_MAX_DEPTH} 层）")

    if not isinstance(node, _ALLOWED_NODES):
        raise ValueError(f"不支持的语法节点: {type(node).__name__}")

    if isinstance(node, ast.Expression):
        return _safe_eval(node.body, depth + 1)

    if isinstance(node, ast.Constant):
        value = node.value
        # bool 是 int 的子类，必须显式排除，否则 True + 1 会被当成 2
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"不支持的常量类型: {type(value).__name__}")
        return value

    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_VARS:
            return _ALLOWED_VARS[node.id]
        raise ValueError(f"不支持的变量: {node.id}（仅支持: {', '.join(_ALLOWED_VARS)}）")

    if isinstance(node, ast.UnaryOp):
        op_func = _UNARY_OPS.get(type(node.op))
        if not op_func:
            raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
        return op_func(_safe_eval(node.operand, depth + 1))

    if isinstance(node, ast.BinOp):
        op_func = _BINARY_OPS.get(type(node.op))
        if not op_func:
            raise ValueError(f"不支持的二元运算符: {type(node.op).__name__}")
        left = _safe_eval(node.left, depth + 1)
        right = _safe_eval(node.right, depth + 1)
        # 防止除零
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise ZeroDivisionError("除数不能为零")
        # 防止幂运算 DoS（如 9**9**9 会让进程长时间占满 CPU）
        if isinstance(node.op, ast.Pow):
            if abs(right) > _MAX_POW_EXPONENT:
                raise ValueError(f"指数过大（上限 {_MAX_POW_EXPONENT}），拒绝计算")
            if abs(left) > _MAX_POW_BASE:
                raise ValueError(f"底数过大（上限 {_MAX_POW_BASE}），拒绝计算")
        return op_func(left, right)

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("只允许直接调用函数名，不支持链式调用")
        func_name = node.func.id
        if func_name not in _ALLOWED_FUNCTIONS:
            raise ValueError(f"不支持的函数: {func_name}（仅支持: {', '.join(_ALLOWED_FUNCTIONS)}）")
        func = _ALLOWED_FUNCTIONS[func_name]
        args = [_safe_eval(a, depth + 1) for a in node.args]
        return func(*args)

    raise ValueError(f"未知节点类型: {type(node).__name__}")


def calculator_handler(expression: str) -> str:
    """计算器 handler."""
    if not expression or not expression.strip():
        raise ValueError("表达式不能为空")

    expr = expression.strip()

    # 用 ast.parse 解析（解析失败可能是 SyntaxError 或 ValueError）
    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, ValueError, MemoryError) as e:
        raise ValueError(f"表达式无法解析: {e}") from e

    # 安全求值（递归过深时给出受控错误，而不是让 RecursionError 冒泡）
    try:
        result = _safe_eval(tree)
    except RecursionError as e:
        raise ValueError("表达式过于复杂（递归过深），请拆分成更小的计算") from e

    # 格式化输出
    if isinstance(result, float):
        if result == int(result):
            return f"计算结果: {int(result)}"
        return f"计算结果: {result:.6g}"
    return f"计算结果: {result}"


# 工具定义
CALCULATOR_TOOL = Tool(
    name="calculator",
    description=(
        "数学计算器，安全求值数学表达式。"
        "支持 +, -, *, /, //, %, ** (幂), unary -, +, "
        "以及函数 abs(), round(), min(), max(), sqrt(), pow(), sin(), cos(), tan(), log()。"
        "常量 pi, e。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "要计算的数学表达式，如 '25 * 4 + 10'、'sqrt(16)'、'2 ** 10'",
            }
        },
        "required": ["expression"],
    },
    handler=calculator_handler,
)
