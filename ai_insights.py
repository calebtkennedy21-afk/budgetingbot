"""
ai_insights.py — Hybrid AI module for Budgeting Bot.

Three capabilities:
1. suggest_category()     — Keyword-based category suggestion; falls back to OpenAI
                            when description is ambiguous.
2. detect_anomalies()     — Statistical z-score anomaly detection on variable expenses.
3. generate_insights()    — OpenAI GPT-4o-mini monthly financial summary & advice.
4. chat_with_advisor()    — Conversational AI that can answer questions about finances.

Only aggregated/summarised data is sent to OpenAI — no raw transaction descriptions.
"""

from __future__ import annotations

import json
import os
import statistics
import re
from datetime import date
from typing import Optional

# ---------------------------------------------------------------------------
# OpenAI client (lazy init so the app still loads without the key set)
# ---------------------------------------------------------------------------
OPENAI_API_KEY_ENV = "BUDGETBOT_OPENAI_API_KEY"
_openai_client = None


def _get_client():
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    api_key = os.getenv(OPENAI_API_KEY_ENV, "")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=api_key)
        return _openai_client
    except ImportError:
        return None


def is_ai_available() -> bool:
    """Return True if OpenAI is configured and the library is installed."""
    return _get_client() is not None


# ---------------------------------------------------------------------------
# 1. Category Suggestion
# ---------------------------------------------------------------------------

# Maps keywords (lowercase) to variable expense categories.
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Food & Dining": [
        "restaurant", "cafe", "coffee", "starbucks", "mcdonald", "burger", "pizza",
        "sushi", "chinese", "thai", "indian", "mexican", "takeout", "takeaway",
        "doordash", "ubereats", "grubhub", "instacart", "delivery", "dine", "lunch",
        "dinner", "breakfast", "brunch", "bar", "pub", "bistro", "grill", "kitchen",
    ],
    "Groceries": [
        "grocery", "groceries", "walmart", "target", "costco", "kroger", "aldi",
        "safeway", "whole foods", "trader joe", "publix", "wegmans", "supermarket",
        "fresh market", "food store", "market", "produce", "butcher",
    ],
    "Entertainment": [
        "netflix", "hulu", "disney", "hbo", "spotify", "apple music", "youtube",
        "cinema", "movie", "theater", "theatre", "concert", "ticket", "game",
        "steam", "playstation", "xbox", "nintendo", "bowling", "arcade", "zoo",
        "museum", "amusement", "fun", "entertainment",
    ],
    "Healthcare": [
        "doctor", "hospital", "clinic", "pharmacy", "cvs", "walgreens", "rite aid",
        "dental", "dentist", "vision", "optometrist", "medical", "prescription",
        "medicine", "health", "therapy", "therapist", "urgent care", "lab", "test",
    ],
    "Clothing": [
        "clothes", "clothing", "shirt", "pants", "shoes", "dress", "fashion",
        "h&m", "zara", "gap", "old navy", "forever 21", "nordstrom", "macy",
        "bloomingdale", "nike", "adidas", "amazon clothing", "boutique",
    ],
    "Transport": [
        "gas", "fuel", "petrol", "uber", "lyft", "taxi", "cab", "bus", "train",
        "subway", "metro", "toll", "parking", "transit", "commute", "zipcar",
        "car wash", "mechanic", "auto", "vehicle",
    ],
    "Travel": [
        "hotel", "motel", "airbnb", "vrbo", "flight", "airline", "airport",
        "vacation", "holiday", "trip", "tour", "travel", "booking", "expedia",
        "resort", "cruise", "luggage", "passport",
    ],
    "Personal Care": [
        "salon", "haircut", "hair", "barber", "spa", "massage", "nail", "beauty",
        "cosmetics", "makeup", "shampoo", "lotion", "personal care", "gym",
        "fitness", "yoga", "pilates",
    ],
    "Education": [
        "school", "university", "college", "tuition", "course", "class", "book",
        "textbook", "udemy", "coursera", "skillshare", "learning", "education",
        "training", "workshop", "seminar",
    ],
    "Gifts": [
        "gift", "present", "birthday", "anniversary", "holiday gift", "christmas",
        "wedding", "baby shower", "flower", "bouquet", "donation", "charity",
    ],
}


