"""Simple built-in tools that don't require external services."""
from typing import Dict, Any, List
import logging
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class MemoryStore:
    """Simple in-memory key-value store for agent memory."""

    def __init__(self):
        self._store: Dict[str, Any] = {}

    def store(self, key: str, value: str) -> str:
        """Store a value."""
        self._store[key] = {
            "value": value,
            "stored_at": datetime.utcnow().isoformat()
        }
        logger.info(f"Stored key: {key}")
        return f"Stored '{key}' successfully"

    def retrieve(self, key: str) -> str:
        """Retrieve a value."""
        if key in self._store:
            data = self._store[key]
            logger.info(f"Retrieved key: {key}")
            return f"Value: {data['value']} (stored at {data['stored_at']})"
        else:
            return f"Key '{key}' not found"

    def list_keys(self) -> str:
        """List all stored keys."""
        if not self._store:
            return "No keys stored"
        keys = list(self._store.keys())
        return f"Stored keys: {', '.join(keys)}"


class Calculator:
    """Simple calculator for arithmetic operations."""

    @staticmethod
    def calculate(expression: str) -> str:
        """
        Safely evaluate a mathematical expression.

        Args:
            expression: Math expression (e.g., "2 + 2", "10 * 5")

        Returns:
            Result as string
        """
        try:
            # Only allow safe operations
            allowed_chars = set("0123456789+-*/()., ")
            if not all(c in allowed_chars for c in expression):
                return "Error: Invalid characters in expression. Only numbers and +-*/() allowed"

            # Evaluate safely
            result = eval(expression, {"__builtins__": {}}, {})
            logger.info(f"Calculated: {expression} = {result}")
            return f"{expression} = {result}"
        except Exception as e:
            logger.error(f"Calculation error: {e}")
            return f"Error: {str(e)}"


class SimpleTool:
    """
    Simple built-in tools that always work.

    These tools don't require external services and can be used
    to demonstrate agentic capabilities.
    """

    def __init__(self):
        self.memory = MemoryStore()
        self.calculator = Calculator()

    @staticmethod
    def get_tool_definitions() -> List[Dict[str, Any]]:
        """
        Get all tool definitions for Ollama.

        Returns:
            List of tool definitions in OpenAI function calling format
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "store_memory",
                    "description": "Store information in memory for later retrieval. Useful for remembering facts, calculations, or intermediate results.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "Key to store the value under (e.g., 'user_name', 'calculation_result')"
                            },
                            "value": {
                                "type": "string",
                                "description": "Value to store"
                            }
                        },
                        "required": ["key", "value"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "retrieve_memory",
                    "description": "Retrieve previously stored information from memory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "Key to retrieve the value for"
                            }
                        },
                        "required": ["key"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_memory_keys",
                    "description": "List all keys currently stored in memory.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate",
                    "description": "Perform mathematical calculations. Supports +, -, *, /, and parentheses.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {
                                "type": "string",
                                "description": "Mathematical expression to evaluate (e.g., '2 + 2', '10 * (5 + 3)')"
                            }
                        },
                        "required": ["expression"]
                    }
                }
            }
        ]

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a simple tool.

        Args:
            tool_name: Name of tool to execute
            arguments: Tool arguments

        Returns:
            Result dict with success, result, and error fields
        """
        try:
            if tool_name == "store_memory":
                result = self.memory.store(arguments["key"], arguments["value"])
                return {"success": True, "result": result}

            elif tool_name == "retrieve_memory":
                result = self.memory.retrieve(arguments["key"])
                return {"success": True, "result": result}

            elif tool_name == "list_memory_keys":
                result = self.memory.list_keys()
                return {"success": True, "result": result}

            elif tool_name == "calculate":
                result = self.calculator.calculate(arguments["expression"])
                return {"success": True, "result": result}

            else:
                return {
                    "success": False,
                    "error": f"Unknown tool: {tool_name}"
                }

        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
