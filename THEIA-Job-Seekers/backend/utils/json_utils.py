import json
import re
from typing import Any, Tuple


def strip_code_fences(text: str) -> str:
    t = (text or "").replace("```json", "```").replace("```JSON", "```")
    return t.replace("```", "")


def extract_first_balanced_json(text: str) -> Tuple[str, bool]:
    """Return first balanced JSON object substring and a boolean indicating success."""
    s = strip_code_fences(text or "").strip()
    depth = 0
    start_idx = None
    for i, ch in enumerate(s):
        if ch == '{':
            if depth == 0:
                start_idx = i
            depth += 1
        elif ch == '}':
            if depth > 0:
                depth -= 1
                if depth == 0 and start_idx is not None:
                    return s[start_idx:i + 1], True
    return s, False


def try_parse_json(text: str) -> Any:
    """Best-effort JSON parse: attempt direct, then trailing-comma cleanup."""
    try:
        return json.loads(text)
    except Exception:
        fixed = re.sub(r",\s*([}\]])", r"\1", text)
        return json.loads(fixed)


