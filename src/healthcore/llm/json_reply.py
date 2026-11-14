"""Pull a JSON object out of a model reply, tolerating code fences and surrounding text."""


def extract_json_object(text: str) -> str | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.rsplit("```", 1)[0]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    return cleaned[start : end + 1]
