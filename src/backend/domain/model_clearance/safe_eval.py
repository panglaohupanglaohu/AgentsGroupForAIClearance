# -*- coding: utf-8 -*-
"""T304 — AST-whitelist expression evaluator without eval/exec."""

from __future__ import annotations

import ast
from typing import Any, Dict


class SafeEvalError(Exception):
    pass


_ALLOWED_OPERATORS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: lambda a, b: a is b,
    ast.IsNot: lambda a, b: a is not b,
}

_ALLOWED_UNARY = {
    ast.Not: lambda a: not a,
    ast.USub: lambda a: -a,
    ast.UAdd: lambda a: +a,
}


def _eval_node(node: ast.AST, context: Dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, context)

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id in context:
            return context[node.id]
        if node.id == "True":
            return True
        if node.id == "False":
            return False
        if node.id == "None":
            return None
        raise SafeEvalError(f"Undefined variable in expression: {node.id}")

    if isinstance(node, ast.Attribute):
        val = _eval_node(node.value, context)
        if isinstance(val, dict):
            return val.get(node.attr)
        return getattr(val, node.attr, None)

    if isinstance(node, ast.Subscript):
        val = _eval_node(node.value, context)
        slice_val = _eval_node(node.slice, context)
        if isinstance(val, (dict, list, tuple)):
            try:
                return val[slice_val]
            except Exception:
                return None
        return None

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, context)
        for op, comparator in zip(node.ops, node.comparators):
            op_type = type(op)
            if op_type not in _ALLOWED_OPERATORS:
                raise SafeEvalError(f"Disallowed comparison operator: {op_type.__name__}")
            right = _eval_node(comparator, context)
            if not _ALLOWED_OPERATORS[op_type](left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for v in node.values:
                if not _eval_node(v, context):
                    return False
            return True
        if isinstance(node.op, ast.Or):
            for v in node.values:
                if _eval_node(v, context):
                    return True
            return False
        raise SafeEvalError(f"Unsupported boolean operator: {type(node.op).__name__}")

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_UNARY:
            raise SafeEvalError(f"Disallowed unary operator: {op_type.__name__}")
        operand = _eval_node(node.operand, context)
        return _ALLOWED_UNARY[op_type](operand)

    if isinstance(node, ast.List):
        return [_eval_node(e, context) for e in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(e, context) for e in node.elts)

    raise SafeEvalError(f"Disallowed AST node in expression: {type(node).__name__}")


def safe_eval(expr: str, context: Dict[str, Any]) -> bool:
    """Safely evaluate an expression returning a boolean condition."""
    if not expr or not expr.strip():
        return False
    try:
        parsed = ast.parse(expr.strip(), mode="eval")
        res = _eval_node(parsed, context)
        return bool(res)
    except Exception as exc:
        raise SafeEvalError(f"Failed to evaluate expression '{expr}': {exc}") from exc
