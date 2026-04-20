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
    if st.button("🚪 Log out", use_container_width=True):
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
            st.plotly_chart(fig, use_container_width=True)
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
        st.plotly_chart(bar_fig, use_container_width=True)

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
        st.plotly_chart(cat_fig, use_container_width=True)

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


# ===========================================================================
# PAGE: INCOME
# ===========================================================================
elif page == "💰 Income":
    st.title("💰 Income")

    with st.expander("➕ Add Income Entry", expanded=True):
        with st.form("income_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                inc_date = st.date_input("Date", value=today)
                inc_amount = st.number_input("Amount ($)", min_value=0.01, step=0.01, format="%.2f")
            with c2:
                inc_cat = st.selectbox("Category", INCOME_CATEGORIES)
                inc_desc = st.text_input("Description (optional)")
            submitted = st.form_submit_button("Add Income")
            if submitted:
                if inc_amount <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    db.add_income(
                        str(inc_date), inc_amount, inc_cat, inc_desc
                    )
                    st.success(f"✅ Added ${inc_amount:,.2f} income on {inc_date}.")
                    st.rerun()

    st.subheader(f"Income — {MONTHS[sel_month]} {sel_year}")
    rows = db.get_income(year=sel_year, month=sel_month)
    if rows:
        df = _to_df(rows)
        df_show = df[["date", "amount", "category", "description"]].copy()
        df_show.columns = ["Date", "Amount ($)", "Category", "Description"]
        df_show["Amount ($)"] = df_show["Amount ($)"].map(lambda x: f"{x:,.2f}")
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        total = sum(r["amount"] for r in rows)
        st.markdown(f"**Total: ${total:,.2f}**")

        del_id = st.number_input(
            "Delete entry by ID", min_value=1, step=1, key="del_income"
        )
        if st.button("🗑 Delete Income Entry"):
            db.delete_income(int(del_id))
            st.success("Entry deleted.")
            st.rerun()
    else:
        st.info("No income entries for this period.")


# ===========================================================================
# PAGE: FIXED EXPENSES
# ===========================================================================
elif page == "📌 Fixed Expenses":
    st.title("📌 Fixed Expenses")
    st.caption(
        "Fixed expenses recur automatically each month (or year). "
        "They are included in budget calculations as long as they are active."
    )

    with st.expander("➕ Add Fixed Expense", expanded=True):
        with st.form("fixed_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                fix_name = st.text_input("Name (e.g. Rent, Netflix)")
                fix_amount = st.number_input("Amount ($)", min_value=0.01, step=0.01, format="%.2f")
                fix_freq = st.selectbox("Frequency", ["monthly", "yearly"])
            with c2:
                fix_cat = st.selectbox("Category", FIXED_EXPENSE_CATEGORIES)
                fix_start = st.date_input("Start Date", value=today.replace(day=1))
                fix_end = st.date_input(
                    "End Date (optional — leave as today if ongoing)",
                    value=None,
                    help="Leave blank / clear to indicate this expense is ongoing.",
                )
                fix_desc = st.text_input("Description (optional)")
            submitted = st.form_submit_button("Add Fixed Expense")
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
                        fix_cat,
                        fix_freq,
                        str(fix_start),
                        end_str,
                        fix_desc,
                    )
                    st.success(f"✅ Added fixed expense: {fix_name}")
                    st.rerun()

    st.subheader("All Fixed Expenses")
    show_active = st.checkbox("Show active only", value=True)
    rows = db.get_fixed_expenses(active_only=show_active)
    if rows:
        df = _to_df(rows)
        df_show = df[["id", "name", "amount", "frequency", "category", "start_date", "end_date", "description"]].copy()
        df_show.columns = ["ID", "Name", "Amount ($)", "Frequency", "Category", "Start", "End", "Description"]
        df_show["Amount ($)"] = df_show["Amount ($)"].map(lambda x: f"{x:,.2f}")
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        monthly_total = db.get_monthly_fixed_cost(sel_year, sel_month)
        st.markdown(f"**Monthly cost for {MONTHS[sel_month]} {sel_year}: ${monthly_total:,.2f}**")

        st.markdown("---")
        col_a, col_b = st.columns(2)
        with col_a:
            end_id = st.number_input("Set end date for ID", min_value=1, step=1)
            end_date_val = st.date_input("End Date", value=today)
            if st.button("✏️ Set End Date"):
                db.update_fixed_expense_end_date(int(end_id), str(end_date_val))
                st.success("End date updated.")
                st.rerun()
        with col_b:
            del_id = st.number_input("Delete fixed expense by ID", min_value=1, step=1, key="del_fixed")
            if st.button("🗑 Delete Fixed Expense"):
                db.delete_fixed_expense(int(del_id))
                st.success("Entry deleted.")
                st.rerun()
    else:
        st.info("No fixed expenses found.")


# ===========================================================================
# PAGE: VARIABLE EXPENSES
# ===========================================================================
elif page == "🛒 Variable Expenses":
    st.title("🛒 Variable Expenses")

    with st.expander("➕ Add Variable Expense", expanded=True):
        with st.form("var_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                var_date = st.date_input("Date", value=today)
                var_amount = st.number_input("Amount ($)", min_value=0.01, step=0.01, format="%.2f")
            with c2:
                var_cat = st.selectbox("Category", VARIABLE_EXPENSE_CATEGORIES)
                var_desc = st.text_input("Description (optional)")
            submitted = st.form_submit_button("Add Expense")
            if submitted:
                if var_amount <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    db.add_variable_expense(str(var_date), var_amount, var_cat, var_desc)
                    st.success(f"✅ Added ${var_amount:,.2f} expense on {var_date}.")
                    st.rerun()

    st.subheader(f"Variable Expenses — {MONTHS[sel_month]} {sel_year}")
    rows = db.get_variable_expenses(year=sel_year, month=sel_month)
    if rows:
        df = _to_df(rows)
        df_show = df[["id", "date", "amount", "category", "description"]].copy()
        df_show.columns = ["ID", "Date", "Amount ($)", "Category", "Description"]
        df_show["Amount ($)"] = df_show["Amount ($)"].map(lambda x: f"{x:,.2f}")
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        total = sum(r["amount"] for r in rows)
        st.markdown(f"**Total: ${total:,.2f}**")

        # category breakdown
        df_cat = df.groupby("category")["amount"].sum().reset_index()
        fig = px.bar(
            df_cat,
            x="category",
            y="amount",
            color="category",
            labels={"amount": "Amount ($)", "category": "Category"},
            title="Spending by Category",
        )
        fig.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig, use_container_width=True)

        del_id = st.number_input("Delete entry by ID", min_value=1, step=1, key="del_var")
        if st.button("🗑 Delete Variable Expense"):
            db.delete_variable_expense(int(del_id))
            st.success("Entry deleted.")
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

    # --- add transaction form ----------------------------------------------
    with st.expander("➕ Add Transaction", expanded=True):
        with st.form("savings_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                sav_account = st.selectbox("Account", SAVINGS_ACCOUNTS)
                sav_type = st.selectbox("Type", ["deposit", "withdrawal"])
                sav_amount = st.number_input(
                    "Amount ($)", min_value=0.01, step=0.01, format="%.2f"
                )
            with c2:
                sav_date = st.date_input("Date", value=today)
                sav_desc = st.text_input("Description (optional)")
            submitted = st.form_submit_button("Add Transaction")
            if submitted:
                if sav_amount <= 0:
                    st.error("Amount must be greater than zero.")
                else:
                    # Guard against withdrawing more than the current balance
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

    # --- per-account transaction history -----------------------------------
    st.subheader("Transaction History")
    view_acct = st.selectbox("View account", ["All"] + SAVINGS_ACCOUNTS, key="sav_view")

    rows = (
        db.get_savings_transactions()
        if view_acct == "All"
        else db.get_savings_transactions(account=view_acct)
    )

    if rows:
        df_sav = _to_df(rows)
        df_show = df_sav[["id", "account", "date", "type", "amount", "description"]].copy()
        df_show.columns = ["ID", "Account", "Date", "Type", "Amount ($)", "Description"]
        df_show["Amount ($)"] = df_show["Amount ($)"].map(lambda x: f"{x:,.2f}")
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        # running balance chart per account
        if view_acct != "All":
            df_chart = df_sav.sort_values("date").copy()
            df_chart["signed"] = df_chart.apply(
                lambda r: r["amount"] if r["type"] == "deposit" else -r["amount"], axis=1
            )
            df_chart["balance"] = df_chart["signed"].cumsum()
            fig_bal = px.line(
                df_chart,
                x="date",
                y="balance",
                title=f"{view_acct} — Running Balance",
                labels={"balance": "Balance ($)", "date": "Date"},
                markers=True,
            )
            fig_bal.update_layout(height=320, margin=dict(t=40, b=0))
            st.plotly_chart(fig_bal, use_container_width=True)
        else:
            # stacked bar showing balance per account
            bar_data = [{"Account": a, "Balance ($)": balances[a]} for a in SAVINGS_ACCOUNTS]
            fig_bar = px.bar(
                bar_data,
                x="Account",
                y="Balance ($)",
                color="Account",
                title="Current Balance by Account",
            )
            fig_bar.update_layout(showlegend=False, height=300, margin=dict(t=40, b=0))
            st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")
        del_id = st.number_input(
            "Delete transaction by ID", min_value=1, step=1, key="del_sav"
        )
        if st.button("🗑 Delete Transaction"):
            db.delete_savings_transaction(int(del_id))
            st.success("Transaction deleted.")
            st.rerun()
    else:
        st.info("No savings transactions recorded yet.")


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
            st.plotly_chart(fig_inc, use_container_width=True)

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
            st.plotly_chart(fig_var, use_container_width=True)

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
        st.plotly_chart(fig_trend, use_container_width=True)

        # monthly breakdown bar
        fig_bar = go.Figure(data=[
            go.Bar(name="Fixed", x=df_yr["Month"], y=df_yr["Fixed"], marker_color="#EF553B"),
            go.Bar(name="Variable", x=df_yr["Month"], y=df_yr["Variable"], marker_color="#636EFA"),
        ])
        fig_bar.update_layout(barmode="stack", title="Monthly Expense Breakdown", yaxis_title="Amount ($)", height=350)
        st.plotly_chart(fig_bar, use_container_width=True)

        # data table
        st.subheader("Monthly Details")
        df_display = df_yr.copy()
        for col in ["Income", "Fixed", "Variable", "Total Expenses", "Net"]:
            df_display[col] = df_display[col].map(lambda x: f"${x:,.2f}")
        st.dataframe(df_display, use_container_width=True, hide_index=True)
