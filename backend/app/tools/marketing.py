import requests
from dotenv import load_dotenv
import os
from langchain_core.tools import tool
from pytrends.request import TrendReq
from typing import List, Dict, Union, Any, Optional
from tavily import TavilyClient
from firecrawl import FirecrawlApp

# Load env variables
load_dotenv()

# --- Google Tools ---


@tool
def get_autocomplete_suggestions(query: str) -> List[str]:
    """
    Get Search Autocomplete Suggestions for a given query to find high-intent long-tail keywords.
    Useful for discovering what users are actually typing into the search bar.
    """
    url = f"http://google.com/complete/search?client=chrome&q={query}"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if len(data) >= 2:
                # data[1] contains the list of suggestions
                return data[1]
        return []
    except Exception as e:
        return [f"Error fetching suggestions: {str(e)}"]


@tool
def get_google_trends(keywords: List[str]) -> Dict[str, str]:
    """
    Get Google Trends data (Interest Over Time) for a list of keywords (max 5).
    Returns a textual summary of the trend direction (Rising/Falling/Stable) and the peak value.
    This is useful for validating market interest and seasonality.
    """
    try:
        pytrends = TrendReq(hl="en-US", tz=360)
        # Pytrends allows max 5 keywords
        kw_list = keywords[:5]

        pytrends.build_payload(kw_list, cat=0, timeframe="today 12-m", geo="", gprop="")

        # Interest Over Time
        data = pytrends.interest_over_time()

        if data.empty:
            return {"error": "No trend data found for these keywords."}

        summary = {}
        for kw in kw_list:
            if kw in data.columns:
                series = data[kw]
                mean_val = series.mean()
                max_val = series.max()
                # Simple trend heuristic
                first_half = series.iloc[: len(series) // 2].mean()
                second_half = series.iloc[len(series) // 2 :].mean()

                trend_direction = "Stable"
                if second_half > first_half * 1.2:
                    trend_direction = "Rising 📈"
                elif first_half > second_half * 1.2:
                    trend_direction = "Falling 📉"

                summary[kw] = (
                    f"Trend: {trend_direction} (Avg Interest: {mean_val:.1f}, Peak: {max_val})"
                )

        return summary
    except Exception as e:
        return {"error": f"Failed to fetch trends: {str(e)}"}


# --- Tavily Tools ---


def _get_tavily_client():
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("TAVILY_API_KEY not set in environment.")
    return TavilyClient(api_key=api_key)


@tool
def tavily_search(query: str) -> str:
    """
    Perform a web search using Tavily.
    Returns a string summary of results (Title + URL + Snippet).
    """
    try:
        client = _get_tavily_client()
        # Use simple "search" not advanced context to get list of results
        response = client.search(query=query, search_depth="advanced", max_results=4)
        results = response.get("results", [])

        # Format as a clean string for the LLM
        formatted_results = "Search Results:\n"
        for i, res in enumerate(results):
            formatted_results += f"{i+1}. {res.get('title')} ({res.get('url')})\n   Snippet: {res.get('content')}\n\n"

        return formatted_results
    except Exception as e:
        return f"Error: {str(e)}"


# --- Firecrawl Tools ---


def _get_firecrawl_app():
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        raise ValueError("FIRECRAWL_API_KEY not set in environment.")
    return FirecrawlApp(api_key=api_key)


@tool
def scrape_competitor_page(url: str) -> str:
    """
    Scrapes a specific URL (like a competitor's landing page or pricing page)
    and returns clean Markdown content. Use this to get deep details
    about a competitor's offer, technology, or pricing.
    """
    try:
        app = _get_firecrawl_app()
        # 'scrape_url' gets the single page content
        scrape_result = app.scrape_url(url, params={"formats": ["markdown"]})

        # Return the clean markdown
        return scrape_result.get("markdown", "No content found.")
    except Exception as e:
        return f"Failed to scrape {url}: {str(e)}"
