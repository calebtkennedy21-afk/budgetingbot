"""
app.py — Budgeting Bot  (Streamlit)

Pages
-----
1. 📊 Dashboard      — monthly / yearly snapshot
2. 💰 Income         — add & manage income entries
3. 📌 Fixed Expenses — recurring fixed costs
4. 🛒 Variable Expenses — ad-hoc spending
5. 🎯 Financial Goals — savings / spending targets
6. 📈 Reports        — charts & trends
"""

import calendar
import hashlib
import hmac
import os
from datetime import date, datetime, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import database as db

# ---------------------------------------------------------------------------
# App-wide config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="💸 Budgeting Bot",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Auth config
# ---------------------------------------------------------------------------
AUTH_USER_ENV = "BUDGETBOT_USERNAME"
AUTH_SALT_ENV = "BUDGETBOT_PASSWORD_SALT"
AUTH_HASH_ENV = "BUDGETBOT_PASSWORD_HASH"
AUTH_TIMEOUT_ENV = "BUDGETBOT_SESSION_TIMEOUT_MINUTES"
AUTH_ITERATIONS = 200_000
AUTH_SETUP_FILE = ".streamlit/secrets.toml"


def _secret_or_env(name: str, default: str = "") -> str:
    # Prefer Streamlit secrets in cloud deployments; fall back to environment.
    try:
        value = st.secrets.get(name)
        if value not in (None, ""):
            return str(value)
    except Exception:
        pass
    return str(os.getenv(name, default) or default)


def _load_secrets_into_env() -> None:
    """Read .streamlit/secrets.toml and populate os.environ for keys not already set.
    This ensures credentials written by the setup flow are available even when
    Streamlit's secrets cache hasn't refreshed yet."""
    if not os.path.exists(AUTH_SETUP_FILE):
        return
    try:
        with open(AUTH_SETUP_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, raw_value = line.partition("=")
                key = key.strip()
                raw_value = raw_value.strip().strip('"').strip("'")
                if key and raw_value and not os.getenv(key):
                    os.environ[key] = raw_value
    except OSError:
        pass


def _hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, AUTH_ITERATIONS
    )
    return digest.hex()


def _upsert_local_secrets(values: dict) -> tuple[bool, str]:
    auth_keys = {
        AUTH_USER_ENV,
        AUTH_SALT_ENV,
        AUTH_HASH_ENV,
        AUTH_TIMEOUT_ENV,
    }

    try:
        os.makedirs(os.path.dirname(AUTH_SETUP_FILE), exist_ok=True)
        existing_lines = []
        if os.path.exists(AUTH_SETUP_FILE):
            with open(AUTH_SETUP_FILE, "r", encoding="utf-8") as f:
                existing_lines = f.read().splitlines()

        cleaned = []
        for line in existing_lines:
            stripped = line.lstrip()
            if any(
                stripped.startswith(f"{key}=") or stripped.startswith(f"{key} =")
                for key in auth_keys
            ):
                continue
            cleaned.append(line)

        if cleaned and cleaned[-1].strip():
            cleaned.append("")

        for key, value in values.items():
            cleaned.append(f'{key} = "{value}"')

        with open(AUTH_SETUP_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(cleaned).rstrip() + "\n")

        return True, AUTH_SETUP_FILE
    except OSError as exc:
        return False, str(exc)


def _is_session_expired(timeout_minutes: int) -> bool:
    if not st.session_state.get("authenticated"):
        return False

    last_activity = st.session_state.get("last_activity")
    if not last_activity:
        return True

    now = datetime.now(timezone.utc)
    elapsed = (now - datetime.fromisoformat(last_activity)).total_seconds()
    return elapsed > timeout_minutes * 60


def _logout() -> None:
    st.session_state["authenticated"] = False
    st.session_state["auth_user"] = ""
    st.session_state["last_activity"] = ""


def _render_login() -> None:
    # Show post-setup credential reminder (survives a single rerun)
    if st.session_state.get("_credential_warning"):
        env_vars = st.session_state["_credential_warning"]
        with st.expander(
            "⚠️ Action required — save these to Railway to prevent re-setup on restart",
            expanded=True,
        ):
            st.warning(
                "Your credentials are saved in a local file that is **deleted whenever "
                "the server container restarts** (Railway, Heroku, etc.). "
                "Copy the values below into your **Railway → Variables** panel so they "
                "persist across restarts. Your budget data will also be lost on restart "
                "unless you add a **Railway PostgreSQL plugin** (the app uses it automatically "
                "when `DATABASE_URL` is set)."
            )
            st.code(
                "\n".join(f"{k}={v}" for k, v in env_vars.items()),
                language="bash",
            )
        st.divider()

    st.title("🔒 Login Required")
    st.caption("Sign in to access your budgeting data.")

    username = _secret_or_env(AUTH_USER_ENV)
    password_salt = _secret_or_env(AUTH_SALT_ENV)
    password_hash = _secret_or_env(AUTH_HASH_ENV)

    if not username or not password_salt or not password_hash:
        st.warning("Authentication is not configured yet.")
        st.subheader("First-Time Setup")
        st.caption("Create your login credentials. The password is stored as a secure hash.")

        with st.form("auth_setup_form", clear_on_submit=True):
            setup_user = st.text_input("Choose a username")
            setup_password = st.text_input("Choose a password", type="password")
            setup_password_confirm = st.text_input("Confirm password", type="password")
            setup_timeout = st.number_input(
                "Session timeout (minutes)", min_value=1, max_value=480, value=30, step=1
            )
            setup_submitted = st.form_submit_button("Save credentials")

            if setup_submitted:
                if not setup_user.strip():
                    st.error("Username is required.")
                elif len(setup_password) < 8:
                    st.error("Password must be at least 8 characters.")
                elif setup_password != setup_password_confirm:
                    st.error("Passwords do not match.")
                else:
                    new_salt = os.urandom(16).hex()
                    new_hash = _hash_password(setup_password, new_salt)

                    values = {
                        AUTH_USER_ENV: setup_user.strip(),
                        AUTH_SALT_ENV: new_salt,
                        AUTH_HASH_ENV: new_hash,
                        AUTH_TIMEOUT_ENV: str(int(setup_timeout)),
                    }

                    ok, detail = _upsert_local_secrets(values)
                    # Ensure current process can authenticate immediately after rerun.
                    for key, value in values.items():
                        os.environ[key] = value

                    # Store credential values in session state so the next render
                    # can show them for the user to copy into Railway Variables.
                    st.session_state["_credential_warning"] = values
                    if not ok:
                        st.session_state["_credential_warning"]["_write_error"] = detail
                    st.rerun()
        st.stop()

    try:
        _ = bytes.fromhex(password_salt)
        _ = bytes.fromhex(password_hash)
    except ValueError:
        st.error("Authentication settings are invalid. Salt/hash must be hex strings.")
        st.stop()

    with st.form("login_form", clear_on_submit=True):
        entered_user = st.text_input("Username")
        entered_password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

        if submitted:
            entered_hash = _hash_password(entered_password, password_salt)
            user_match = hmac.compare_digest(entered_user, username)
            pass_match = hmac.compare_digest(entered_hash, password_hash)

            if user_match and pass_match:
                st.session_state["authenticated"] = True
                st.session_state["auth_user"] = entered_user
                st.session_state["last_activity"] = datetime.now(timezone.utc).isoformat()
                st.session_state.pop("_credential_warning", None)
                st.rerun()
            else:
                st.error("Invalid username or password.")


# Load credentials from secrets.toml into env vars so they survive reruns
# even when Streamlit's secrets cache hasn't refreshed yet.
_load_secrets_into_env()

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "auth_user" not in st.session_state:
    st.session_state["auth_user"] = ""
if "last_activity" not in st.session_state:
    st.session_state["last_activity"] = ""

try:
    session_timeout_minutes = max(1, int(_secret_or_env(AUTH_TIMEOUT_ENV, "30")))
except ValueError:
    session_timeout_minutes = 30
if _is_session_expired(session_timeout_minutes):
    _logout()
    st.warning("Your session expired. Please log in again.")

if not st.session_state["authenticated"]:
    _render_login()
    st.stop()

st.session_state["last_activity"] = datetime.now(timezone.utc).isoformat()

db_online = True
db_error = ""
try:
    db.init_db()
except Exception as exc:
    db_online = False
    db_error = str(exc)

INCOME_CATEGORIES = [
    "Salary",
    "Freelance",
    "Investment",
    "Rental",
    "Gift",
    "Other",
]

