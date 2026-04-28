"""
AI research agent using Gemini 2.5 Flash-Lite with Google Search grounding.
Produces structured consultant-style briefing for each Korean company.
"""

import json
from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash-lite"

SYSTEM_PROMPT = """Ты — аналитик-консультант уровня McKinsey, специализирующийся на корейских компаниях и возможностях для Казахстана и Центральной Азии.

Твоя задача — провести структурированное исследование корейской компании и выдать чёткий, лаконичный брифинг.

Правила:
- Используй веб-поиск для проверки фактов
- Каждое утверждение должно подкрепляться источником (URL)
- Если данные не найдены — пиши "Не подтверждено"
- НЕ придумывай факты
- Стиль — профессиональный, сжатый, как в консалтинговом отчёте
- Ответ ВСЕГДА в формате JSON

Структура ответа (строго JSON):
{
  "business_description": "Краткое описание компании (2-3 предложения)",
  "main_products": "Основные продукты/услуги (перечень через ; )",
  "headquarters_location": "Город, провинция, Корея",
  "production_locations": "Где находятся производственные мощности",
  "kazakhstan_presence": {
    "exists": true/false,
    "projects": "описание проектов или Не подтверждено",
    "partners": "партнёры/дистрибьюторы или Не подтверждено",
    "details": "подробности"
  },
  "uzbekistan_presence": "описание или Не подтверждено",
  "azerbaijan_presence": "описание или Не подтверждено",
  "georgia_presence": "описание или Не подтверждено",
  "armenia_presence": "описание или Не подтверждено",
  "kyrgyzstan_presence": "описание или Не подтверждено",
  "central_asia_presence": "Сводное описание присутствия в ЦА",
  "likelihood_kz": "High/Medium/Low",
  "likelihood_reasoning": "Обоснование оценки (3-5 предложений): наличие региональной базы, сектор, спрос в КЗ",
  "why_kazakhstan": ["тезис 1", "тезис 2", "тезис 3"],
  "engagement_format": "Рекомендуемые форматы сотрудничества: локализация / СП / поставки / EPC / технологии",
  "negotiation_questions": ["вопрос 1", "вопрос 2", "вопрос 3"],
  "source_links": ["url1", "url2", "url3"]
}"""


def make_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def research_company(company_name: str, sector: str, industry_name: str,
                     client: genai.Client) -> dict:
    user_prompt = (
        f"Исследуй корейскую компанию: **{company_name}**\n"
        f"Сектор: {sector or 'не указан'}\n"
        f"Отрасль: {industry_name or 'не указана'}\n\n"
        f"Выполни анализ по схеме и верни строго JSON без markdown-обёртки."
    )

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

        text = response.text.strip()

        # Strip markdown fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            start = 1
            end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            text = "\n".join(lines[start:end])

        return json.loads(text)

    except json.JSONDecodeError:
        return _fallback_response()
    except Exception as e:
        return {**_fallback_response(), "_error": str(e)}


def _fallback_response() -> dict:
    return {
        "business_description": "Не подтверждено",
        "main_products": "Не подтверждено",
        "headquarters_location": "Не подтверждено",
        "production_locations": "Не подтверждено",
        "kazakhstan_presence": {
            "exists": False,
            "projects": "Не подтверждено",
            "partners": "Не подтверждено",
            "details": "Не подтверждено",
        },
        "uzbekistan_presence": "Не подтверждено",
        "azerbaijan_presence": "Не подтверждено",
        "georgia_presence": "Не подтверждено",
        "armenia_presence": "Не подтверждено",
        "kyrgyzstan_presence": "Не подтверждено",
        "central_asia_presence": "Не подтверждено",
        "likelihood_kz": "Low",
        "likelihood_reasoning": "Данные не найдены",
        "why_kazakhstan": ["Требует дополнительного анализа"],
        "engagement_format": "Не определено",
        "negotiation_questions": ["Требует уточнения"],
        "source_links": [],
    }
