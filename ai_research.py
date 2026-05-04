"""
AI research agent using Gemini 2.5 Flash-Lite with Google Search grounding.
Source URLs are extracted from grounding_metadata (actual site URLs, not search links).
"""

import json
import time
from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash-lite"

SYSTEM_PROMPT = """Ты — аналитик-консультант уровня McKinsey, специализирующийся на корейских компаниях и возможностях для Казахстана и Центральной Азии.

Твоя задача — провести структурированное исследование корейской компании и выдать чёткий, лаконичный брифинг.

Правила:
- Используй веб-поиск для проверки фактов
- Если данные не найдены — пиши "Не подтверждено"
- НЕ придумывай факты
- Стиль — профессиональный, сжатый, как в консалтинговом отчёте
- Ответ ВСЕГДА строго в формате JSON без markdown-обёртки и на русском языке

Структура ответа:
{
  "business_description": "Краткое описание компании (2-3 предложения)",
  "production_table": [
    {
      "product": "Название продукта или линейки",
      "facility": "Название завода, фабрики или офиса (или 'Штаб-квартира')",
      "location": "Город, провинция/страна"
    }
  ],
  "kazakhstan_presence": {
    "exists": true/false,
    "projects": "описание проектов или Не подтверждено",
    "partners": "партнёры/дистрибьюторы или Не подтверждено",
    "details": "подробности"
  },
  "central_asia_presence": {
    "uzbekistan": "описание или Не подтверждено",
    "kyrgyzstan": "описание или Не подтверждено",
    "summary": "Сводное описание присутствия в ЦА (Узбекистан + Кыргызстан)"
  },
  "caucasus_presence": {
    "azerbaijan": "описание или Не подтверждено",
    "armenia": "описание или Не подтверждено",
    "georgia": "описание или Не подтверждено",
    "summary": "Сводное описание присутствия на Кавказе"
  },
  "likelihood_kz": "High/Medium/Low",
  "likelihood_reasoning": "Обоснование оценки (3-5 предложений): наличие региональной базы, сектор, спрос в КЗ",
  "why_kazakhstan": ["тезис 1", "тезис 2", "тезис 3"],
  "engagement_format": "Рекомендуемые форматы сотрудничества: локализация / СП / поставки / EPC / технологии",
  "negotiation_questions": ["вопрос 1", "вопрос 2", "вопрос 3"]
}"""


def make_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def _get_response_text(response) -> str:
    """Extract non-thought text from a Gemini response (handles thinking models)."""
    # Try convenience property first (works in most SDK versions)
    try:
        if response.text:
            return response.text
    except Exception:
        pass

    # Fall back to manual extraction, skipping thought parts
    parts = []
    try:
        for candidate in (response.candidates or []):
            content = getattr(candidate, "content", None)
            if not content:
                continue
            for part in (content.parts or []):
                if getattr(part, "thought", False):
                    continue
                text = getattr(part, "text", None)
                if text:
                    parts.append(text)
    except Exception:
        pass
    return "\n".join(parts)


def _extract_grounding_urls(response) -> list[str]:
    """Extract actual website URLs from Gemini grounding metadata."""
    urls = []
    try:
        for candidate in response.candidates:
            meta = getattr(candidate, "grounding_metadata", None)
            if not meta:
                continue
            chunks = getattr(meta, "grounding_chunks", []) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if web:
                    uri = getattr(web, "uri", None)
                    if uri and not uri.startswith("https://www.google.com/search"):
                        urls.append(uri)
    except Exception:
        pass
    # Deduplicate while preserving order
    seen = set()
    return [u for u in urls if not (u in seen or seen.add(u))]


def _extract_json(text: str) -> dict:
    """Extract JSON from text, handling markdown fences and preamble text."""
    text = text.strip()

    # Strip markdown fences (handles ```json ... ``` or ``` ... ```)
    if "```" in text:
        fence_start = text.find("```")
        newline_after_fence = text.find("\n", fence_start)
        fence_end = text.rfind("```")
        if newline_after_fence != -1 and fence_end > newline_after_fence:
            text = text[newline_after_fence + 1:fence_end].strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find JSON object by scanning for matching braces (handles preamble text)
    brace_start = text.find("{")
    if brace_start != -1:
        depth = 0
        for i, ch in enumerate(text[brace_start:], brace_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[brace_start:i + 1])
                    except json.JSONDecodeError:
                        break

    raise json.JSONDecodeError("No valid JSON found in response", text, 0)


def research_company(company_name: str, sector: str, industry_name: str,
                     client: genai.Client) -> dict:
    user_prompt = (
        f"Исследуй корейскую компанию: {company_name}\n"
        f"Сектор: {sector or 'не указан'}\n"
        f"Отрасль: {industry_name or 'не указана'}\n\n"
        f"Верни строго JSON без markdown-обёртки."
    )

    last_error = "Unknown error"
    for attempt in range(3):
        text = ""
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.1,
                ),
            )

            text = _get_response_text(response)
            if not text:
                last_error = "Empty response from model"
                time.sleep(2 ** attempt)
                continue

            result = _extract_json(text)

            # Always override source_links with real grounded URLs from metadata
            grounded_urls = _extract_grounding_urls(response)
            result["source_links"] = grounded_urls if grounded_urls else result.get("source_links", [])

            return result

        except json.JSONDecodeError as e:
            last_error = f"JSON parse error: {e} | Raw: {text[:300]}"
            time.sleep(2 ** attempt)
        except Exception as e:
            return {**_fallback_response(), "_error": str(e)}

    return {**_fallback_response(), "_error": last_error}


def _fallback_response() -> dict:
    return {
        "business_description": "Не подтверждено",
        "production_table": [],
        "kazakhstan_presence": {
            "exists": False,
            "projects": "Не подтверждено",
            "partners": "Не подтверждено",
            "details": "Не подтверждено",
        },
        "central_asia_presence": {
            "uzbekistan": "Не подтверждено",
            "kyrgyzstan": "Не подтверждено",
            "summary": "Не подтверждено",
        },
        "caucasus_presence": {
            "azerbaijan": "Не подтверждено",
            "armenia": "Не подтверждено",
            "georgia": "Не подтверждено",
            "summary": "Не подтверждено",
        },
        "likelihood_kz": "Low",
        "likelihood_reasoning": "Данные не найдены",
        "why_kazakhstan": ["Требует дополнительного анализа"],
        "engagement_format": "Не определено",
        "negotiation_questions": ["Требует уточнения"],
        "source_links": [],
    }
