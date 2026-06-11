"""
AILIZA API Client - LLM Kommunikation
DSGVO Art. 28: Auftragsverarbeitung
"""
from __future__ import annotations
import json, logging, os
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

def call_llm_api(agent, messages, system_message, stream_callback=None):
    provider = "anthropic" if "claude" in (agent.model or "").lower() else "openai"
    if provider == "anthropic":
        return _call_anthropic(agent, messages, system_message, stream_callback)
    return _call_openai_compatible(agent, messages, system_message, stream_callback)

def _call_anthropic(agent, messages, system_message, stream_callback=None):
    try:
        import anthropic
        api_key = agent.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY nicht gesetzt")
        client = anthropic.Anthropic(api_key=api_key)
        model = agent.model.replace("anthropic/", "") or "claude-sonnet-4-6-20251001"
        tools = _build_anthropic_tools(agent)
        kwargs = {"model": model, "max_tokens": 8096, "system": system_message, "messages": _convert_messages(messages)}
        if tools:
            kwargs["tools"] = tools
        response = client.messages.create(**kwargs)
        return _parse_anthropic_response(response)
    except ImportError:
        raise ImportError("anthropic nicht installiert: pip install anthropic")

def _parse_anthropic_response(response):
    content_text = ""
    tool_calls = []
    for block in response.content:
        if block.type == "text":
            content_text = block.text
        elif block.type == "tool_use":
            tool_calls.append({"id": block.id, "type": "function", "function": {"name": block.name, "arguments": json.dumps(block.input)}})
    message = {"role": "assistant", "content": content_text}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"message": message, "finish_reason": response.stop_reason}

def _call_openai_compatible(agent, messages, system_message, stream_callback=None):
    try:
        from openai import OpenAI
        api_key = agent.api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("AILIZA_BASE_URL", "https://openrouter.ai/api/v1")
        client = OpenAI(api_key=api_key, base_url=base_url)
        all_messages = [{"role": "system", "content": system_message}] + messages
        tools = _build_openai_tools(agent)
        kwargs = {"model": agent.model or "anthropic/claude-sonnet-4-6", "messages": all_messages, "max_tokens": 8096}
        if tools:
            kwargs["tools"] = tools
        response = client.chat.completions.create(**kwargs)
        return _parse_openai_response(response)
    except ImportError:
        raise ImportError("openai nicht installiert: pip install openai")

def _parse_openai_response(response):
    choice = response.choices[0]
    message = choice.message
    result = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        result["tool_calls"] = [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in message.tool_calls]
    return {"message": result, "finish_reason": choice.finish_reason}

def _build_anthropic_tools(agent):
    return [{"name": n, "description": i.get("schema",{}).get("description",""), "input_schema": i.get("schema",{}).get("parameters",{"type":"object","properties":{}})} for n,i in agent._tool_registry.items()]

def _build_openai_tools(agent):
    return [{"type":"function","function":{"name":n,"description":i.get("schema",{}).get("description",""),"parameters":i.get("schema",{}).get("parameters",{"type":"object","properties":{}})}} for n,i in agent._tool_registry.items()]

def _convert_messages(messages):
    converted = []
    for msg in messages:
        role = msg.get("role","user")
        if role == "tool":
            converted.append({"role":"user","content":[{"type":"tool_result","tool_use_id":msg.get("tool_call_id",""),"content":msg.get("content","")}]})
        elif role == "assistant" and msg.get("tool_calls"):
            content = []
            if msg.get("content"):
                content.append({"type":"text","text":msg["content"]})
            for tc in msg["tool_calls"]:
                args = tc["function"]["arguments"]
                if isinstance(args, str):
                    try: args = json.loads(args)
                    except: args = {}
                content.append({"type":"tool_use","id":tc["id"],"name":tc["function"]["name"],"input":args})
            converted.append({"role":"assistant","content":content})
        elif role in ("user","assistant"):
            converted.append({"role":role,"content":msg.get("content","")})
    return converted