def suggest_category(description: str, amount: float, history: list[dict]) -> tuple[str, str]:
    """
    Suggest a variable expense category based on description.

    Returns (suggested_category, source) where source is one of:
      'history'  — matched a description in past transactions
      'keyword'  — matched a keyword rule
      'ai'       — OpenAI suggestion
      'none'     — no suggestion available
    """
    if not description:
        return "", "none"

    desc_lower = description.lower()

    # 1. Check history — most specific signal
    for row in reversed(history):
        if row.get("description") and row.get("category"):
            if row["description"].lower() == desc_lower:
                return str(row["category"]), "history"

    # 2. Keyword matching
    for category, keywords in _CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                return category, "keyword"

    # 3. OpenAI fallback (only for non-trivial descriptions)
    client = _get_client()
    if client and len(description.strip()) >= 3:
        try:
            categories = list(_CATEGORY_KEYWORDS.keys()) + ["Other"]
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a financial categorisation assistant. "
                            "Classify the expense description into exactly one of the given categories. "
                            "Reply with only the category name, nothing else."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Categories: {', '.join(categories)}\n"
                            f"Expense description: {description}\n"
                            f"Amount: ${amount:.2f}"
                        ),
                    },
                ],
                max_tokens=20,
                temperature=0,
            )
            suggestion = response.choices[0].message.content.strip()
            if suggestion in categories:
                return suggestion, "ai"
        except Exception:
            pass

    return "", "none"


# ---------------------------------------------------------------------------
# 2. Anomaly Detection
# ---------------------------------------------------------------------------

def detect_anomalies(var_rows: list[dict], threshold_stdev: float = 2.0) -> list[dict]:
    """
    Flag variable expense rows where the amount is unusually high for their category.
    Uses z-score (mean + N * stdev).

    Returns a list of anomaly dicts with keys:
      id, date, category, amount, description, avg_for_category, z_score
    """
    if not var_rows:
        return []

    # Group amounts by category
    by_cat: dict[str, list[float]] = {}
    for row in var_rows:
        by_cat.setdefault(row["category"], []).append(float(row["amount"]))

    anomalies = []
    for row in var_rows:
        cat = row["category"]
        amounts = by_cat.get(cat, [])
        if len(amounts) < 3:
            # Not enough data for meaningful stats
            continue
        mean = statistics.mean(amounts)
        stdev = statistics.stdev(amounts)
        if stdev == 0:
            continue
        z = (float(row["amount"]) - mean) / stdev
        if z >= threshold_stdev:
            anomalies.append(
                {
                    "id": row["id"],
                    "date": row["date"],
                    "category": cat,
                    "amount": float(row["amount"]),
                    "description": row.get("description") or "",
                    "avg_for_category": round(mean, 2),
                    "z_score": round(z, 2),
                }
            )

    return sorted(anomalies, key=lambda x: x["z_score"], reverse=True)


# ---------------------------------------------------------------------------
# 3. Monthly Spending Insights (OpenAI)
# ---------------------------------------------------------------------------

def generate_insights(
    month: int,
    year: int,
    total_income: float,
    fixed_cost: float,
    variable_cost: float,
    category_breakdown: dict[str, float],
    total_savings: float,
    total_debt: float,
    goals: list[dict],
    prev_month_variable: float | None = None,
) -> str:
    """
    Generate a concise financial insights summary using OpenAI GPT-4o-mini.
    Only aggregate/summary data is sent — no raw transaction descriptions.

    Returns the generated text, or an error message string.
    """
    client = _get_client()
    if not client:
        return "⚠️ OpenAI API key not configured. Add BUDGETBOT_OPENAI_API_KEY to your environment."

    net = total_income - fixed_cost - variable_cost
    savings_rate = (total_savings / total_income * 100) if total_income > 0 else 0

    month_name = date(year, month, 1).strftime("%B %Y")
    cat_lines = "\n".join(
        f"  - {cat}: ${amt:,.2f}" for cat, amt in sorted(category_breakdown.items(), key=lambda x: -x[1])
    )
    goals_lines = "\n".join(
        f"  - {g['name']}: ${g['current_amount']:,.2f} / ${g['target_amount']:,.2f} ({min(g['current_amount']/g['target_amount']*100, 100):.0f}%)"
        for g in goals
    ) or "  - None set"

    prev_line = (
        f"Previous month variable expenses: ${prev_month_variable:,.2f}"
        if prev_month_variable is not None
        else "No prior month data available."
    )

    prompt = f"""You are a friendly personal finance advisor. Analyse the budget data below for {month_name} and provide:
1. A 2-3 sentence overall financial health summary.
2. 2-3 specific, actionable insights or recommendations.
3. One positive observation to keep the user motivated.

Keep the tone friendly, concise, and constructive. Use bullet points for insights. Do not repeat the raw numbers back verbatim.

--- BUDGET DATA ---
Month: {month_name}
Total Income: ${total_income:,.2f}
Fixed Expenses: ${fixed_cost:,.2f}
Variable Expenses: ${variable_cost:,.2f}
Net Balance: ${net:,.2f}
{prev_line}

Variable expense breakdown by category:
{cat_lines}

Savings (total across all accounts): ${total_savings:,.2f}
Total Debt Remaining: ${total_debt:,.2f}
Savings Rate (savings / income): {savings_rate:.1f}%

Financial Goals Progress:
{goals_lines}
---
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a concise, friendly personal finance advisor."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=600,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return f"⚠️ Could not generate insights: {exc}"


# ---------------------------------------------------------------------------
# 4. Chat Advisor
# ---------------------------------------------------------------------------

def chat_with_advisor(
    user_message: str,
    conversation_history: list[dict],
    financial_context: dict,
) -> str:
    """
    Conversational AI advisor. Answers questions about the user's finances.

    financial_context should include aggregated data (not raw transactions):
      month, year, total_income, fixed_cost, variable_cost, net,
      category_breakdown, total_savings, total_debt, goals
    """
    client = _get_client()
    if not client:
        return "⚠️ OpenAI API key not configured. Add BUDGETBOT_OPENAI_API_KEY to your environment."

    ctx = financial_context
    month_name = date(ctx.get("year", date.today().year), ctx.get("month", date.today().month), 1).strftime("%B %Y")
    cat_lines = "\n".join(
        f"  - {cat}: ${amt:,.2f}"
        for cat, amt in sorted(ctx.get("category_breakdown", {}).items(), key=lambda x: -x[1])
    ) or "  - No variable expenses this month"

    system_prompt = f"""You are a helpful personal finance assistant for a household budgeting app.
