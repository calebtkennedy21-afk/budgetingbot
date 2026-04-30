"""
database.py — SQLite / PostgreSQL data layer for the Budgeting Bot.

If the DATABASE_URL environment variable is set the app connects to PostgreSQL
(Railway sets this automatically when you add a PostgreSQL plugin).  Otherwise
it falls back to a local SQLite file controlled by the DB_PATH env var.

Tables
------
income           : one-off or recurring income entries
fixed_expenses   : recurring fixed costs (e.g. rent, subscriptions)
variable_expenses: ad-hoc spending entries
financial_goals  : savings / spending goals with progress tracking
"""

import calendar
import os
import sqlite3
from datetime import datetime

# Railway sometimes supplies 'postgres://' — psycopg2 requires 'postgresql://'
_DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
if _DATABASE_URL.startswith("postgres://"):
    _DATABASE_URL = "postgresql://" + _DATABASE_URL[len("postgres://"):]

DB_PATH: str = os.environ.get("DB_PATH", "budget.db")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_pg() -> bool:
    return bool(_DATABASE_URL)


def _sql(query: str) -> str:
    """Convert %s placeholders to ? for SQLite."""
    if _is_pg():
        return query
    return query.replace("%s", "?")


def _read(query: str, params: tuple = ()) -> list:
    """Run a SELECT query and return rows as a list of plain dicts."""
    if _is_pg():
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(_DATABASE_URL)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, params)
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(_sql(query), params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def _write(query: str, params: tuple = ()) -> None:
    """Run an INSERT, UPDATE, or DELETE query."""
    if _is_pg():
        import psycopg2
        conn = psycopg2.connect(_DATABASE_URL)
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
            conn.commit()
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        try:
            conn.execute(_sql(query), params)
            conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

SAVINGS_ACCOUNTS = ["Caleb Savings", "Jamie Savings", "Joint Savings"]


def init_db() -> None:
    """Create all tables if they don't already exist."""
    if _is_pg():
        import psycopg2
        conn = psycopg2.connect(_DATABASE_URL)
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS income (
                        id          SERIAL PRIMARY KEY,
                        date        TEXT   NOT NULL,
                        amount      REAL   NOT NULL CHECK(amount > 0),
                        category    TEXT   NOT NULL DEFAULT 'General',
                        description TEXT,
                        created_at  TEXT   NOT NULL
                                    DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS fixed_expenses (
                        id          SERIAL PRIMARY KEY,
                        name        TEXT   NOT NULL,
                        amount      REAL   NOT NULL CHECK(amount > 0),
                        category    TEXT   NOT NULL DEFAULT 'General',
                        frequency   TEXT   NOT NULL DEFAULT 'monthly'
                                           CHECK(frequency IN ('monthly','yearly')),
                        start_date  TEXT   NOT NULL,
                        end_date    TEXT,
                        description TEXT,
                        created_at  TEXT   NOT NULL
                                    DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS variable_expenses (
                        id          SERIAL PRIMARY KEY,
                        date        TEXT   NOT NULL,
                        amount      REAL   NOT NULL CHECK(amount > 0),
                        category    TEXT   NOT NULL DEFAULT 'General',
                        description TEXT,
                        created_at  TEXT   NOT NULL
                                    DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS financial_goals (
                        id             SERIAL PRIMARY KEY,
                        name           TEXT   NOT NULL,
                        target_amount  REAL   NOT NULL CHECK(target_amount > 0),
                        current_amount REAL   NOT NULL DEFAULT 0
                                              CHECK(current_amount >= 0),
                        target_date    TEXT,
                        description    TEXT,
                        created_at     TEXT   NOT NULL
                                       DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS savings_transactions (
                        id          SERIAL PRIMARY KEY,
                        account     TEXT   NOT NULL,
                        date        TEXT   NOT NULL,
                        amount      REAL   NOT NULL CHECK(amount > 0),
                        type        TEXT   NOT NULL CHECK(type IN ('deposit','withdrawal')),
                        description TEXT,
                        created_at  TEXT   NOT NULL
                                    DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS debts (
                        id                    SERIAL PRIMARY KEY,
                        name                  TEXT   NOT NULL,
                        original_amount       REAL   NOT NULL CHECK(original_amount > 0),
                        current_balance       REAL   NOT NULL CHECK(current_balance >= 0),
                        interest_rate         REAL   NOT NULL DEFAULT 0 CHECK(interest_rate >= 0),
                        minimum_payment       REAL   NOT NULL DEFAULT 0 CHECK(minimum_payment >= 0),
                        minimum_payment_date  TEXT,
                        category              TEXT   NOT NULL DEFAULT 'Other',
                        description           TEXT,
                        created_at            TEXT   NOT NULL
                                              DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
                    )
                """)
            conn.commit()
            # Migration: add minimum_payment_date if it doesn't exist yet
            with conn.cursor() as cur:
                cur.execute("""
                    ALTER TABLE debts ADD COLUMN IF NOT EXISTS minimum_payment_date TEXT
                """)
            conn.commit()
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.executescript("""
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

            CREATE TABLE IF NOT EXISTS savings_transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                account     TEXT    NOT NULL,
                date        TEXT    NOT NULL,
                amount      REAL    NOT NULL CHECK(amount > 0),
                type        TEXT    NOT NULL CHECK(type IN ('deposit','withdrawal')),
                description TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS debts (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                name                  TEXT    NOT NULL,
                original_amount       REAL    NOT NULL CHECK(original_amount > 0),
                current_balance       REAL    NOT NULL CHECK(current_balance >= 0),
                interest_rate         REAL    NOT NULL DEFAULT 0 CHECK(interest_rate >= 0),
                minimum_payment       REAL    NOT NULL DEFAULT 0 CHECK(minimum_payment >= 0),
                minimum_payment_date  TEXT,
                category              TEXT    NOT NULL DEFAULT 'Other',
                description           TEXT,
                created_at            TEXT    NOT NULL DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        # Migration: add minimum_payment_date if it doesn't exist yet
        cols = [row[1] for row in conn.execute("PRAGMA table_info(debts)").fetchall()]
        if "minimum_payment_date" not in cols:
            conn.execute("ALTER TABLE debts ADD COLUMN minimum_payment_date TEXT")
            conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# Income
# ---------------------------------------------------------------------------

def add_income(date: str, amount: float, category: str, description: str) -> None:
    _write(
        "INSERT INTO income (date, amount, category, description) VALUES (%s, %s, %s, %s)",
        (date, amount, category, description),
    )


def get_income(year: int = None, month: int = None):
    query = "SELECT * FROM income WHERE 1=1"
    params: list = []
    if year:
        query += " AND SUBSTR(date, 1, 4) = %s"
        params.append(str(year))
    if month:
        query += " AND SUBSTR(date, 6, 2) = %s"
        params.append(f"{month:02d}")
    query += " ORDER BY date DESC"
    return _read(query, tuple(params))


def delete_income(record_id: int) -> None:
    _write("DELETE FROM income WHERE id = %s", (record_id,))


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
    _write(
        """INSERT INTO fixed_expenses
           (name, amount, category, frequency, start_date, end_date, description)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (name, amount, category, frequency, start_date, end_date, description),
    )


def get_fixed_expenses(active_only: bool = False):
    params: list = []
    query = "SELECT * FROM fixed_expenses"
    if active_only:
        today = datetime.today().strftime("%Y-%m-%d")
        query += " WHERE (end_date IS NULL OR end_date >= %s)"
        params.append(today)
    query += " ORDER BY name"
    return _read(query, tuple(params))


def delete_fixed_expense(record_id: int) -> None:
    _write("DELETE FROM fixed_expenses WHERE id = %s", (record_id,))


def update_fixed_expense_end_date(record_id: int, end_date: str) -> None:
    _write(
        "UPDATE fixed_expenses SET end_date = %s WHERE id = %s",
        (end_date, record_id),
    )


# ---------------------------------------------------------------------------
# Variable Expenses
# ---------------------------------------------------------------------------

def add_variable_expense(
    date: str, amount: float, category: str, description: str
) -> None:
    _write(
        "INSERT INTO variable_expenses (date, amount, category, description) VALUES (%s, %s, %s, %s)",
        (date, amount, category, description),
    )


def get_variable_expenses(year: int = None, month: int = None):
    query = "SELECT * FROM variable_expenses WHERE 1=1"
    params: list = []
    if year:
        query += " AND SUBSTR(date, 1, 4) = %s"
        params.append(str(year))
    if month:
        query += " AND SUBSTR(date, 6, 2) = %s"
        params.append(f"{month:02d}")
    query += " ORDER BY date DESC"
    return _read(query, tuple(params))


def delete_variable_expense(record_id: int) -> None:
    _write("DELETE FROM variable_expenses WHERE id = %s", (record_id,))


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
    _write(
        """INSERT INTO financial_goals
           (name, target_amount, current_amount, target_date, description)
           VALUES (%s, %s, %s, %s, %s)""",
        (name, target_amount, current_amount, target_date, description),
    )


def get_financial_goals():
    return _read("SELECT * FROM financial_goals ORDER BY name")


def update_goal_progress(record_id: int, current_amount: float) -> None:
    _write(
        "UPDATE financial_goals SET current_amount = %s WHERE id = %s",
        (current_amount, record_id),
    )


def delete_financial_goal(record_id: int) -> None:
    _write("DELETE FROM financial_goals WHERE id = %s", (record_id,))


# ---------------------------------------------------------------------------
# Savings
# ---------------------------------------------------------------------------

def add_savings_transaction(
    account: str,
    date: str,
    amount: float,
    transaction_type: str,
    description: str = "",
) -> None:
    _write(
        """INSERT INTO savings_transactions
           (account, date, amount, type, description)
           VALUES (%s, %s, %s, %s, %s)""",
        (account, date, amount, transaction_type, description),
    )


def get_savings_transactions(account: str = None):
    if account:
        return _read(
            "SELECT * FROM savings_transactions WHERE account = %s ORDER BY date DESC",
            (account,),
        )
    return _read("SELECT * FROM savings_transactions ORDER BY account, date DESC")


def get_savings_balance(account: str) -> float:
    rows = _read(
        "SELECT type, amount FROM savings_transactions WHERE account = %s",
        (account,),
    )
    balance = 0.0
    for r in rows:
        if r["type"] == "deposit":
            balance += r["amount"]
        else:
            balance -= r["amount"]
    return balance


def get_all_savings_balances() -> dict:
    """Return {account_name: balance} for all three savings accounts."""
    return {acct: get_savings_balance(acct) for acct in SAVINGS_ACCOUNTS}


def delete_savings_transaction(record_id: int) -> None:
    _write("DELETE FROM savings_transactions WHERE id = %s", (record_id,))


# ---------------------------------------------------------------------------
# Debts
# ---------------------------------------------------------------------------

DEBT_CATEGORIES = [
    "Credit Card",
    "Student Loan",
    "Car Loan",
    "Mortgage",
    "Personal Loan",
    "Medical",
    "Other",
]


def add_debt(
    name: str,
    original_amount: float,
    current_balance: float,
    interest_rate: float = 0.0,
    minimum_payment: float = 0.0,
    minimum_payment_date: str = None,
    category: str = "Other",
    description: str = "",
) -> None:
    _write(
        """INSERT INTO debts
           (name, original_amount, current_balance, interest_rate, minimum_payment, minimum_payment_date, category, description)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (name, original_amount, current_balance, interest_rate, minimum_payment, minimum_payment_date, category, description),
    )


def get_debts():
    return _read("SELECT * FROM debts ORDER BY name")


def update_debt_balance(record_id: int, new_balance: float) -> None:
    _write(
        "UPDATE debts SET current_balance = %s WHERE id = %s",
        (new_balance, record_id),
    )


def delete_debt(record_id: int) -> None:
    _write("DELETE FROM debts WHERE id = %s", (record_id,))


def get_total_debt() -> float:
    rows = _read("SELECT current_balance FROM debts")
    return sum(r["current_balance"] for r in rows)


# ---------------------------------------------------------------------------
# Aggregate helpers
# ---------------------------------------------------------------------------

def get_monthly_fixed_cost(year: int, month: int) -> float:
    """
    Sum of fixed expenses active during a given month.
    Monthly expenses count at full value; yearly expenses are divided by 12.
    """
    first_day = f"{year}-{month:02d}-01"
    if month == 12:
        last_day = f"{year}-12-31"
    else:
        last_day = f"{year}-{month:02d}-{calendar.monthrange(year, month)[1]}"

    rows = _read(
        """SELECT amount, frequency FROM fixed_expenses
           WHERE start_date <= %s
             AND (end_date IS NULL OR end_date >= %s)""",
        (last_day, first_day),
    )

    total = 0.0
    for r in rows:
        if r["frequency"] == "monthly":
            total += r["amount"]
        else:
            total += r["amount"] / 12
    return total
