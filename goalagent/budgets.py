"""Explicit null limits mean unlimited; finite budgets remain available for tests."""
import math


def valid_limit(value):
    return value is None or (type(value) is int and value > 0)


def limit(value):
    return math.inf if value is None else value


def visible_remaining(value):
    return None if math.isinf(value) else max(0, int(value))