INCOME_SOURCES = db.INCOME_SOURCES

FIXED_EXPENSE_CATEGORIES = [
    "Housing",
    "Utilities",
    "Insurance",
    "Subscriptions",
    "Loan / Debt",
    "Transport",
    "Other",
]

VARIABLE_EXPENSE_CATEGORIES = [
    "Food & Dining",
    "Groceries",
    "Entertainment",
    "Healthcare",
    "Clothing",
    "Transport",
    "Travel",
    "Personal Care",
    "Education",
    "Gifts",
    "Other",
]

MONTHS = {i: calendar.month_name[i] for i in range(1, 13)}

# ---------------------------------------------------------------------------
# Sidebar — navigation & period selector
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("💸 Budgeting Bot")
    st.caption(f"Signed in as: {st.session_state['auth_user']}")
    if db_online:
        st.markdown(
            "<span style='color:#16a34a;'>Database: Online</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<span style='color:#dc2626;'>Database: Offline</span>",
            unsafe_allow_html=True,
        )
    if st.button("🚪 Log out", width="stretch"):
        _logout()
        st.rerun()
    st.markdown("---")

    page = st.radio(
        "Navigate",
        [
            "📊 Dashboard",
            "💰 Income",
            "📌 Fixed Expenses",
            "🛒 Variable Expenses",
            "💵 Savings",
            "💳 Debt",
            "🎯 Financial Goals",
            "📈 Reports",
        ],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.subheader("Period Filter")
    today = date.today()
    sel_year = st.selectbox(
        "Year",
        list(range(today.year - 3, today.year + 2)),
        index=3,
    )
    sel_month = st.selectbox(
        "Month",
        list(MONTHS.keys()),
        format_func=lambda m: MONTHS[m],
        index=today.month - 1,
    )
    st.markdown("---")
    st.caption("Data stored in local SQLite database.")

if not db_online:
    st.error("Database is offline. Please check your database connection and restart the app.")
    if db_error:
        st.caption(f"Connection error: {db_error}")
    st.stop()


# ---------------------------------------------------------------------------
# Helper: metric card
# ---------------------------------------------------------------------------
def _metric(label: str, value: float, delta: float = None, prefix: str = "$"):
    fmt = f"{prefix}{value:,.2f}"
    if delta is not None:
        st.metric(label, fmt, f"{prefix}{delta:+,.2f}")
    else:
        st.metric(label, fmt)


def _to_df(rows: list, columns: list = None) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)


# ===========================================================================
# PAGE: DASHBOARD
# ===========================================================================
if page == "📊 Dashboard":
    st.title(f"📊 Dashboard — {MONTHS[sel_month]} {sel_year}")

    # --- gather data --------------------------------------------------------
    income_rows = db.get_income(year=sel_year, month=sel_month)
    var_rows = db.get_variable_expenses(year=sel_year, month=sel_month)
    fixed_cost = db.get_monthly_fixed_cost(sel_year, sel_month)
    goals = db.get_financial_goals()

    total_income = sum(r["amount"] for r in income_rows)
    total_variable = sum(r["amount"] for r in var_rows)
    total_expenses = fixed_cost + total_variable
    net = total_income - total_expenses

    # --- KPI row ------------------------------------------------------------
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        _metric("Total Income", total_income)
    with col2:
        _metric("Fixed Expenses", fixed_cost)
    with col3:
        _metric("Variable Expenses", total_variable)
    with col4:
        color = "normal" if net >= 0 else "inverse"
        st.metric("Net Balance", f"${net:,.2f}", delta=f"${net:+,.2f}", delta_color=color)

    st.markdown("---")

    # --- expense breakdown pie ----------------------------------------------
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Expense Breakdown")
        if total_expenses > 0:
            pie_data = {"Fixed": fixed_cost, "Variable": total_variable}
            fig = px.pie(
                names=list(pie_data.keys()),
                values=list(pie_data.values()),
                color_discrete_sequence=["#EF553B", "#636EFA"],
            )
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("No expenses recorded this month.")

    with col_right:
        st.subheader("Income vs Expenses")
        bar_fig = go.Figure(
            data=[
                go.Bar(name="Income", x=["This Month"], y=[total_income], marker_color="#00CC96"),
                go.Bar(name="Fixed Exp.", x=["This Month"], y=[fixed_cost], marker_color="#EF553B"),
                go.Bar(name="Variable Exp.", x=["This Month"], y=[total_variable], marker_color="#636EFA"),
            ]
        )
        bar_fig.update_layout(
            barmode="group", margin=dict(t=0, b=0), height=300, yaxis_title="Amount ($)"
        )
        st.plotly_chart(bar_fig, width="stretch")

    # --- variable expense by category ---------------------------------------
    if var_rows:
        st.subheader("Variable Expenses by Category")
        df_var = pd.DataFrame(var_rows)
        cat_sum = df_var.groupby("category")["amount"].sum().reset_index()
        cat_fig = px.bar(
            cat_sum,
            x="category",
            y="amount",
            labels={"amount": "Amount ($)", "category": "Category"},
            color="category",
        )
        cat_fig.update_layout(showlegend=False, margin=dict(t=0), height=300)
        st.plotly_chart(cat_fig, width="stretch")

    # --- goals summary ------------------------------------------------------
    if goals:
        st.subheader("🎯 Goals Progress")
        for g in goals:
            pct = min(g["current_amount"] / g["target_amount"] * 100, 100)
            st.markdown(
                f"**{g['name']}** — ${g['current_amount']:,.2f} / ${g['target_amount']:,.2f}"
                + (f"  *(target: {g['target_date']})*" if g["target_date"] else "")
            )
            st.progress(pct / 100)

    # --- savings snapshot ---------------------------------------------------
    savings_balances = db.get_all_savings_balances()
    total_saved = sum(savings_balances.values())
    if total_saved > 0 or any(True for _ in savings_balances):
        st.markdown("---")
        st.subheader("💵 Savings Snapshot")
        sav_cols = st.columns(len(db.SAVINGS_ACCOUNTS) + 1)
        for i, acct in enumerate(db.SAVINGS_ACCOUNTS):
            with sav_cols[i]:
                st.metric(acct, f"${savings_balances[acct]:,.2f}")
        with sav_cols[-1]:
            st.metric("Total Savings", f"${total_saved:,.2f}")

    # --- debt snapshot ------------------------------------------------------
    debts_snapshot = db.get_debts()
    total_debt_dash = sum(d["current_balance"] for d in debts_snapshot)
    if debts_snapshot:
        st.markdown("---")
        st.subheader("💳 Debt Snapshot")
        debt_dash_cols = st.columns(min(len(debts_snapshot), 4) + 1)
        for i, d in enumerate(debts_snapshot[:4]):
            with debt_dash_cols[i]:
                st.metric(d["name"], f"${d['current_balance']:,.2f}")
        with debt_dash_cols[-1]:
            st.metric("Total Debt", f"${total_debt_dash:,.2f}")