You have access to the following financial summary for {month_name}:

Income: ${ctx.get('total_income', 0):,.2f}
Fixed Expenses: ${ctx.get('fixed_cost', 0):,.2f}
Variable Expenses: ${ctx.get('variable_cost', 0):,.2f}
Net Balance: ${ctx.get('net', 0):,.2f}
Total Savings: ${ctx.get('total_savings', 0):,.2f}
Total Debt: ${ctx.get('total_debt', 0):,.2f}

Variable Spending by Category:
{cat_lines}

Answer questions helpfully and concisely. If you don't have enough data to answer, say so.
Do not make up specific numbers not provided above. Keep answers under 150 words unless the user asks for detail."""

    messages = [{"role": "system", "content": system_prompt}]

    # Include last 8 conversation turns for context
    for turn in conversation_history[-8:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return f"⚠️ Could not get a response: {exc}"


def classify_statement_rows(
    statement_rows: list[dict],
    statement_owner: str,
    default_income_source: str,
    default_savings_account: str,
    debt_names: list[str],
) -> list[dict]:
    """
    Classify statement rows into import routes using AI.

    Returns a list aligned with statement_rows. Each item can include:
      route, category, is_recurring, frequency, source, savings_account,
      savings_type, debt_name, fixed_name, confidence
    """
    client = _get_client()
    if not client or not statement_rows:
        return []

    payload_rows = []
    for idx, row in enumerate(statement_rows):
        payload_rows.append(
            {
                "row_id": idx,
                "date": row.get("date", ""),
                "amount": row.get("amount", ""),
                "description": row.get("description", ""),
                "category_hint": row.get("category", "Other"),
            }
        )

    prompt = f"""Classify household banking statement rows into import destinations.

Statement owner: {statement_owner}
Default income source: {default_income_source}
Default savings account: {default_savings_account}
Known debt names: {', '.join(debt_names) if debt_names else 'None'}

Use one of these routes exactly:
- income
- variable_expense
- fixed_expense
- savings_transfer
- debt_payment
- unknown

Guidance:
- fixed_expense = recurring bills/subscriptions/rent/insurance/utilities/loan bills that should create or update a fixed expense record.
- variable_expense = discretionary or one-off spending.
- income = wages, refunds, interest, dividends, reimbursements.
- savings_transfer = transfers between household accounts or savings moves.
- debt_payment = credit card or loan payments that reduce debt balances.

Return ONLY valid JSON as an array with one object per row, in the same order as the input rows.
Each object must contain:
row_id, route, category, is_recurring, frequency, source, savings_account, savings_type, debt_name, fixed_name, confidence

Rules:
- category should be a sensible app category or "Other".
- is_recurring should be true for recurring fixed charges or recurring habits.
- frequency should be "monthly", "yearly", or "one_time".
- source should usually be the default income source when route is income.
- savings_account should usually be the default savings account when route is savings_transfer.
- debt_name should be one of the known debt names when route is debt_payment.
- fixed_name should be a short label for the fixed expense when route is fixed_expense.
- confidence should be a number from 0 to 1.

