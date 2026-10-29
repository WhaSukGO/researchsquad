"""Example agent-authored script tool: JSON stdin, compact JSON stdout."""
import json
import sys


def main():
    data = json.load(sys.stdin)
    if not isinstance(data, dict) or set(data) != {"values"}:
        raise ValueError("Expected an object containing values only")
    values = data["values"]
    if not isinstance(values, list) or len(values) > 10000:
        raise ValueError("Expected at most 10000 integers")
    if any(type(value) is not int for value in values):
        raise ValueError("Every value must be an integer")
    print(json.dumps({
        "count": len(values),
        "duplicate_count": len(values) - len(set(values)),
    }))


if __name__ == "__main__":
    main()