# ===========================================================================
# PAGE: INCOME
# ===========================================================================
elif page == "💰 Income":
    st.title("💰 Income")

    # Fetch all income for month and year across all sources
    month_rows = db.get_income(year=sel_year, month=sel_month)
    year_rows  = db.get_income(year=sel_year)

    month_by_src = {s: [] for s in INCOME_SOURCES}
    year_by_src  = {s: [] for s in INCOME_SOURCES}
    for r in month_rows:
        month_by_src.setdefault(r["source"], []).append(r)
    for r in year_rows:
        year_by_src.setdefault(r["source"], []).append(r)

    # --- top summary strip -------------------------------------------------
    total_month = sum(r["amount"] for r in month_rows)
    total_year  = sum(r["amount"] for r in year_rows)
    kpi_cols = st.columns(len(INCOME_SOURCES) + 1)
    for i, src in enumerate(INCOME_SOURCES):
        with kpi_cols[i]:
            src_mo = sum(r['amount'] for r in month_by_src.get(src, []))
            st.markdown(
                f"<div style='font-size:0.75rem;color:gray;margin-bottom:2px'>{src} — {MONTHS[sel_month]}</div>"
                f"<div style='font-size:1rem;font-weight:600'>${src_mo:,.2f}</div>",
                unsafe_allow_html=True,
            )
    with kpi_cols[-1]:
        st.markdown(
            f"<div style='font-size:0.75rem;color:gray;margin-bottom:2px'>Total This Month</div>"
            f"<div style='font-size:1rem;font-weight:600'>${total_month:,.2f}</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # --- one card per income source ----------------------------------------
    card_cols = st.columns(len(INCOME_SOURCES))
    for col_idx, source in enumerate(INCOME_SOURCES):
        src_month = month_by_src.get(source, [])
        src_year  = year_by_src.get(source, [])
        month_total = sum(r["amount"] for r in src_month)
        year_total  = sum(r["amount"] for r in src_year)

        with card_cols[col_idx]:
            with st.container(border=True):
                st.subheader(source)
                m1, m2 = st.columns(2)
                with m1:
                    st.markdown(
                        f"<div style='font-size:0.72rem;color:gray;margin-bottom:2px'>{MONTHS[sel_month]}</div>"
                        f"<div style='font-size:0.95rem;font-weight:600'>${month_total:,.2f}</div>",
                        unsafe_allow_html=True,
                    )
                with m2:
                    st.markdown(
                        f"<div style='font-size:0.72rem;color:gray;margin-bottom:2px'>{sel_year} Total</div>"
                        f"<div style='font-size:0.95rem;font-weight:600'>${year_total:,.2f}</div>",
                        unsafe_allow_html=True,
                    )

                st.markdown("**Add Income**")
                with st.form(f"income_form_{col_idx}", clear_on_submit=True):
                    inc_cat = st.selectbox("Category", INCOME_CATEGORIES,
                                           key=f"inc_cat_{col_idx}")
                    inc_amount = st.number_input("Amount ($)", min_value=0.01,
                                                 step=0.01, format="%.2f",
                                                 key=f"inc_amt_{col_idx}")
                    inc_date = st.date_input("Date", value=today,
                                             key=f"inc_date_{col_idx}")
                    inc_desc = st.text_input("Description (optional)",
                                             key=f"inc_desc_{col_idx}")
                    submitted = st.form_submit_button("Add Income", width="stretch")
                    if submitted:
                        if inc_amount <= 0:
                            st.error("Amount must be greater than zero.")
                        else:
                            db.add_income(str(inc_date), inc_amount, inc_cat,
                                          source, inc_desc)
                            st.success(f"✅ Added ${inc_amount:,.2f} to {source}.")
                            st.rerun()

                st.markdown(f"**{MONTHS[sel_month]} Entries**")
                if src_month:
                    for entry in sorted(src_month, key=lambda r: r["date"], reverse=True):
                        label = f"{entry['date']} • ${entry['amount']:,.2f} • {entry['category']}"
                        with st.expander(label):
                            with st.form(f"edit_inc_{col_idx}_{entry['id']}"):
                                e1, e2 = st.columns(2)
                                with e1:
                                    e_date = st.date_input(
                                        "Date",
                                        value=date.fromisoformat(str(entry["date"])),
                                        key=f"e_inc_date_{col_idx}_{entry['id']}",
                                    )
                                    e_amount = st.number_input(
                                        "Amount ($)", min_value=0.01, step=0.01,
                                        format="%.2f", value=float(entry["amount"]),
                                        key=f"e_inc_amt_{col_idx}_{entry['id']}",
                                    )
                                with e2:
                                    cur_cat = str(entry["category"])
                                    cat_opts = INCOME_CATEGORIES.copy()
                                    if cur_cat not in cat_opts:
                                        cat_opts.append(cur_cat)
                                    e_cat = st.selectbox(
                                        "Category", cat_opts,
                                        index=cat_opts.index(cur_cat),
                                        key=f"e_inc_cat_{col_idx}_{entry['id']}",
                                    )
                                    e_src = st.selectbox(
                                        "Source", INCOME_SOURCES,
                                        index=INCOME_SOURCES.index(source),
                                        key=f"e_inc_src_{col_idx}_{entry['id']}",
                                    )
                                e_desc = st.text_input(
                                    "Description (optional)",
                                    value=entry.get("description") or "",
                                    key=f"e_inc_desc_{col_idx}_{entry['id']}",
                                )
                                ac1, ac2 = st.columns(2)
                                with ac1:
                                    save_it = st.form_submit_button("Save", width="stretch")
                                with ac2:
                                    del_it = st.form_submit_button("Delete", width="stretch")
                                if save_it:
                                    db.update_income(
                                        int(entry["id"]), str(e_date),
                                        float(e_amount), e_cat, e_src, e_desc,
                                    )
                                    st.success("Entry updated.")
                                    st.rerun()
                                if del_it:
                                    db.delete_income(int(entry["id"]))
                                    st.success("Entry deleted.")
                                    st.rerun()
                else:
                    st.caption(f"No income recorded for {MONTHS[sel_month]}.")


# ===========================================================================
# PAGE: FIXED EXPENSES
# ===========================================================================
elif page == "📌 Fixed Expenses":
    st.title("📌 Fixed Expenses")
    st.caption(
        "Fixed expenses recur automatically each month (or year). "
        "They are included in budget calculations as long as they are active."
    )

    show_active = st.checkbox("Show active only", value=True)
    rows = db.get_fixed_expenses(active_only=show_active)
    all_fixed_rows = db.get_fixed_expenses(active_only=False)
    debts_for_link = db.get_debts()
    debt_options = {f"{d['name']} (ID {d['id']})": d["id"] for d in debts_for_link}
    debt_id_to_label = {d["id"]: f"{d['name']} (ID {d['id']})" for d in debts_for_link}
    linked_debt_owner = {
        int(row["linked_debt_id"]): int(row["id"])
        for row in all_fixed_rows
        if row.get("linked_debt_id") is not None
    }
    extra_categories = sorted({row["category"] for row in rows if row["category"] not in FIXED_EXPENSE_CATEGORIES})
    category_options = FIXED_EXPENSE_CATEGORIES + extra_categories
    rows_by_category = {category: [] for category in category_options}
    for row in rows:
        rows_by_category.setdefault(row["category"], []).append(row)

    monthly_total = db.get_monthly_fixed_cost(sel_year, sel_month)
    st.markdown(f"**Monthly cost for {MONTHS[sel_month]} {sel_year}: ${monthly_total:,.2f}**")

    st.subheader("Fixed Expense Categories")
    st.caption("Each category card lets you add new expenses and manage the ones already saved in that category.")

    card_columns = st.columns(3)
    for idx, category in enumerate(category_options):
        category_rows = rows_by_category.get(category, [])
        with card_columns[idx % 3]:
            with st.container(border=True):
                st.markdown(f"### {category}")
                st.caption(f"{len(category_rows)} expense(s) in this category")

                with st.form(f"fixed_form_{idx}", clear_on_submit=True):
                    fix_name = st.text_input(
                        "Name",
                        placeholder=f"Add a {category.lower()} expense",
                        key=f"fix_name_{idx}",
                    )
                    fix_amount = st.number_input(
                        "Amount ($)",
                        min_value=0.01,
                        step=0.01,
                        format="%.2f",
                        key=f"fix_amount_{idx}",
                    )
                    freq_col, start_col = st.columns(2)
                    with freq_col:
                        fix_freq = st.selectbox(
                            "Frequency",
                            ["monthly", "yearly"],
                            key=f"fix_freq_{idx}",
                        )
                    with start_col:
                        fix_start = st.date_input(
                            "Start Date",
                            value=today.replace(day=1),
                            key=f"fix_start_{idx}",
                        )
                    fix_end = st.date_input(
                        "End Date",
                        value=None,
                        help="Leave blank / clear to indicate this expense is ongoing.",
                        key=f"fix_end_{idx}",
                    )
                    fix_desc = st.text_input(
                        "Description (optional)",
                        key=f"fix_desc_{idx}",
                    )
                    submitted = st.form_submit_button(f"Add to {category}", width="stretch")
                    if submitted:
                        if not fix_name.strip():
                            st.error("Name is required.")
                        elif fix_amount <= 0:
                            st.error("Amount must be greater than zero.")
                        else:
                            end_str = str(fix_end) if fix_end else None
                            db.add_fixed_expense(
                                fix_name.strip(),
                                fix_amount,
                                category,
                                fix_freq,
                                str(fix_start),
                                end_str,
                                fix_desc,
                            )
                            st.success(f"✅ Added fixed expense: {fix_name}")
                            st.rerun()

                st.markdown("**Saved Expenses**")
                if category_rows:
                    for expense in category_rows:
                        linked_label = None
                        if expense.get("linked_debt_id") is not None:
                            linked_label = debt_id_to_label.get(int(expense["linked_debt_id"]), f"Debt ID {int(expense['linked_debt_id'])}")
                        expander_label = f"{expense['name']} • ${expense['amount']:,.2f} • {expense['frequency'].title()}"
                        with st.expander(expander_label):
                            start_value = date.fromisoformat(str(expense["start_date"]))
                            end_value = (
                                date.fromisoformat(str(expense["end_date"]))
                                if expense.get("end_date")
                                else None
                            )
                            if linked_label:
                                st.caption(f"Linked debt: {linked_label}")

                            with st.form(f"edit_fixed_{expense['id']}"):
                                edit_name = st.text_input(
                                    "Name",
                                    value=expense["name"],
                                    key=f"edit_fix_name_{expense['id']}",
                                )
                                edit_amount = st.number_input(
                                    "Amount ($)",
                                    min_value=0.01,
                                    step=0.01,
                                    format="%.2f",
                                    value=float(expense["amount"]),
                                    key=f"edit_fix_amount_{expense['id']}",
                                )
                                edit_col1, edit_col2 = st.columns(2)
                                with edit_col1:
                                    edit_category = st.selectbox(
                                        "Category",
                                        category_options,
                                        index=category_options.index(expense["category"]),
                                        key=f"edit_fix_category_{expense['id']}",
                                    )
                                    edit_start = st.date_input(
                                        "Start Date",
                                        value=start_value,
                                        key=f"edit_fix_start_{expense['id']}",
                                    )
                                with edit_col2:
                                    edit_freq = st.selectbox(
                                        "Frequency",
                                        ["monthly", "yearly"],
                                        index=["monthly", "yearly"].index(expense["frequency"]),
                                        key=f"edit_fix_freq_{expense['id']}",
                                    )
                                    edit_end = st.date_input(
                                        "End Date",
                                        value=end_value,
                                        help="Leave blank / clear to indicate this expense is ongoing.",
                                        key=f"edit_fix_end_{expense['id']}",
                                    )
                                edit_desc = st.text_input(
                                    "Description (optional)",
                                    value=expense.get("description") or "",
                                    key=f"edit_fix_desc_{expense['id']}",
                                )

                                selected_debt_label = "Not linked"
                                if debts_for_link:
                                    available_debt_options = {
                                        label: debt_id
                                        for label, debt_id in debt_options.items()
                                        if linked_debt_owner.get(int(debt_id)) in (None, int(expense["id"]))
                                    }
                                    debt_labels = ["Not linked", *available_debt_options.keys()]
                                    current_debt_label = (
                                        debt_id_to_label.get(int(expense["linked_debt_id"]), "Not linked")
                                        if expense.get("linked_debt_id") is not None
                                        else "Not linked"
                                    )
                                    if len(debt_labels) > 1:
                                        selected_debt_label = st.selectbox(
                                            "Linked Debt",
                                            debt_labels,
                                            index=debt_labels.index(current_debt_label),
                                            key=f"edit_fix_debt_{expense['id']}",
                                        )
                                    else:
                                        st.caption("No available debts to link. Unlink an existing debt first.")

                                action_col1, action_col2 = st.columns(2)
                                with action_col1:
                                    save_changes = st.form_submit_button("Save Changes", width="stretch")
                                with action_col2:
                                    delete_expense = st.form_submit_button("Delete Expense", width="stretch")

                                if save_changes:
                                    if not edit_name.strip():
                                        st.error("Name is required.")
                                    elif edit_amount <= 0:
                                        st.error("Amount must be greater than zero.")
                                    else:
                                        db.update_fixed_expense(
                                            int(expense["id"]),
                                            edit_name.strip(),
                                            edit_amount,
                                            edit_category,
                                            edit_freq,
                                            str(edit_start),
                                            str(edit_end) if edit_end else None,
                                            edit_desc,
                                        )
                                        if debts_for_link:
                                            if selected_debt_label == "Not linked":
                                                db.unlink_fixed_expense_from_debt(int(expense["id"]))
                                            elif selected_debt_label in available_debt_options:
                                                db.link_fixed_expense_to_debt(
                                                    int(expense["id"]),
                                                    available_debt_options[selected_debt_label],
                                                )
                                        st.success(f"Updated {edit_name.strip()}.")
                                        st.rerun()

                                if delete_expense:
                                    db.delete_fixed_expense(int(expense["id"]))
                                    st.success(f"Deleted {expense['name']}.")
                                    st.rerun()
                else:
                    empty_message = "No active expenses in this category yet." if show_active else "No expenses in this category yet."
                    st.caption(empty_message)

    if not rows:
        st.info("No fixed expenses found for the current filter.")


# ===========================================================================
# PAGE: VARIABLE EXPENSES
# ===========================================================================
elif page == "🛒 Variable Expenses":
    st.title("🛒 Variable Expenses")

    rows = db.get_variable_expenses(year=sel_year, month=sel_month)
    all_var_rows = db.get_variable_expenses()

    entry_col, review_col = st.columns([1, 2])
    with entry_col:
        with st.container(border=True):
            st.subheader("Quick Add")
            with st.form("var_form", clear_on_submit=True):
                var_cat = st.selectbox("Category", VARIABLE_EXPENSE_CATEGORIES)
                var_amount = st.number_input("Amount ($)", min_value=0.01, step=0.01, format="%.2f")
                var_date = st.date_input("Date", value=today)
                var_desc = st.text_input("Description (optional)")
                submitted = st.form_submit_button("Add Expense", width="stretch")
                if submitted:
                    if var_amount <= 0:
                        st.error("Amount must be greater than zero.")
                    else:
                        duplicates = [
                            r for r in all_var_rows
                            if r["date"] == str(var_date)
                            and float(r["amount"]) == float(var_amount)
                            and r["category"] == var_cat
                        ]
                        if duplicates:
                            st.warning("A similar expense already exists for this date/category/amount.")
                        db.add_variable_expense(str(var_date), var_amount, var_cat, var_desc)
                        st.success(f"✅ Added ${var_amount:,.2f} expense on {var_date}.")
                        st.rerun()

    with review_col:
        st.subheader(f"Variable Expenses — {MONTHS[sel_month]} {sel_year}")
        if rows:
            df_month = _to_df(rows)
            total = float(df_month["amount"].sum())
            txn_count = int(len(df_month))
            avg_spend = total / txn_count if txn_count else 0.0
            cat_totals = df_month.groupby("category")["amount"].sum().sort_values(ascending=False)
            top_category = cat_totals.index[0] if not cat_totals.empty else "N/A"

            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Total This Month", f"${total:,.2f}")
            with m2:
                st.metric("Transactions", f"{txn_count}")
            with m3:
                st.metric("Average Spend", f"${avg_spend:,.2f}")
            with m4:
                st.metric("Biggest Category", top_category)

            insight_col1, insight_col2 = st.columns(2)
            with insight_col1:
                df_cat = df_month.groupby("category")["amount"].sum().reset_index()
                fig_cat = px.bar(
                    df_cat,
                    x="category",
                    y="amount",
                    color="category",
                    labels={"amount": "Amount ($)", "category": "Category"},
                    title="Spending by Category",
                )
                fig_cat.update_layout(showlegend=False, height=280, margin=dict(t=40, b=0))
                st.plotly_chart(fig_cat, width="stretch")

            with insight_col2:
                df_all = _to_df(all_var_rows)
                if not df_all.empty:
                    df_all["date"] = pd.to_datetime(df_all["date"])
                    window_start = pd.Timestamp(today) - pd.Timedelta(days=29)
                    df_30 = df_all[df_all["date"] >= window_start].copy()
                else:
                    df_30 = pd.DataFrame()

                if not df_30.empty:
                    df_trend = df_30.groupby("date")["amount"].sum().reset_index()
                    fig_trend = px.line(
                        df_trend,
                        x="date",
                        y="amount",
                        title="Last 30 Days Spend",
                        labels={"amount": "Amount ($)", "date": "Date"},
                        markers=True,
                    )
                    fig_trend.update_layout(height=280, margin=dict(t=40, b=0))
                    st.plotly_chart(fig_trend, width="stretch")
                else:
                    st.info("No variable expenses in the last 30 days.")

            st.markdown("---")
            tab_labels = ["All", *VARIABLE_EXPENSE_CATEGORIES]
            tabs = st.tabs(tab_labels)
            for idx, tab_label in enumerate(tab_labels):
                with tabs[idx]:
                    df_tab = (
                        df_month.copy()
                        if tab_label == "All"
                        else df_month[df_month["category"] == tab_label].copy()
                    )

                    filter_col1, filter_col2 = st.columns(2)
                    with filter_col1:
                        search_text = st.text_input(
                            "Search description",
                            key=f"var_search_{idx}",
                            placeholder="Type to filter",
                        ).strip().lower()
                    with filter_col2:
                        min_amount = st.number_input(
                            "Min amount ($)",
                            min_value=0.0,
                            step=1.0,
                            value=0.0,
                            key=f"var_min_{idx}",
                        )

                    if search_text:
                        desc_values = df_tab["description"].fillna("").astype(str).str.lower()
                        df_tab = df_tab[desc_values.str.contains(search_text)]
                    df_tab = df_tab[df_tab["amount"] >= float(min_amount)]

                    if df_tab.empty:
                        st.info("No expenses match this filter.")
                    else:
                        df_show = df_tab[["date", "amount", "category", "description"]].copy()
                        df_show.columns = ["Date", "Amount ($)", "Category", "Description"]
                        df_show["Amount ($)"] = df_show["Amount ($)"].map(lambda x: f"{x:,.2f}")
                        st.dataframe(df_show, width="stretch", hide_index=True)

                        st.caption("Inline Actions")
                        for expense in df_tab.sort_values("date", ascending=False).to_dict("records"):
                            row_label = f"{expense['date']} • ${expense['amount']:,.2f} • {expense['category']}"
                            with st.expander(row_label):
                                with st.form(f"edit_var_{idx}_{int(expense['id'])}"):
                                    edit_c1, edit_c2 = st.columns(2)
                                    with edit_c1:
                                        edit_date = st.date_input(
                                            "Date",
                                            value=date.fromisoformat(str(expense["date"])),
                                            key=f"edit_var_date_{idx}_{int(expense['id'])}",
                                        )
                                        edit_amount = st.number_input(
                                            "Amount ($)",
                                            min_value=0.01,
                                            step=0.01,
                                            format="%.2f",
                                            value=float(expense["amount"]),
                                            key=f"edit_var_amt_{idx}_{int(expense['id'])}",
                                        )
                                    with edit_c2:
                                        current_cat = str(expense["category"])
                                        edit_cat_options = VARIABLE_EXPENSE_CATEGORIES.copy()
                                        if current_cat not in edit_cat_options:
                                            edit_cat_options.append(current_cat)
                                        edit_cat = st.selectbox(
                                            "Category",
                                            edit_cat_options,
                                            index=edit_cat_options.index(current_cat),
                                            key=f"edit_var_cat_{idx}_{int(expense['id'])}",
                                        )
                                        edit_desc = st.text_input(
                                            "Description (optional)",
                                            value=expense.get("description") or "",
                                            key=f"edit_var_desc_{idx}_{int(expense['id'])}",
                                        )

                                    act_c1, act_c2 = st.columns(2)
                                    with act_c1:
                                        save_edit = st.form_submit_button("Save Changes", width="stretch")
                                    with act_c2:
                                        delete_item = st.form_submit_button("Delete Expense", width="stretch")

                                    if save_edit:
                                        db.update_variable_expense(
                                            int(expense["id"]),
                                            str(edit_date),
                                            float(edit_amount),
                                            edit_cat,
                                            edit_desc,
                                        )
                                        st.success("Expense updated.")
                                        st.rerun()

                                    if delete_item:
                                        db.delete_variable_expense(int(expense["id"]))
                                        st.success("Expense deleted.")
                                        st.rerun()
        else:
            st.info("No variable expenses for this period.")


# ===========================================================================
# PAGE: SAVINGS
# ===========================================================================
elif page == "💵 Savings":
    st.title("💵 Savings")

    SAVINGS_ACCOUNTS = db.SAVINGS_ACCOUNTS

    # --- current balances KPI row ------------------------------------------
    balances = db.get_all_savings_balances()
    total_savings = sum(balances.values())

    kpi_cols = st.columns(len(SAVINGS_ACCOUNTS) + 1)
    for i, acct in enumerate(SAVINGS_ACCOUNTS):
        with kpi_cols[i]:
            st.metric(acct, f"${balances[acct]:,.2f}")
    with kpi_cols[-1]:
        st.metric("Total Savings", f"${total_savings:,.2f}")

    st.markdown("---")

    layout_left, layout_right = st.columns([1, 2])

    with layout_left:
        with st.container(border=True):
            st.subheader("Add Transaction")
            with st.form("savings_form", clear_on_submit=True):
                sav_account = st.selectbox("Account", SAVINGS_ACCOUNTS)
                sav_type = st.selectbox("Type", ["deposit", "withdrawal"])
                sav_amount = st.number_input(
                    "Amount ($)", min_value=0.01, step=0.01, format="%.2f"
                )
                sav_date = st.date_input("Date", value=today)
                sav_desc = st.text_input("Description (optional)")
                submitted = st.form_submit_button("Add Transaction", width="stretch")
                if submitted:
                    if sav_amount <= 0:
                        st.error("Amount must be greater than zero.")
                    else:
                        current_bal = db.get_savings_balance(sav_account)
                        if sav_type == "withdrawal" and sav_amount > current_bal:
                            st.error(
                                f"Withdrawal of ${sav_amount:,.2f} exceeds the current "
                                f"{sav_account} balance of ${current_bal:,.2f}."
                            )
                        else:
                            db.add_savings_transaction(
                                sav_account, str(sav_date), sav_amount, sav_type, sav_desc
                            )
                            action = "Deposited" if sav_type == "deposit" else "Withdrew"
                            st.success(
                                f"✅ {action} ${sav_amount:,.2f} {'to' if sav_type == 'deposit' else 'from'} {sav_account}."
                            )
                            st.rerun()

    with layout_right:
        st.subheader("Activity")
        tab_labels = ["All", *SAVINGS_ACCOUNTS]
        account_tabs = st.tabs(tab_labels)

        for idx, tab_label in enumerate(tab_labels):
            with account_tabs[idx]:
                rows = (
                    db.get_savings_transactions()
                    if tab_label == "All"
                    else db.get_savings_transactions(account=tab_label)
                )

                if rows:
                    df_sav = _to_df(rows)

                    chart_col, table_col = st.columns([1, 1])
                    with chart_col:
                        if tab_label != "All":
                            df_chart = df_sav.sort_values("date").copy()
                            df_chart["signed"] = df_chart.apply(
                                lambda r: r["amount"] if r["type"] == "deposit" else -r["amount"],
                                axis=1,
                            )
                            df_chart["balance"] = df_chart["signed"].cumsum()
                            fig_bal = px.line(
                                df_chart,
                                x="date",
                                y="balance",
                                title=f"{tab_label} Running Balance",
                                labels={"balance": "Balance ($)", "date": "Date"},
                                markers=True,
                            )
                            fig_bal.update_layout(height=280, margin=dict(t=40, b=0))
                            st.plotly_chart(fig_bal, width="stretch")
                        else:
                            bar_data = [{"Account": a, "Balance ($)": balances[a]} for a in SAVINGS_ACCOUNTS]
                            fig_bar = px.bar(
                                bar_data,
                                x="Account",
                                y="Balance ($)",
                                color="Account",
                                title="Current Balance by Account",
                            )
                            fig_bar.update_layout(showlegend=False, height=280, margin=dict(t=40, b=0))
                            st.plotly_chart(fig_bar, width="stretch")

                    with table_col:
                        st.caption("Recent Transactions")
                        if tab_label == "All":
                            df_show = df_sav[["id", "account", "date", "type", "amount", "description"]].copy()
                            df_show.columns = ["ID", "Account", "Date", "Type", "Amount ($)", "Description"]
                        else:
                            df_show = df_sav[["id", "date", "type", "amount", "description"]].copy()
                            df_show.columns = ["ID", "Date", "Type", "Amount ($)", "Description"]
                        df_show["Amount ($)"] = df_show["Amount ($)"].map(lambda x: f"{x:,.2f}")
                        st.dataframe(df_show, width="stretch", hide_index=True)

                    st.caption("Edit / Delete Transactions")
                    for row_idx, row in enumerate(rows):
                        sign = "+" if row["type"] == "deposit" else "-"
                        exp_label = (
                            f"{row['date']} · {row.get('account', tab_label)} · "
                            f"{sign}${row['amount']:,.2f}"
                        )
                        with st.expander(exp_label, expanded=False):
                            with st.form(f"edit_sav_{idx}_{row_idx}_{row['id']}"):
                                f1, f2 = st.columns(2)
                                with f1:
                                    e_acct = st.selectbox(
                                        "Account", SAVINGS_ACCOUNTS,
                                        index=SAVINGS_ACCOUNTS.index(row["account"]) if row["account"] in SAVINGS_ACCOUNTS else 0,
                                        key=f"es_acct_{idx}_{row_idx}_{row['id']}",
                                    )
                                    e_type = st.selectbox(
                                        "Type", ["deposit", "withdrawal"],
                                        index=0 if row["type"] == "deposit" else 1,
                                        key=f"es_type_{idx}_{row_idx}_{row['id']}",
                                    )
                                with f2:
                                    e_date = st.date_input(
                                        "Date",
                                        value=date.fromisoformat(str(row["date"])),
                                        key=f"es_date_{idx}_{row_idx}_{row['id']}",
                                    )
                                    e_amount = st.number_input(
                                        "Amount ($)", min_value=0.01, step=0.01,
                                        format="%.2f", value=float(row["amount"]),
                                        key=f"es_amt_{idx}_{row_idx}_{row['id']}",
                                    )
                                e_desc = st.text_input(
                                    "Description (optional)",
                                    value=row.get("description") or "",
                                    key=f"es_desc_{idx}_{row_idx}_{row['id']}",
                                )
                                ac1, ac2 = st.columns(2)
                                with ac1:
                                    save_it = st.form_submit_button("Save", width="stretch")
                                with ac2:
                                    del_it = st.form_submit_button("Delete", width="stretch")
                                if save_it:
                                    db.update_savings_transaction(
                                        int(row["id"]), e_acct, str(e_date),
                                        float(e_amount), e_type, e_desc,
                                    )
                                    st.success("Transaction updated.")
                                    st.rerun()
                                if del_it:
                                    db.delete_savings_transaction(int(row["id"]))
                                    st.success("Transaction deleted.")
                                    st.rerun()
                else:
                    st.info("No savings transactions recorded for this view.")


# ===========================================================================
# PAGE: DEBT
# ===========================================================================
elif page == "💳 Debt":
    st.title("💳 Debt")

    debts = db.get_debts()
    total_debt = sum(d["current_balance"] for d in debts)
    total_original = sum(d["original_amount"] for d in debts)
    total_paid = total_original - total_debt

    # --- KPI row ------------------------------------------------------------
    k1, k2, k3 = st.columns(3)
    with k1:
        st.metric("Total Remaining Debt", f"${total_debt:,.2f}")
    with k2:
        st.metric("Original Debt", f"${total_original:,.2f}")
    with k3:
        st.metric("Total Paid Off", f"${total_paid:,.2f}")

    st.markdown("---")

    # --- add debt form ------------------------------------------------------
    with st.expander("➕ Add Debt", expanded=True):
        with st.form("debt_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                debt_name = st.text_input("Debt Name (e.g. Car Loan, Credit Card)")
                debt_original = st.number_input(
                    "Original Amount ($)", min_value=0.01, step=0.01, format="%.2f"
                )
                debt_balance = st.number_input(
                    "Current Balance ($)", min_value=0.00, step=0.01, format="%.2f"
                )
            with c2:
                debt_cat = st.selectbox("Category", db.DEBT_CATEGORIES)
                debt_rate = st.number_input(
                    "Interest Rate (APR %)", min_value=0.0, max_value=100.0, step=0.01, format="%.2f"
                )
                debt_min = st.number_input(
                    "Minimum Payment ($)", min_value=0.0, step=0.01, format="%.2f"
                )
                debt_due = st.date_input(
                    "Minimum Payment Due Date (optional)", value=None
                )
                debt_desc = st.text_input("Description (optional)")
            submitted = st.form_submit_button("Add Debt")
            if submitted:
                if not debt_name.strip():
                    st.error("Debt name is required.")
                elif debt_original <= 0:
                    st.error("Original amount must be greater than zero.")
                elif debt_balance > debt_original:
                    st.error("Current balance cannot exceed the original amount.")
                else:
                    db.add_debt(
                        debt_name.strip(),
                        debt_original,
                        debt_balance,
                        debt_rate,
                        debt_min,
                        str(debt_due) if debt_due else None,
                        debt_cat,
                        debt_desc,
                    )
                    st.success(f"✅ Added debt: {debt_name}")
                    st.rerun()

    if debts:
        st.subheader("Your Debts")
        debt_columns = st.columns(2)
        for idx, d in enumerate(debts):
            paid = d["original_amount"] - d["current_balance"]
            pct = min(paid / d["original_amount"] * 100, 100) if d["original_amount"] > 0 else 0
            linked_fes = db.get_linked_fixed_expenses(d["id"])
            with debt_columns[idx % 2]:
                with st.container(border=True):
                    st.markdown(f"### {d['name']}")
                    tags = f"{d['category']} · ID {d['id']}"
                    if d["interest_rate"] > 0:
                        tags += f" · {d['interest_rate']:.2f}% APR"
                    if d["minimum_payment"] > 0:
                        tags += f" · Min payment: ${d['minimum_payment']:,.2f}"
                    if d.get("minimum_payment_date"):
                        tags += f" · Due: {d['minimum_payment_date']}"
                    st.caption(tags)
                    if d["description"]:
                        st.caption(d["description"])

                    metric_cols = st.columns(3)
                    with metric_cols[0]:
                        st.metric("Remaining", f"${d['current_balance']:,.2f}")
                    with metric_cols[1]:
                        st.metric("Original", f"${d['original_amount']:,.2f}")
                    with metric_cols[2]:
                        st.metric("Paid", f"${paid:,.2f}")

                    st.progress(pct / 100)
                    st.caption(f"{pct:.1f}% paid off")

                    payment_disabled = d["current_balance"] <= 0
                    with st.form(f"debt_payment_form_{d['id']}"):
                        payment_amt = st.number_input(
                            "Manual Payment ($)",
                            min_value=0.01,
                            max_value=float(d["current_balance"]) if d["current_balance"] > 0 else 0.01,
                            step=0.01,
                            format="%.2f",
                            value=min(float(d["minimum_payment"]), float(d["current_balance"]))
                            if d["minimum_payment"] > 0 and d["current_balance"] > 0
                            else 0.01,
                            key=f"pay_{d['id']}",
                        )
                        apply_manual_payment = st.form_submit_button(
                            "Apply Manual Payment",
                            width="stretch",
                            disabled=payment_disabled,
                        )
                        if apply_manual_payment:
                            if payment_amt > d["current_balance"]:
                                st.error("Payment exceeds remaining balance.")
                            else:
                                new_balance = max(d["current_balance"] - payment_amt, 0.0)
                                db.update_debt_balance(d["id"], new_balance)
                                st.success(f"Payment of ${payment_amt:,.2f} applied.")
                                st.rerun()

                    if payment_disabled:
                        st.caption("This debt is fully paid off.")

                    st.markdown("**Linked Fixed Expenses**")
                    if linked_fes:
                        for fe in linked_fes:
                            already_applied = db.is_debt_payment_applied(
                                d["id"], fe["id"], sel_year, sel_month
                            )
                            info_col, action_col = st.columns([3, 1])
                            with info_col:
                                st.markdown(
                                    f"**{fe['name']}**  \n${fe['amount']:,.2f} · {fe['frequency'].title()}"
                                )
                                if fe.get("description"):
                                    st.caption(fe["description"])
                            with action_col:
                                if already_applied:
                                    st.caption(f"Applied for {MONTHS[sel_month]}")
                                else:
                                    if st.button(
                                        f"Apply {MONTHS[sel_month]}",
                                        key=f"auto_pay_{d['id']}_{fe['id']}",
                                        width="stretch",
                                        disabled=payment_disabled,
                                    ):
                                        if fe["amount"] > d["current_balance"]:
                                            st.error("Payment exceeds remaining balance.")
                                        else:
                                            db.apply_debt_payment(
                                                d["id"], fe["id"], sel_year, sel_month, fe["amount"]
                                            )
                                            st.success(
                                                f"Applied ${fe['amount']:,.2f} from '{fe['name']}' for {MONTHS[sel_month]} {sel_year}."
                                            )
                                            st.rerun()
                                if st.button(
                                    "Unlink",
                                    key=f"unlink_fe_{d['id']}_{fe['id']}",
                                    width="stretch",
                                ):
                                    db.unlink_fixed_expense_from_debt(int(fe["id"]))
                                    st.success(f"Unlinked '{fe['name']}' from {d['name']}.")
                                    st.rerun()
                    else:
                        st.caption("No fixed expenses linked to this debt.")

                    if st.button("Delete Debt", key=f"delete_debt_{d['id']}", width="stretch"):
                        db.delete_debt(int(d["id"]))
                        st.success(f"Deleted {d['name']}.")
                        st.rerun()

        # --- summary chart -------------------------------------------------
        if len(debts) > 1:
            bar_data = [
                {"Debt": d["name"], "Remaining ($)": d["current_balance"]}
                for d in debts
            ]
            fig_debt = px.bar(
                bar_data,
                x="Debt",
                y="Remaining ($)",
                color="Debt",
                title="Remaining Balance by Debt",
            )
            fig_debt.update_layout(showlegend=False, height=300, margin=dict(t=40, b=0))
            st.plotly_chart(fig_debt, width="stretch")
    else:
        st.info("No debts recorded yet.")


# ===========================================================================
# PAGE: FINANCIAL GOALS
# ===========================================================================
elif page == "🎯 Financial Goals":
    st.title("🎯 Financial Goals")

    with st.expander("➕ Add New Goal", expanded=True):
        with st.form("goal_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                goal_name = st.text_input("Goal Name (e.g. Emergency Fund)")
                goal_target = st.number_input("Target Amount ($)", min_value=1.0, step=1.0, format="%.2f")
                goal_current = st.number_input("Current Saved ($)", min_value=0.0, step=1.0, format="%.2f")
            with c2:
                goal_date = st.date_input("Target Date (optional)", value=None)
                goal_desc = st.text_area("Description (optional)", height=95)
            submitted = st.form_submit_button("Add Goal")
            if submitted:
                if not goal_name.strip():
                    st.error("Goal name is required.")
                elif goal_target <= 0:
                    st.error("Target amount must be greater than zero.")
                else:
                    db.add_financial_goal(
                        goal_name.strip(),
                        goal_target,
                        goal_current,
                        str(goal_date) if goal_date else None,
                        goal_desc,
                    )
                    st.success(f"✅ Goal '{goal_name}' added.")
                    st.rerun()

    goals = db.get_financial_goals()
    if goals:
        st.subheader("Your Goals")
        for g in goals:
            pct = min(g["current_amount"] / g["target_amount"] * 100, 100)
            remaining = max(g["target_amount"] - g["current_amount"], 0)
            with st.container():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"### {g['name']} (ID: {g['id']})")
                    if g["description"]:
                        st.caption(g["description"])
                    if g["target_date"]:
                        st.caption(f"🗓 Target date: {g['target_date']}")
                    st.progress(pct / 100)
                    st.markdown(
                        f"**${g['current_amount']:,.2f}** saved of **${g['target_amount']:,.2f}** "
                        f"— {pct:.1f}% complete — **${remaining:,.2f}** remaining"
                    )
                with col2:
                    st.markdown("**Update Progress**")
                    new_val = st.number_input(
                        "New saved amount ($)",
                        min_value=0.0,
                        value=float(g["current_amount"]),
                        step=1.0,
                        key=f"goal_upd_{g['id']}",
                    )
                    if st.button("💾 Save", key=f"btn_upd_{g['id']}"):
                        db.update_goal_progress(g["id"], new_val)
                        st.rerun()
                st.markdown("---")

        del_id = st.number_input("Delete goal by ID", min_value=1, step=1, key="del_goal")
        if st.button("🗑 Delete Goal"):
            db.delete_financial_goal(int(del_id))
            st.success("Goal deleted.")
            st.rerun()
    else:
        st.info("No financial goals set yet.")


# ===========================================================================
# PAGE: REPORTS
# ===========================================================================
elif page == "📈 Reports":
    st.title("📈 Reports")

    report_type = st.radio("Report Type", ["Monthly Summary", "Yearly Summary"], horizontal=True)

    if report_type == "Monthly Summary":
        st.subheader(f"Monthly Summary — {MONTHS[sel_month]} {sel_year}")

        income_rows = db.get_income(year=sel_year, month=sel_month)
        var_rows = db.get_variable_expenses(year=sel_year, month=sel_month)
        fixed_cost = db.get_monthly_fixed_cost(sel_year, sel_month)

        total_income = sum(r["amount"] for r in income_rows)
        total_variable = sum(r["amount"] for r in var_rows)
        total_expenses = fixed_cost + total_variable
        net = total_income - total_expenses

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Income", f"${total_income:,.2f}")
        with c2:
            st.metric("Fixed Expenses", f"${fixed_cost:,.2f}")
        with c3:
            st.metric("Variable Expenses", f"${total_variable:,.2f}")
        with c4:
            st.metric("Net", f"${net:,.2f}", delta=f"${net:+,.2f}", delta_color="normal" if net >= 0 else "inverse")

        # income breakdown
        if income_rows:
            st.subheader("Income by Category")
            df_inc = pd.DataFrame(income_rows)
            inc_cat = df_inc.groupby("category")["amount"].sum().reset_index()
            fig_inc = px.pie(inc_cat, names="category", values="amount", title="Income Sources")
            fig_inc.update_layout(height=300, margin=dict(t=30, b=0))
            st.plotly_chart(fig_inc, width="stretch")

        # variable breakdown
        if var_rows:
            st.subheader("Variable Expenses by Category")
            df_var = pd.DataFrame(var_rows)
            var_cat = df_var.groupby("category")["amount"].sum().reset_index()
            fig_var = px.bar(
                var_cat,
                x="category",
                y="amount",
                color="category",
                labels={"amount": "Amount ($)", "category": "Category"},
            )
            fig_var.update_layout(showlegend=False, height=300, margin=dict(t=0))
            st.plotly_chart(fig_var, width="stretch")

        # table summary
        st.subheader("Budget Summary Table")
        summary_data = {
            "Category": ["Total Income", "Fixed Expenses", "Variable Expenses", "Net Balance"],
            "Amount ($)": [
                f"{total_income:,.2f}",
                f"{fixed_cost:,.2f}",
                f"{total_variable:,.2f}",
                f"{net:,.2f}",
            ],
        }
        st.table(pd.DataFrame(summary_data))

        # --- surplus allocation suggestions (only when net positive) --------
        if net > 0:
            st.markdown("---")
            st.subheader("💡 Surplus Allocation Suggestions")
            st.caption(
                f"You have a surplus of **${net:,.2f}** this month. "
                "Adjust the sliders to see how different splits would look."
            )

            col_s, col_d, col_g = st.columns(3)
            with col_s:
                pct_savings = st.slider("Savings %", 0, 100, 50, 5, key="alloc_savings")
            with col_d:
                max_debt = 100 - pct_savings
                pct_debt = st.slider("Debt Paydown %", 0, max_debt, min(30, max_debt), 5, key="alloc_debt")
            with col_g:
                max_goals = 100 - pct_savings - pct_debt
                pct_goals = st.slider("Financial Goals %", 0, max_goals, min(20, max_goals), 5, key="alloc_goals")

            pct_unallocated = 100 - pct_savings - pct_debt - pct_goals

            amt_savings = net * pct_savings / 100
            amt_debt    = net * pct_debt / 100
            amt_goals   = net * pct_goals / 100
            amt_unallocated = net * pct_unallocated / 100

            a1, a2, a3, a4 = st.columns(4)
            with a1:
                st.metric("💵 Into Savings", f"${amt_savings:,.2f}", f"{pct_savings}%")
            with a2:
                st.metric("💳 Debt Paydown", f"${amt_debt:,.2f}", f"{pct_debt}%")
            with a3:
                st.metric("🎯 Financial Goals", f"${amt_goals:,.2f}", f"{pct_goals}%")
            with a4:
                st.metric("➕ Unallocated Net Positive", f"${amt_unallocated:,.2f}", f"{pct_unallocated}%")

            # context: how far does each bucket go?
            hints = []
            report_debts_hint = db.get_debts()
            total_debt_hint = sum(d["current_balance"] for d in report_debts_hint)
            if amt_debt > 0 and total_debt_hint > 0:
                months_to_clear = total_debt_hint / amt_debt
                hints.append(f"At this rate you'd clear all debt in roughly **{months_to_clear:.1f} months**.")

            goals_hint = db.get_financial_goals()
            total_goals_remaining = sum(
                max(g["target_amount"] - g["current_amount"], 0) for g in goals_hint
            )
            if amt_goals > 0 and total_goals_remaining > 0:
                months_to_goals = total_goals_remaining / amt_goals
                hints.append(f"Your financial goals would be fully funded in roughly **{months_to_goals:.1f} months**.")

            savings_balances_hint = db.get_all_savings_balances()
            total_savings_hint = sum(savings_balances_hint.values())
            if amt_savings > 0:
                hints.append(f"Your savings balance would grow to **${total_savings_hint + amt_savings:,.2f}** after this month.")

            if hints:
                for hint in hints:
                    st.info(hint)

            # donut chart of the split
            if pct_savings + pct_debt + pct_goals + pct_unallocated > 0:
                fig_alloc = px.pie(
                    names=["Savings", "Debt Paydown", "Financial Goals", "Unallocated"],
                    values=[amt_savings, amt_debt, amt_goals, amt_unallocated],
                    hole=0.5,
                    color_discrete_sequence=["#00CC96", "#EF553B", "#636EFA", "#A3A3A3"],
                )
                fig_alloc.update_layout(height=280, margin=dict(t=10, b=0))
                st.plotly_chart(fig_alloc, width="stretch")

        # --- debt overview (informational only, not included in net) --------
        report_debts = db.get_debts()
        if report_debts:
            st.markdown("---")
            st.subheader("💳 Debt Overview")
            st.caption("Debt balances are shown for reference and are not included in the net calculation.")
            total_debt_report = sum(d["current_balance"] for d in report_debts)
            total_orig_report = sum(d["original_amount"] for d in report_debts)
            rd1, rd2, rd3 = st.columns(3)
            with rd1:
                st.metric("Total Remaining Debt", f"${total_debt_report:,.2f}")
            with rd2:
                st.metric("Original Debt", f"${total_orig_report:,.2f}")
            with rd3:
                st.metric("Total Paid Off", f"${total_orig_report - total_debt_report:,.2f}")
            df_debts_report = pd.DataFrame(report_debts)
            df_debt_show = df_debts_report[
                ["name", "category", "original_amount", "current_balance", "interest_rate", "minimum_payment", "minimum_payment_date"]
            ].copy()
            df_debt_show.columns = ["Name", "Category", "Original ($)", "Balance ($)", "APR (%)", "Min Payment ($)", "Due Date"]
            df_debt_show["Original ($)"] = df_debt_show["Original ($)"].map(lambda x: f"{x:,.2f}")
            df_debt_show["Balance ($)"] = df_debt_show["Balance ($)"].map(lambda x: f"{x:,.2f}")
            df_debt_show["APR (%)"] = df_debt_show["APR (%)"].map(lambda x: f"{x:.2f}")
            df_debt_show["Min Payment ($)"] = df_debt_show["Min Payment ($)"].map(lambda x: f"{x:,.2f}")
            df_debt_show["Due Date"] = df_debt_show["Due Date"].fillna("—")
            st.dataframe(df_debt_show, width="stretch", hide_index=True)
            if len(report_debts) > 1:
                fig_debt_report = px.bar(
                    [{"Debt": d["name"], "Balance ($)": d["current_balance"]} for d in report_debts],
                    x="Debt",
                    y="Balance ($)",
                    color="Debt",
                    title="Remaining Balance by Debt",
                )
                fig_debt_report.update_layout(showlegend=False, height=280, margin=dict(t=40, b=0))
                st.plotly_chart(fig_debt_report, width="stretch")

    else:
        st.subheader(f"Yearly Summary — {sel_year}")

        months_data = []
        for m in range(1, 13):
            inc = db.get_income(year=sel_year, month=m)
            var = db.get_variable_expenses(year=sel_year, month=m)
            fixed = db.get_monthly_fixed_cost(sel_year, m)
            total_inc = sum(r["amount"] for r in inc)
            total_var = sum(r["amount"] for r in var)
            total_exp = fixed + total_var
            months_data.append(
                {
                    "Month": calendar.month_abbr[m],
                    "Income": total_inc,
                    "Fixed": fixed,
                    "Variable": total_var,
                    "Total Expenses": total_exp,
                    "Net": total_inc - total_exp,
                }
            )

        df_yr = pd.DataFrame(months_data)

        # KPIs
        yr_income = df_yr["Income"].sum()
        yr_fixed = df_yr["Fixed"].sum()
        yr_variable = df_yr["Variable"].sum()
        yr_net = df_yr["Net"].sum()

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Yearly Income", f"${yr_income:,.2f}")
        with c2:
            st.metric("Fixed Expenses", f"${yr_fixed:,.2f}")
        with c3:
            st.metric("Variable Expenses", f"${yr_variable:,.2f}")
        with c4:
            st.metric("Net Balance", f"${yr_net:,.2f}", delta=f"${yr_net:+,.2f}", delta_color="normal" if yr_net >= 0 else "inverse")

        # monthly trend line
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Scatter(x=df_yr["Month"], y=df_yr["Income"], name="Income", mode="lines+markers", line=dict(color="#00CC96")))
        fig_trend.add_trace(go.Scatter(x=df_yr["Month"], y=df_yr["Total Expenses"], name="Total Expenses", mode="lines+markers", line=dict(color="#EF553B")))
        fig_trend.add_trace(go.Scatter(x=df_yr["Month"], y=df_yr["Net"], name="Net", mode="lines+markers", line=dict(color="#636EFA", dash="dot")))
        fig_trend.update_layout(title="Monthly Income vs Expenses", yaxis_title="Amount ($)", height=400)
        st.plotly_chart(fig_trend, width="stretch")

        # monthly breakdown bar
        fig_bar = go.Figure(data=[
            go.Bar(name="Fixed", x=df_yr["Month"], y=df_yr["Fixed"], marker_color="#EF553B"),
            go.Bar(name="Variable", x=df_yr["Month"], y=df_yr["Variable"], marker_color="#636EFA"),
        ])
        fig_bar.update_layout(barmode="stack", title="Monthly Expense Breakdown", yaxis_title="Amount ($)", height=350)
        st.plotly_chart(fig_bar, width="stretch")

        # data table
        st.subheader("Monthly Details")
        df_display = df_yr.copy()
        for col in ["Income", "Fixed", "Variable", "Total Expenses", "Net"]:
            df_display[col] = df_display[col].map(lambda x: f"${x:,.2f}")
        st.dataframe(df_display, width="stretch", hide_index=True)

        # --- debt overview (informational only, not included in net) --------
        report_debts_yr = db.get_debts()
        if report_debts_yr:
            st.markdown("---")
            st.subheader("💳 Debt Overview")
            st.caption("Debt balances are shown for reference and are not included in the net calculation.")
            total_debt_yr = sum(d["current_balance"] for d in report_debts_yr)
            total_orig_yr = sum(d["original_amount"] for d in report_debts_yr)
            yd1, yd2, yd3 = st.columns(3)
            with yd1:
                st.metric("Total Remaining Debt", f"${total_debt_yr:,.2f}")
            with yd2:
                st.metric("Original Debt", f"${total_orig_yr:,.2f}")
            with yd3:
                st.metric("Total Paid Off", f"${total_orig_yr - total_debt_yr:,.2f}")
            df_debts_yr = pd.DataFrame(report_debts_yr)
            df_debt_yr_show = df_debts_yr[
                ["name", "category", "original_amount", "current_balance", "interest_rate", "minimum_payment", "minimum_payment_date"]
            ].copy()
            df_debt_yr_show.columns = ["Name", "Category", "Original ($)", "Balance ($)", "APR (%)", "Min Payment ($)", "Due Date"]
            df_debt_yr_show["Original ($)"] = df_debt_yr_show["Original ($)"].map(lambda x: f"{x:,.2f}")
            df_debt_yr_show["Balance ($)"] = df_debt_yr_show["Balance ($)"].map(lambda x: f"{x:,.2f}")
            df_debt_yr_show["APR (%)"] = df_debt_yr_show["APR (%)"].map(lambda x: f"{x:.2f}")
            df_debt_yr_show["Min Payment ($)"] = df_debt_yr_show["Min Payment ($)"].map(lambda x: f"{x:,.2f}")
            df_debt_yr_show["Due Date"] = df_debt_yr_show["Due Date"].fillna("—")
            st.dataframe(df_debt_yr_show, width="stretch", hide_index=True)
            if len(report_debts_yr) > 1:
                fig_debt_yr = px.bar(
                    [{"Debt": d["name"], "Balance ($)": d["current_balance"]} for d in report_debts_yr],
                    x="Debt",
                    y="Balance ($)",
                    color="Debt",
                    title="Remaining Balance by Debt",
                )
                fig_debt_yr.update_layout(showlegend=False, height=280, margin=dict(t=40, b=0))
                st.plotly_chart(fig_debt_yr, width="stretch")