Rows:
{json.dumps(payload_rows, ensure_ascii=False)}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You classify statement rows into finance import routes and return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1200,
            temperature=0,
        )
        content = response.choices[0].message.content.strip()
        content = re.sub(r"^```json\s*", "", content, flags=re.IGNORECASE)
        content = re.sub(r"^```\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        parsed = json.loads(content)
        if isinstance(parsed, dict) and "rows" in parsed:
            parsed = parsed["rows"]
        if not isinstance(parsed, list):
            return []

        normalized: list[dict] = []
        for idx, item in enumerate(parsed[: len(statement_rows)]):
            if not isinstance(item, dict):
                normalized.append({"row_id": idx, "route": "unknown"})
                continue
            normalized.append(
                {
                    "row_id": int(item.get("row_id", idx)),
                    "route": str(item.get("route", "unknown")),
                    "category": str(item.get("category", "Other") or "Other"),
                    "is_recurring": bool(item.get("is_recurring", False)),
                    "frequency": str(item.get("frequency", "one_time") or "one_time"),
                    "source": str(item.get("source", default_income_source) or default_income_source),
                    "savings_account": str(item.get("savings_account", default_savings_account) or default_savings_account),
                    "savings_type": str(item.get("savings_type", "deposit") or "deposit"),
                    "debt_name": str(item.get("debt_name", "") or ""),
                    "fixed_name": str(item.get("fixed_name", "") or ""),
                    "confidence": float(item.get("confidence", 0.5) or 0.5),
                }
            )
        return normalized
    except Exception:
        return []


def generate_weekly_brief(financial_context: dict, recent_events: list[dict] | None = None) -> str:
    """
    Generate a concise weekly financial brief from aggregate data.

    The output should include:
      - What changed recently
      - What to do this week
      - One encouraging takeaway
    """
    client = _get_client()
    if not client:
        return "⚠️ OpenAI API key not configured. Add BUDGETBOT_OPENAI_API_KEY to your environment."

    ctx = financial_context
    month_name = date(ctx.get("year", date.today().year), ctx.get("month", date.today().month), 1).strftime("%B %Y")
    cat_lines = "\n".join(
        f"  - {cat}: ${amt:,.2f}"
        for cat, amt in sorted(ctx.get("category_breakdown", {}).items(), key=lambda x: -x[1])
    ) or "  - No variable expenses recorded"

    event_lines = "\n".join(
        f"  - {event.get('label', 'Event')}: {event.get('value', '')}"
        for event in (recent_events or [])[:10]
    ) or "  - No notable events were provided"

    prompt = f"""Create a weekly personal finance brief from this data.
Month context: {month_name}
Income: ${ctx.get('total_income', 0):,.2f}
Fixed: ${ctx.get('fixed_cost', 0):,.2f}
Variable: ${ctx.get('variable_cost', 0):,.2f}
Net: ${ctx.get('net', 0):,.2f}
Savings: ${ctx.get('total_savings', 0):,.2f}
Debt: ${ctx.get('total_debt', 0):,.2f}

Category breakdown:
{cat_lines}

Recent events:
{event_lines}

Return exactly three sections:
1) "What changed" (2 bullets)
2) "This week actions" (3 bullets, specific and practical)
3) "Momentum" (1 short positive sentence)
Keep total under 180 words.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a concise, practical weekly finance coach."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=350,
            temperature=0.6,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return f"⚠️ Could not generate weekly brief: {exc}"


def run_scenario_plan(financial_context: dict, scenario_prompt: str) -> str:
    """
    Run a what-if scenario analysis from aggregate financial context.
    """
    client = _get_client()
    if not client:
        return "⚠️ OpenAI API key not configured. Add BUDGETBOT_OPENAI_API_KEY to your environment."

    ctx = financial_context
    cat_lines = "\n".join(
        f"  - {cat}: ${amt:,.2f}"
        for cat, amt in sorted(ctx.get("category_breakdown", {}).items(), key=lambda x: -x[1])
    ) or "  - No variable expenses recorded"

    prompt = f"""You are helping with a personal finance what-if analysis.

Current baseline:
- Income: ${ctx.get('total_income', 0):,.2f}
- Fixed expenses: ${ctx.get('fixed_cost', 0):,.2f}
- Variable expenses: ${ctx.get('variable_cost', 0):,.2f}
- Net: ${ctx.get('net', 0):,.2f}
- Savings: ${ctx.get('total_savings', 0):,.2f}
- Debt: ${ctx.get('total_debt', 0):,.2f}

Spending categories:
{cat_lines}

Scenario request:
{scenario_prompt}

Respond with:
1) Estimated monthly impact (range is okay when uncertain)
2) Main trade-offs and risks
3) A 3-step action plan to try the scenario safely this month

Keep it concrete and concise. Avoid claiming precision you do not have.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a pragmatic personal finance scenario planner."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return f"⚠️ Could not run scenario plan: {exc}"
