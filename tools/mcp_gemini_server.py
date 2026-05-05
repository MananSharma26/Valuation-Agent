#!/usr/bin/env python3
"""MCP Server that wraps Google Gemini API for code review and analysis.

Provides tools that Claude Code can call to get Gemini's perspective on
valuations, code, assumptions, or any context.

Usage: configured in .mcp.json, launched automatically by Claude Code.
"""

import os

from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP("gemini-reviewer")

_MODEL = "gemini-2.5-flash"
_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        _client = genai.Client(api_key=api_key)
    return _client


def _ask(prompt: str) -> str:
    client = _get_client()
    resp = client.models.generate_content(model=_MODEL, contents=prompt)
    return resp.text


@mcp.tool()
def gemini_review(context: str, focus: str = "general") -> str:
    """Ask Gemini to review code, valuation assumptions, or any context.

    Args:
        context: The text/code/data to review (can be long)
        focus: What to focus on — "code", "valuation", "assumptions", "report", "general"

    Returns:
        Gemini's review as text
    """
    prompts = {
        "code": "You are a senior software engineer reviewing code. Focus on: bugs, edge cases, performance, readability, and correctness. Be specific and actionable.",
        "valuation": "You are a financial analyst reviewing a company valuation. Focus on: assumption reasonableness, methodology consistency with Damodaran, potential biases, missing factors, and whether the conclusion is defensible.",
        "assumptions": "You are reviewing valuation assumptions. For each assumption, assess: is the value reasonable? What data supports it? What could make it wrong? What's the sensitivity?",
        "report": "You are reviewing a valuation report for a finance professional. Focus on: completeness, clarity, whether conclusions follow from the analysis, any missing sections, and presentation quality.",
        "general": "Review the following and provide constructive feedback. Be specific and actionable.",
    }

    system = prompts.get(focus, prompts["general"])
    prompt = f"{system}\n\n---\n\n{context}"

    try:
        return _ask(prompt)
    except Exception as e:
        return f"Gemini error: {e}"


@mcp.tool()
def gemini_analyze(question: str, context: str = "") -> str:
    """Ask Gemini a specific question, optionally with context.

    Args:
        question: The question to ask
        context: Optional supporting context/data

    Returns:
        Gemini's analysis as text
    """
    prompt = question
    if context:
        prompt = f"{question}\n\nContext:\n{context}"

    try:
        return _ask(prompt)
    except Exception as e:
        return f"Gemini error: {e}"


@mcp.tool()
def gemini_compare_valuations(our_valuation: str, context: str = "") -> str:
    """Ask Gemini to critique our valuation vs market/analyst consensus.

    Args:
        our_valuation: Summary of our valuation (DCF value, key assumptions, etc.)
        context: Additional context (analyst targets, news, earnings call excerpts)

    Returns:
        Gemini's comparison and critique
    """
    prompt = f"""You are a senior equity research analyst. Compare and critique this independent valuation:

{our_valuation}

Additional context:
{context}

Provide:
1. What are the strongest and weakest assumptions?
2. Where does this valuation diverge from market consensus and why?
3. What risks or catalysts could materially change the conclusion?
4. Your overall assessment: is this valuation defensible?

Be specific and reference the numbers provided."""

    try:
        return _ask(prompt)
    except Exception as e:
        return f"Gemini error: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
