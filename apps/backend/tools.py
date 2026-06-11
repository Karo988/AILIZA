from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException


def run_tavily_search(query: str) -> dict[str, Any]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="TAVILY_API_KEY is not configured")

    try:
        from tavily import TavilyClient
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="tavily-python is not installed") from exc

    try:
        client = TavilyClient(api_key=api_key)
        return client.search(query=query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Tavily search failed: {exc}") from exc


def fetch_webpage(url: str) -> dict[str, str]:
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="requests and beautifulsoup4 are required") from exc

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Webpage fetch failed: {exc}") from exc

    soup = BeautifulSoup(response.text, "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""
    text = soup.get_text(separator="\n", strip=True)

    return {"title": title, "text": text}


def execute_tool(tool_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
    if tool_name == "search":
        query = str(parameters.get("query", ""))
        if not query:
            raise HTTPException(status_code=422, detail="query is required")
        return run_tavily_search(query)

    if tool_name == "fetch":
        url = str(parameters.get("url", ""))
        if not url:
            raise HTTPException(status_code=422, detail="url is required")
        return fetch_webpage(url)

    raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")
