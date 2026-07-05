import requests
from typing import List, Dict, Any

TAVILY_API_URL = "https://api.tavily.com/search"

def execute_web_search(query: str, api_key: str, max_results: int = 4) -> List[Dict[str, Any]]:
    """
    Queries Tavily Search REST API directly using requests.
    Returns a list of structured web results: {"title", "url", "content"}.
    """
    if not api_key:
        raise ValueError("Tavily API key is missing.")

    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "include_answer": False,
        "max_results": max_results
    }

    try:
        response = requests.post(TAVILY_API_URL, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", "Web Page"),
                "url": item.get("url", ""),
                "content": item.get("content", "")
            })
        return results
    except Exception as e:
        raise RuntimeError(f"Tavily Search API request failed: {str(e)}")
