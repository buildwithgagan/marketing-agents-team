import requests
from dotenv import load_dotenv
import os
from langchain_core.tools import tool
from pytrends.request import TrendReq
from typing import List, Dict, Any
from tavily import TavilyClient
from firecrawl import FirecrawlApp

load_dotenv()


@tool
def get_autocomplete_suggestions(query: str) -> List[str]:
    """Get Search Autocomplete Suggestions."""
    url = f"http://google.com/complete/search?client=chrome&q={query}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if len(data) >= 2:
                return data[1]
        return []
    except Exception as e:
        return [f"Error: {str(e)}"]


@tool
def get_google_trends(keywords: List[str]) -> Dict[str, str]:
    """Get Google Trends data summary. Handles >5 keywords by batching."""
    try:
        pytrends = TrendReq(hl="en-US", tz=360)
        summary = {}

        # Batch keywords into chunks of 5 (Google Trends limit)
        chunk_size = 5
        for i in range(0, len(keywords), chunk_size):
            kw_chunk = keywords[i : i + chunk_size]
            try:
                pytrends.build_payload(
                    kw_chunk, cat=0, timeframe="today 12-m", geo="", gprop=""
                )
                data = pytrends.interest_over_time()

                if not data.empty:
                    for kw in kw_chunk:
                        if kw in data.columns:
                            series = data[kw]
                            mean_val = series.mean()
                            first_half = series.iloc[: len(series) // 2].mean()
                            second_half = series.iloc[len(series) // 2 :].mean()
                            trend = (
                                "Rising 📈"
                                if second_half > first_half * 1.2
                                else "Falling 📉"
                            )
                            summary[kw] = f"Trend: {trend} (Avg: {mean_val:.1f})"
            except Exception as e:
                # Log error for this chunk but continue
                for kw in kw_chunk:
                    summary[kw] = f"Error: {str(e)}"

        if not summary:
            return {"error": "No trend data found."}

        return summary
    except Exception as e:
        return {"error": f"Failed: {str(e)}"}


def _get_tavily_client():
    return TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


@tool
def tavily_search(query: str) -> str:
    """Perform a web search using Tavily. Use this to find blog URLs, service pages, and competitor content before scraping."""
    try:
        client = _get_tavily_client()
        # Using advanced search to get comprehensive results with URLs
        response = client.search(query=query, search_depth="advanced", max_results=8)
        results = response.get("results", [])

        out = "Search Results:\n"
        urls_found = []
        for i, res in enumerate(results):
            url = res.get("url", "").strip().rstrip(":").rstrip("/")
            title = res.get("title", "No Title")
            content = res.get("content", "")[:400]

            if url and url.startswith(("http://", "https://")):
                urls_found.append(url)
                out += f"{i+1}. **{title}**\n   **URL:** {url}\n   {content}...\n\n"
            else:
                out += f"{i+1}. **{title}**\n   (Invalid or missing URL)\n   {content}...\n\n"

        # Add summary of URLs found for easy extraction
        if urls_found:
            out += f"\n--- URLs DISCOVERED ({len(urls_found)} total) ---\n"
            for idx, u in enumerate(urls_found, 1):
                out += f"{idx}. {u}\n"
            out += "--- Use these URLs with scrape_competitor_page ---\n"

        if not results:
            out += "No results found. Try a different query.\n"

        return out
    except Exception as e:
        return f"Error: {str(e)}"


def _get_firecrawl_app():
    return FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))


@tool
def scrape_competitor_page(url: str) -> str:
    """Scrapes a specific URL returning Markdown content. Use this after finding URLs via tavily_search."""
    try:
        # Clean URL - remove trailing colons, spaces, and normalize
        url = url.strip().rstrip(":").rstrip("/")
        if not url.startswith(("http://", "https://")):
            return f"Invalid URL format: {url}. Must start with http:// or https://"

        app = _get_firecrawl_app()
        # FirecrawlApp uses v2 by default (scrape method), v1 available via .v1.scrape_url()
        result = None
        try:
            # Method 1: v2 API - scrape(url) with params dict
            result = app.scrape(url, {"formats": ["markdown"]})
        except (AttributeError, TypeError, Exception) as e1:
            try:
                # Method 2: v2 API - scrape(url=url, params={})
                result = app.scrape(url=url, params={"formats": ["markdown"]})
            except (AttributeError, TypeError, Exception) as e2:
                try:
                    # Method 3: v2 API - just scrape(url)
                    result = app.scrape(url)
                except (AttributeError, TypeError, Exception) as e3:
                    try:
                        # Method 4: v1 API fallback - app.v1.scrape_url()
                        if hasattr(app, "v1") and app.v1:
                            result = app.v1.scrape_url(url, {"formats": ["markdown"]})
                    except (AttributeError, TypeError, Exception) as e4:
                        raise Exception(
                            f"All Firecrawl API methods failed. Errors: v2={e1}, v2_kw={e2}, v2_simple={e3}, v1={e4}"
                        )

        if result is None:
            raise Exception(
                "All Firecrawl API methods returned None. Check SDK version and API key."
            )

        # Handle response - v2 returns Document object, v1 returns dict
        # #region agent log
        import json

        try:
            with open(r"e:\Automation_BTB\DeepAgent\.cursor\debug.log", "a") as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "FIX",
                            "location": "marketing.py:133",
                            "message": "Firecrawl scrape result type",
                            "data": {
                                "url": url,
                                "result_type": type(result).__name__,
                                "is_dict": isinstance(result, dict),
                                "has_markdown_attr": hasattr(result, "markdown"),
                                "has_content_attr": hasattr(result, "content"),
                                "result_keys": (
                                    list(result.keys())
                                    if isinstance(result, dict)
                                    else "N/A"
                                ),
                            },
                            "timestamp": __import__("time").time() * 1000,
                        }
                    )
                    + "\n"
                )
        except:
            pass
        # #endregion

        # Handle response - could be dict, Document object, or string
        if isinstance(result, dict):
            # v1 API returns dict
            return result.get(
                "markdown",
                result.get("content", result.get("data", "No content found.")),
            )
        elif hasattr(result, "markdown"):
            # v2 Document object with markdown attribute
            return result.markdown
        elif hasattr(result, "content"):
            # v2 Document object with content attribute
            return result.content
        elif hasattr(result, "data"):
            # Nested data attribute
            data = result.data
            if isinstance(data, dict):
                return data.get("markdown", data.get("content", "No content found."))
            return str(data)[:5000]
        elif hasattr(result, "get"):
            # Try calling get method if it exists
            return result.get("markdown", result.get("content", "No content found."))
        else:
            # Fallback: convert to string
            result_str = str(result)
            return result_str[:5000] if len(result_str) > 5000 else result_str
    except Exception as e:
        return f"Failed to scrape {url}: {str(e)}"
