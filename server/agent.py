from __future__ import annotations

import ast
import datetime as dt
import json
import operator
from typing import Any
from zoneinfo import ZoneInfo

from openai import OpenAI

SYSTEM_PROMPT = """You are a concise general voice assistant in a proof-of-concept demo.
Speak in short sentences that sound natural when read aloud. Avoid markdown, lists, and URLs unless asked.
You can:
- tell the current local time
- remember short notes the user asks you to store
- do simple math and unit conversions
- pretend to control named devices (lights, fan, etc.) as a stand-in for later physical AI

If the user greets you, introduce yourself in one sentence and offer to help.
When a tool result comes back, summarize it in spoken English rather than repeating raw JSON.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current date and time. Defaults to the server local timezone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Optional IANA timezone, e.g. Asia/Kolkata",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_note",
            "description": "Store a short note the user wants remembered for this session.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note": {"type": "string"},
                },
                "required": ["note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_notes",
            "description": "Recall notes stored in this session.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a simple arithmetic expression like 12 * 3.5 + 2.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_units",
            "description": "Convert between common units: C/F, km/mi, kg/lb, m/ft.",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {"type": "number"},
                    "from_unit": {"type": "string"},
                    "to_unit": {"type": "string"},
                },
                "required": ["value", "from_unit", "to_unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_device",
            "description": "Turn a named placeholder device on or off (physical-AI stub).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "on": {"type": "boolean"},
                },
                "required": ["name", "on"],
            },
        },
    },
]

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.Mod: operator.mod,
}


class SessionMemory:
    def __init__(self) -> None:
        self.notes: list[str] = []
        self.devices: dict[str, bool] = {}
        self.history: list[dict[str, Any]] = []


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    raise ValueError("Unsupported expression")


def calculate(expression: str) -> str:
    tree = ast.parse(expression, mode="eval")
    result = _eval_node(tree.body)
    if result.is_integer():
        return str(int(result))
    return str(round(result, 6))


def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    key = (from_unit.lower().strip(), to_unit.lower().strip())
    factors = {
        ("c", "f"): lambda v: v * 9 / 5 + 32,
        ("f", "c"): lambda v: (v - 32) * 5 / 9,
        ("km", "mi"): lambda v: v * 0.621371,
        ("mi", "km"): lambda v: v / 0.621371,
        ("kg", "lb"): lambda v: v * 2.20462,
        ("lb", "kg"): lambda v: v / 2.20462,
        ("m", "ft"): lambda v: v * 3.28084,
        ("ft", "m"): lambda v: v / 3.28084,
        ("cm", "in"): lambda v: v / 2.54,
        ("in", "cm"): lambda v: v * 2.54,
    }
    fn = factors.get(key)
    if not fn:
        return f"I don't know how to convert {from_unit} to {to_unit} yet."
    out = fn(float(value))
    return f"{value} {from_unit} is {round(out, 4)} {to_unit}"


def run_tool(name: str, arguments: dict[str, Any], memory: SessionMemory) -> str:
    if name == "get_current_time":
        tz_name = arguments.get("timezone")
        try:
            tz = ZoneInfo(tz_name) if tz_name else dt.datetime.now().astimezone().tzinfo
        except Exception:
            tz = dt.datetime.now().astimezone().tzinfo
        now = dt.datetime.now(tz)
        return now.strftime("%A, %B %d, %Y, %I:%M %p %Z")
    if name == "remember_note":
        note = str(arguments.get("note", "")).strip()
        if note:
            memory.notes.append(note)
        return json.dumps({"stored": note, "count": len(memory.notes)})
    if name == "recall_notes":
        return json.dumps({"notes": memory.notes})
    if name == "calculate":
        try:
            return calculate(str(arguments.get("expression", "")))
        except Exception as exc:
            return f"Could not calculate that: {exc}"
    if name == "convert_units":
        return convert_units(
            float(arguments.get("value", 0)),
            str(arguments.get("from_unit", "")),
            str(arguments.get("to_unit", "")),
        )
    if name == "set_device":
        device = str(arguments.get("name", "device")).strip() or "device"
        on = bool(arguments.get("on"))
        memory.devices[device.lower()] = on
        state = "on" if on else "off"
        return json.dumps({"device": device, "state": state})
    return f"Unknown tool: {name}"


def chat_reply(
    client: OpenAI,
    model: str,
    user_text: str,
    memory: SessionMemory,
) -> str:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *memory.history,
        {"role": "user", "content": user_text},
    ]

    for _ in range(4):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.6,
        )
        choice = response.choices[0]
        msg = choice.message
        if msg.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in msg.tool_calls
                    ],
                }
            )
            for call in msg.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = run_tool(call.function.name, args, memory)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result,
                    }
                )
            continue

        reply = (msg.content or "").strip()
        memory.history.append({"role": "user", "content": user_text})
        memory.history.append({"role": "assistant", "content": reply})
        if len(memory.history) > 20:
            memory.history = memory.history[-20:]
        return reply or "I didn't catch that."

    return "I got stuck calling tools. Please try again."
