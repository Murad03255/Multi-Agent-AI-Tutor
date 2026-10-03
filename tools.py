import json
import math
import urllib.parse
import urllib.request
from crewai.tools import tool


@tool("Concept Lookup")
def concept_lookup(query: str) -> str:
    """Look up definitions and facts for common academic topics."""
    q = query.lower()
    facts = {
        "photosynthesis": "Photosynthesis converts CO2 and water into glucose and oxygen using sunlight: 6CO2 + 6H2O → C6H12O6 + 6O2.",
        "gravity": "Gravity is the attractive force between masses. Newton's formula: F = G*m1*m2/r^2.",
        "mitosis": "Mitosis is cell division that produces two identical daughter cells (Prophase → Metaphase → Anaphase → Telophase).",
        "binary search": "Binary search works on sorted arrays and finds a value in O(log n) by halving the search space each step.",
        "recursion": "Recursion is when a function calls itself. Every recursive function needs a base case to stop.",
        "pythagorean theorem": "In a right triangle: a² + b² = c², where c is the hypotenuse."
    }
    for key in facts:
        if key in q:
            return facts[key]
    return f"No specific definition found for '{query}', but this is a valid academic topic."


@tool("Calculator")
def calculator(expression: str) -> str:
    """Evaluate math expressions safely."""
    try:
        safe_env = {k: v for k, v in math.__dict__.items() if not k.startswith("__")}
        result = eval(expression.replace("^", "**"), {"__builtins__": {}}, safe_env)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Could not calculate '{expression}': {e}"


@tool("Wikipedia Search")
def wiki_search(query: str) -> str:
    """Search Wikipedia for a topic summary."""
    try:
        encoded = urllib.parse.quote(query.strip())
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        req = urllib.request.Request(url, headers={"User-Agent": "LeoTutor/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            text = data.get("extract", "")
            if text:
                return text[:600]
    except Exception:
        pass
    return f"Wikipedia result not found for '{query}'."
