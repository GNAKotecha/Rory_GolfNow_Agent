"""Sample deterministic calculation script.

Reads arguments from stdin as JSON and writes result to stdout as JSON.
"""
import json
import sys


def calculate(operation: str, a: float, b: float) -> float:
    """
    Perform simple calculations.

    Args:
        operation: Operation to perform (add, subtract, multiply, divide)
        a: First operand
        b: Second operand

    Returns:
        Calculation result

    Raises:
        ValueError: If operation is unknown or division by zero
    """
    operations = {
        "add": lambda x, y: x + y,
        "subtract": lambda x, y: x - y,
        "multiply": lambda x, y: x * y,
        "divide": lambda x, y: x / y if y != 0 else None,
    }

    func = operations.get(operation)
    if func is None:
        raise ValueError(f"Unknown operation: {operation}")

    result = func(a, b)

    if result is None:
        raise ValueError("Division by zero")

    return result


if __name__ == "__main__":
    try:
        # Read arguments from stdin
        args = json.loads(sys.stdin.read())

        # Validate required arguments
        if "operation" not in args or "a" not in args or "b" not in args:
            raise ValueError("Missing required arguments: operation, a, b")

        # Perform calculation
        result = calculate(
            args["operation"],
            float(args["a"]),
            float(args["b"])
        )

        # Write result to stdout
        print(json.dumps({"result": result}))

    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}), file=sys.stderr)
        sys.exit(1)

    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        print(json.dumps({"error": f"Unexpected error: {e}"}), file=sys.stderr)
        sys.exit(1)
