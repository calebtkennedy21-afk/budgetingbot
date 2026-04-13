"""
database.py — SQLite data layer for the Budgeting Bot.

Tables
------
income           : one-off or recurring income entries
fixed_expenses   : recurring fixed costs (e.g. rent, subscriptions)
variable_expenses: ad-hoc spending entries
financial_goals  : savings / spending goals with progress tracking
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "budget.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create all tables if they don't already exist."""
    conn = _connect()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS income (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL,
            amount      REAL    NOT NULL CHECK(amount > 0),
            category    TEXT    NOT NULL DEFAULT 'General',
            description TEXT,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS fixed_expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            amount      REAL    NOT NULL CHECK(amount > 0),
            category    TEXT    NOT NULL DEFAULT 'General',
            frequency   TEXT    NOT NULL DEFAULT 'monthly'
                                CHECK(frequency IN ('monthly','yearly')),
            start_date  TEXT    NOT NULL,
            end_date    TEXT,
            description TEXT,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS variable_expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL,
            amount      REAL    NOT NULL CHECK(amount > 0),
            category    TEXT    NOT NULL DEFAULT 'General',
            description TEXT,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS financial_goals (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT    NOT NULL,
            target_amount  REAL    NOT NULL CHECK(target_amount > 0),
            current_amount REAL    NOT NULL DEFAULT 0 CHECK(current_amount >= 0),
            target_date    TEXT,
            description    TEXT,
            created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        """
    )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Income
# ---------------------------------------------------------------------------

def add_income(date: str, amount: float, category: str, description: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO income (date, amount, category, description) VALUES (?, ?, ?, ?)",
        (date, amount, category, description),
    )
    conn.commit()
    conn.close()


def get_income(year: int = None, month: int = None):
    conn = _connect()
    query = "SELECT * FROM income WHERE 1=1"
    params = []
    if year:
        query += " AND strftime('%Y', date) = ?"
        params.append(str(year))
    if month:
        query += " AND strftime('%m', date) = ?"
        params.append(f"{month:02d}")
    query += " ORDER BY date DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_income(record_id: int) -> None:
    conn = _connect()
    conn.execute("DELETE FROM income WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Fixed Expenses
# ---------------------------------------------------------------------------

def add_fixed_expense(
    name: str,
    amount: float,
    category: str,
    frequency: str,
    start_date: str,
    end_date: str = None,
    description: str = "",
) -> None:
    conn = _connect()
    conn.execute(
        """INSERT INTO fixed_expenses
           (name, amount, category, frequency, start_date, end_date, description)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (name, amount, category, frequency, start_date, end_date, description),
    )
    conn.commit()
    conn.close()


def get_fixed_expenses(active_only: bool = False):
    conn = _connect()
    params: list = []
    query = "SELECT * FROM fixed_expenses"
    if active_only:
        today = datetime.today().strftime("%Y-%m-%d")
        query += " WHERE (end_date IS NULL OR end_date >= ?)"
        params.append(today)
    query += " ORDER BY name"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_fixed_expense(record_id: int) -> None:
    conn = _connect()
    conn.execute("DELETE FROM fixed_expenses WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()


def update_fixed_expense_end_date(record_id: int, end_date: str) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE fixed_expenses SET end_date = ? WHERE id = ?",
        (end_date, record_id),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Variable Expenses
# ---------------------------------------------------------------------------

def add_variable_expense(
    date: str, amount: float, category: str, description: str
) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO variable_expenses (date, amount, category, description) VALUES (?, ?, ?, ?)",
        (date, amount, category, description),
    )
    conn.commit()
    conn.close()


def get_variable_expenses(year: int = None, month: int = None):
    conn = _connect()
    query = "SELECT * FROM variable_expenses WHERE 1=1"
    params = []
    if year:
        query += " AND strftime('%Y', date) = ?"
        params.append(str(year))
    if month:
        query += " AND strftime('%m', date) = ?"
        params.append(f"{month:02d}")
    query += " ORDER BY date DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_variable_expense(record_id: int) -> None:
    conn = _connect()
    conn.execute("DELETE FROM variable_expenses WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Financial Goals
# ---------------------------------------------------------------------------

def add_financial_goal(
    name: str,
    target_amount: float,
    current_amount: float = 0,
    target_date: str = None,
    description: str = "",
) -> None:
    conn = _connect()
    conn.execute(
        """INSERT INTO financial_goals
           (name, target_amount, current_amount, target_date, description)
           VALUES (?, ?, ?, ?, ?)""",
        (name, target_amount, current_amount, target_date, description),
    )
    conn.commit()
    conn.close()


def get_financial_goals():
    conn = _connect()
    rows = conn.execute("SELECT * FROM financial_goals ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_goal_progress(record_id: int, current_amount: float) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE financial_goals SET current_amount = ? WHERE id = ?",
        (current_amount, record_id),
    )
    conn.commit()
    conn.close()


def delete_financial_goal(record_id: int) -> None:
    conn = _connect()
    conn.execute("DELETE FROM financial_goals WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Aggregate helpers
# ---------------------------------------------------------------------------

def get_monthly_fixed_cost(year: int, month: int) -> float:
    """
    Sum of fixed expenses active during a given month.
    Monthly expenses count at full value; yearly expenses are divided by 12.
    """
    # A fixed expense is "active" in a month if:
    #   start_date <= last day of month  AND  (end_date IS NULL OR end_date >= first day of month)
    first_day = f"{year}-{month:02d}-01"
    # last day: advance to next month, subtract one day
    if month == 12:
        last_day = f"{year}-12-31"
    else:
        import calendar
        last_day = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"

    conn = _connect()
    rows = conn.execute(
        """SELECT amount, frequency FROM fixed_expenses
           WHERE start_date <= ?
             AND (end_date IS NULL OR end_date >= ?)""",
        (last_day, first_day),
    ).fetchall()
    conn.close()

    total = 0.0
    for r in rows:
        if r["frequency"] == "monthly":
            total += r["amount"]
        else:
            total += r["amount"] / 12
    return total
