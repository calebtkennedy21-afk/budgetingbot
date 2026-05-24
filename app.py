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
from contextlib import contextmanager
import html
import hashlib
import hmac
import os
import re
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

import database as db
import ai_insights as ai

# ---------------------------------------------------------------------------
# App-wide config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="💸 Budgeting Bot",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)

THEME_PRESETS = {
    "Midnight Ledger": {
        "bg": "#0d1117",
        "surface": "#161b22",
        "surface_strong": "#1f2630",
        "ink": "#e6edf3",
        "muted": "#9fb0c3",
        "accent": "#1f8f80",
        "accent_2": "#2aa79a",
        "accent_soft": "#18343b",
        "warn": "#f08a6b",
        "good": "#3fb98a",
        "border": "#2d3847",
        "shadow": "0 12px 32px rgba(0, 0, 0, 0.45)",
        "plot_bg": "#111821",
        "colorway": ["#3fb98a", "#f08a6b", "#68a5ff", "#d6a756", "#9aa6b2", "#7ad1c6"],
    },
    "Warm Editorial": {
        "bg": "#f6f4ef",
        "surface": "#fcfbf8",
        "surface_strong": "#ffffff",
        "ink": "#1f2833",
        "muted": "#5f6b7a",
        "accent": "#0f766e",
        "accent_2": "#13867d",
        "accent_soft": "#d4f2ef",
        "warn": "#e07a5f",
        "good": "#1f8f56",
        "border": "#d7d3c7",
        "shadow": "0 10px 30px rgba(31, 40, 51, 0.08)",
        "plot_bg": "#fffdfa",
        "colorway": ["#0f766e", "#e07a5f", "#2f5d8c", "#d9a441", "#64748b", "#7f5539"],
    },
    "Clean Data Studio": {
        "bg": "#edf2f7",
        "surface": "#f8fbff",
        "surface_strong": "#ffffff",
        "ink": "#17212b",
        "muted": "#4b5b6b",
        "accent": "#0f766e",
        "accent_2": "#1f9a8f",
        "accent_soft": "#d7f3ef",
        "warn": "#d65d48",
        "good": "#15803d",
        "border": "#c8d3e1",
        "shadow": "0 8px 24px rgba(23, 33, 43, 0.08)",
        "plot_bg": "#f9fbff",
        "colorway": ["#0f766e", "#2f5d8c", "#d65d48", "#16a34a", "#0ea5e9", "#64748b"],
    },
}


def _configure_visual_theme(theme_name: str) -> None:
    """Apply app-wide CSS tokens and a shared Plotly chart template."""
    theme = THEME_PRESETS.get(theme_name, THEME_PRESETS["Midnight Ledger"])
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:wght@500;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

:root {
    --bb-bg: #f6f4ef;
    --bb-surface: #fcfbf8;
    --bb-surface-strong: #ffffff;
    --bb-ink: #1f2833;
    --bb-muted: #5f6b7a;
    --bb-accent: #0f766e;
    --bb-accent-soft: #d4f2ef;
    --bb-warn: #e07a5f;
    --bb-good: #1f8f56;
    --bb-border: #d7d3c7;
    --bb-shadow: 0 10px 30px rgba(31, 40, 51, 0.08);
}

html, body, [class*="stApp"] {
    font-family: 'Space Grotesk', sans-serif;
    color: var(--bb-ink);
}

.stApp {
    background:
    radial-gradient(1000px 400px at 10% 5%, rgba(46, 118, 109, 0.24), transparent 65%),
    radial-gradient(900px 350px at 95% 2%, rgba(126, 72, 56, 0.22), transparent 70%),
        var(--bb-bg);
}

h1, h2, h3 {
    font-family: 'Fraunces', serif;
    letter-spacing: 0.2px;
    color: var(--bb-ink);
}

[data-testid="stAppViewContainer"] > .main {
    max-width: 1280px;
}

hr {
    border: none;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(159, 176, 195, 0.45), transparent);
    margin: 1.2rem 0;
}

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #121922 0%, #0f141d 100%);
    border-right: 1px solid var(--bb-border);
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] label {
    color: var(--bb-ink) !important;
}

[data-testid="stMetric"] {
    background: var(--bb-surface-strong);
    border: 1px solid var(--bb-border);
    border-radius: 14px;
    box-shadow: var(--bb-shadow);
    padding: 0.85rem 0.95rem;
}

[data-testid="stMetricLabel"] p,
[data-testid="stMetricValue"] div,
[data-testid="stMetricDelta"] div {
    color: var(--bb-ink) !important;
    opacity: 1 !important;
}

[data-testid="stCaptionContainer"] p,
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] strong,
[data-testid="stMarkdownContainer"] span {
    color: var(--bb-ink);
}

[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3 {
    color: var(--bb-ink) !important;
}

[data-testid="stForm"],
[data-testid="stExpander"],
[data-testid="stDataFrame"],
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 14px;
}

[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid var(--bb-border);
    background: var(--bb-surface-strong);
    box-shadow: var(--bb-shadow);
}

[data-testid="stExpander"] {
    border: 1px solid var(--bb-border);
    background: var(--bb-surface-strong);
}

[data-testid="stExpander"] summary {
    font-weight: 600;
    color: var(--bb-ink);
}

[data-baseweb="tab-list"] {
    gap: 0.35rem;
}

[data-baseweb="tab"] {
    border-radius: 10px 10px 0 0;
    background: rgba(63, 185, 138, 0.13);
    border: 1px solid rgba(63, 185, 138, 0.26);
    font-weight: 600;
    color: var(--bb-ink) !important;
}

[data-baseweb="tab-highlight"] {
    background-color: var(--bb-accent);
}

[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
[data-baseweb="textarea"] > div,
[data-baseweb="base-input"] > div {
    background: var(--bb-surface);
    border-color: var(--bb-border);
}

[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea,
[data-baseweb="select"] div,
[data-baseweb="base-input"] input {
    color: var(--bb-ink) !important;
}

[data-testid="stRadio"] label,
[data-testid="stCheckbox"] label {
    font-weight: 500;
    color: var(--bb-ink);
}

[data-testid="stButton"] button,
[data-testid="baseButton-secondary"] {
    border-radius: 12px;
    border: 1px solid var(--bb-accent);
    background: linear-gradient(160deg, var(--bb-accent-2) 0%, var(--bb-accent) 100%);
    color: #f4f8f7;
    font-weight: 600;
    transition: transform 0.16s ease, box-shadow 0.16s ease;
}

[data-testid="stButton"] button:hover,
[data-testid="baseButton-secondary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 16px rgba(15, 118, 110, 0.25);
}

.bb-kpi-tile {
    background: var(--bb-surface-strong);
    border: 1px solid var(--bb-border);
    border-radius: 14px;
    box-shadow: var(--bb-shadow);
    padding: 0.75rem 0.85rem;
    animation: bb-fade-up 0.35s ease both;
}

.bb-page-head {
    background: linear-gradient(120deg, rgba(42, 167, 154, 0.2), rgba(240, 138, 107, 0.14));
    border: 1px solid var(--bb-border);
    border-radius: 16px;
    box-shadow: var(--bb-shadow);
    padding: 1rem 1.15rem;
    margin-bottom: 0.95rem;
    animation: bb-fade-up 0.38s ease both;
}

.bb-page-title {
    margin: 0;
    line-height: 1.2;
}

.bb-page-subtitle {
    margin-top: 0.35rem;
    color: var(--bb-muted);
    font-weight: 500;
    font-size: 0.94rem;
}

.bb-inline-stat {
    text-align: right;
    color: var(--bb-ink);
    font-weight: 700;
    font-size: 0.95rem;
}

.bb-kpi-label {
    color: var(--bb-muted);
    font-size: 0.8rem;
    margin-bottom: 0.2rem;
}

.bb-kpi-value {
    color: var(--bb-ink);
    font-size: 1.1rem;
    font-weight: 700;
}

.bb-chip {
    display: inline-block;
    border-radius: 999px;
    padding: 0.15rem 0.6rem;
    font-size: 0.78rem;
    font-weight: 600;
    border: 1px solid transparent;
}

.bb-chip-good {
    color: #14532d;
    background: #d1fae5;
    border-color: #86efac;
}

.bb-chip-bad {
    color: #7f1d1d;
    background: #fee2e2;
    border-color: #fca5a5;
}

.bb-chip-accent {
    color: #134e4a;
    background: var(--bb-accent-soft);
    border-color: #8ddad2;
}

@keyframes bb-fade-up {
    from {
        opacity: 0;
        transform: translateY(8px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@media (max-width: 900px) {
    h1 {
        font-size: 1.7rem;
    }

    [data-testid="stMetric"] {
        padding: 0.7rem 0.75rem;
    }
}
</style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
<style>
:root {{
    --bb-bg: {theme['bg']};
    --bb-surface: {theme['surface']};
    --bb-surface-strong: {theme['surface_strong']};
    --bb-ink: {theme['ink']};
    --bb-muted: {theme['muted']};
    --bb-accent: {theme['accent']};
    --bb-accent-2: {theme['accent_2']};
    --bb-accent-soft: {theme['accent_soft']};
    --bb-warn: {theme['warn']};
    --bb-good: {theme['good']};
    --bb-border: {theme['border']};
    --bb-shadow: {theme['shadow']};
}}
</style>
        """,
        unsafe_allow_html=True,
    )

    pio.templates["budgetingbot"] = go.layout.Template(
        layout=go.Layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor=theme["plot_bg"],
            font={"family": "Space Grotesk, sans-serif", "color": theme["ink"], "size": 13},
            colorway=theme["colorway"],
            title={"font": {"family": "Fraunces, serif", "size": 19, "color": theme["ink"]}},
            xaxis={
                "gridcolor": "rgba(95, 107, 122, 0.15)",
                "linecolor": "rgba(95, 107, 122, 0.4)",
                "zerolinecolor": "rgba(95, 107, 122, 0.22)",
            },
            yaxis={
                "gridcolor": "rgba(95, 107, 122, 0.15)",
                "linecolor": "rgba(95, 107, 122, 0.4)",
                "zerolinecolor": "rgba(95, 107, 122, 0.22)",
            },
            legend={"bgcolor": "rgba(0,0,0,0)"},
        )
    )
    pio.templates.default = "budgetingbot"


def _status_chip(text: str, state: str = "accent") -> None:
    class_map = {
        "good": "bb-chip-good",
        "bad": "bb-chip-bad",
        "accent": "bb-chip-accent",
    }
    chip_class = class_map.get(state, "bb-chip-accent")
    st.markdown(f"<span class='bb-chip {chip_class}'>{text}</span>", unsafe_allow_html=True)


def _kpi_tile(label: str, value: str) -> None:
    st.markdown(
        f"<div class='bb-kpi-tile'><div class='bb-kpi-label'>{label}</div><div class='bb-kpi-value'>{value}</div></div>",
        unsafe_allow_html=True,
    )


def _page_header(title: str, subtitle: str = "") -> None:
    escaped_title = html.escape(title)
    subtitle_html = (
        f"<div class='bb-page-subtitle'>{html.escape(subtitle)}</div>" if subtitle else ""
    )
    st.markdown(
        f"<div class='bb-page-head'><h1 class='bb-page-title'>{escaped_title}</h1>{subtitle_html}</div>",
        unsafe_allow_html=True,
    )


def _inline_stat(value: str) -> None:
    st.markdown(f"<div class='bb-inline-stat'>{html.escape(value)}</div>", unsafe_allow_html=True)


def _notify(level: str, message: str) -> None:
    notify_map = {
        "success": st.success,
        "warning": st.warning,
        "info": st.info,
        "error": st.error,
    }
    renderer = notify_map.get(level, st.info)
    renderer(message)


@contextmanager
def _section_card(title: str = "", caption: str = ""):
    with st.container(border=True):
        if title:
            st.subheader(title)
        if caption:
            st.caption(caption)
        yield


if "visual_theme" not in st.session_state:
    st.session_state["visual_theme"] = "Midnight Ledger"

_configure_visual_theme(st.session_state["visual_theme"])


# ---------------------------------------------------------------------------
# Auth config
# ---------------------------------------------------------------------------
AUTH_USER_ENV = "BUDGETBOT_USERNAME"
AUTH_SALT_ENV = "BUDGETBOT_PASSWORD_SALT"
AUTH_HASH_ENV = "BUDGETBOT_PASSWORD_HASH"
AUTH_TIMEOUT_ENV = "BUDGETBOT_SESSION_TIMEOUT_MINUTES"
OPENAI_KEY_ENV = ai.OPENAI_API_KEY_ENV
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
            _notify("warning", 
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

    _page_header("🔒 Login Required", "Sign in to access your budgeting data.")

    username = _secret_or_env(AUTH_USER_ENV)
    password_salt = _secret_or_env(AUTH_SALT_ENV)
    password_hash = _secret_or_env(AUTH_HASH_ENV)

    if not username or not password_salt or not password_hash:
        _notify("warning", "Authentication is not configured yet.")
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
                    _notify("error", "Username is required.")
                elif len(setup_password) < 8:
                    _notify("error", "Password must be at least 8 characters.")
                elif setup_password != setup_password_confirm:
                    _notify("error", "Passwords do not match.")
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
        _notify("error", "Authentication settings are invalid. Salt/hash must be hex strings.")
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
                _notify("error", "Invalid username or password.")


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
    _notify("warning", "Your session expired. Please log in again.")

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
    selected_theme = st.selectbox(
        "Visual Theme",
        list(THEME_PRESETS.keys()),
        index=list(THEME_PRESETS.keys()).index(st.session_state["visual_theme"]),
        help="Switch between the warm editorial look and a cleaner data-studio style.",
    )
    if selected_theme != st.session_state["visual_theme"]:
        st.session_state["visual_theme"] = selected_theme
        st.rerun()

    if db_online:
        _status_chip("Database: Online", state="good")
    else:
        _status_chip("Database: Offline", state="bad")
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
            "🧭 Planning",
            "🤖 AI Insights",
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

    # --- OpenAI API key config -------------------------------------------
    st.subheader("🤖 AI Settings")
    openai_key = _secret_or_env(OPENAI_KEY_ENV, "")
    if openai_key:
        os.environ[OPENAI_KEY_ENV] = openai_key
        _status_chip("AI: Configured", state="good")
    else:
        with st.expander("Configure OpenAI Key"):
            new_key = st.text_input("OpenAI API Key", type="password", key="sidebar_openai_key")
            if st.button("Save Key", key="save_openai_key"):
                if new_key.strip().startswith("sk-"):
                    ok, detail = _upsert_local_secrets({OPENAI_KEY_ENV: new_key.strip()})
                    os.environ[OPENAI_KEY_ENV] = new_key.strip()
                    if ok:
                        _notify("success", "Key saved.")
                        st.rerun()
                    else:
                        _notify("error", f"Could not save: {detail}")
                else:
                    _notify("error", "Key must start with 'sk-'.")

    st.markdown("---")
    st.caption("Data stored in local SQLite database.")

if not db_online:
    _notify("error", "Database is offline. Please check your database connection and restart the app.")
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


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    total = (year * 12 + (month - 1)) + offset
    new_year = total // 12
    new_month = (total % 12) + 1
    return new_year, new_month


def _avg_variable_spend(year: int, month: int, lookback_months: int = 3, recurring_only: bool | None = None) -> float:
    amounts: list[float] = []
    for i in range(lookback_months):
        y, m = _shift_month(year, month, -i)
        rows = db.get_variable_expenses(year=y, month=m)
        if recurring_only is True:
            rows = [r for r in rows if bool(r.get("is_recurring"))]
        elif recurring_only is False:
            rows = [r for r in rows if not bool(r.get("is_recurring"))]
        amounts.append(sum(float(r["amount"]) for r in rows))
    if not amounts:
        return 0.0
    return sum(amounts) / len(amounts)


def _avg_income(year: int, month: int, lookback_months: int = 3) -> float:
    vals: list[float] = []
    for i in range(lookback_months):
        y, m = _shift_month(year, month, -i)
        rows = db.get_income(year=y, month=m)
        vals.append(sum(float(r["amount"]) for r in rows))
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def _cashflow_forecast(base_year: int, base_month: int, horizon_months: int = 3) -> list[dict]:
    debts = db.get_debts()
    debt_minimum_total = sum(float(d.get("minimum_payment", 0) or 0) for d in debts)
    out: list[dict] = []
    for i in range(horizon_months):
        y, m = _shift_month(base_year, base_month, i)
        income_rows = db.get_income(year=y, month=m)
        known_income = sum(float(r["amount"]) for r in income_rows)
        projected_income = known_income if known_income > 0 else _avg_income(base_year, base_month)

        fixed_cost = db.get_monthly_fixed_cost(y, m)
        projected_recurring = _avg_variable_spend(base_year, base_month, recurring_only=True)
        projected_discretionary = _avg_variable_spend(base_year, base_month, recurring_only=False)

        projected_outflow = fixed_cost + projected_recurring + projected_discretionary + debt_minimum_total
        projected_net = projected_income - projected_outflow
        safe_to_spend = max(projected_income - fixed_cost - projected_recurring - debt_minimum_total, 0.0)
        out.append(
            {
                "year": y,
                "month": m,
                "label": f"{calendar.month_abbr[m]} {y}",
                "projected_income": projected_income,
                "fixed_cost": fixed_cost,
                "recurring_variable": projected_recurring,
                "discretionary_variable": projected_discretionary,
                "debt_minimum": debt_minimum_total,
                "projected_net": projected_net,
                "safe_to_spend": safe_to_spend,
            }
        )
    return out


def _build_bill_calendar(year: int, month: int) -> list[dict]:
    today_local = date.today()
    last_day = calendar.monthrange(year, month)[1]
    items: list[dict] = []

    for fe in db.get_fixed_expenses(active_only=True):
        start_dt = date.fromisoformat(str(fe["start_date"]))
        end_dt = date.fromisoformat(str(fe["end_date"])) if fe.get("end_date") else None
        if start_dt > date(year, month, last_day):
            continue
        if end_dt and end_dt < date(year, month, 1):
            continue

        if fe["frequency"] == "monthly":
            due_day = min(start_dt.day, last_day)
            due_dt = date(year, month, due_day)
        else:
            if start_dt.month != month:
                continue
            due_day = min(start_dt.day, last_day)
            due_dt = date(year, month, due_day)

        if due_dt < date(year, month, 1) or due_dt > date(year, month, last_day):
            continue

        days = (due_dt - today_local).days
        if days < 0:
            status = "Overdue"
        elif days <= 7:
            status = "Due soon"
        else:
            status = "Upcoming"
        items.append(
            {
                "type": "Fixed Expense",
                "name": fe["name"],
                "due_date": str(due_dt),
                "amount": float(fe["amount"] if fe["frequency"] == "monthly" else fe["amount"] / 12),
                "status": status,
            }
        )

    for debt in db.get_debts():
        if not debt.get("minimum_payment_date") or float(debt.get("minimum_payment", 0) or 0) <= 0:
            continue
        try:
            due_seed = date.fromisoformat(str(debt["minimum_payment_date"]))
        except ValueError:
            continue
        due_day = min(due_seed.day, last_day)
        due_dt = date(year, month, due_day)
        days = (due_dt - today_local).days
        if days < 0:
            status = "Overdue"
        elif days <= 7:
            status = "Due soon"
        else:
            status = "Upcoming"
        items.append(
            {
                "type": "Debt Minimum",
                "name": debt["name"],
                "due_date": str(due_dt),
                "amount": float(debt["minimum_payment"]),
                "status": status,
            }
        )

    items.sort(key=lambda x: x["due_date"])
    return items


def _apply_import_rules(description: str, current_category: str, rules: list[dict]) -> tuple[str, bool]:
    desc = (description or "").lower()
    cat = (current_category or "").lower()
    for rule in rules:
        field = (rule.get("field") or "description").lower()
        pattern = (rule.get("pattern") or "").strip().lower()
        if not pattern:
            continue
        target = desc if field == "description" else cat
        if pattern in target:
            return str(rule.get("target_category") or current_category), bool(rule.get("recurring_flag"))
    return current_category, False


def _normalize_text(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _parse_statement_date(value) -> str | None:
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def _parse_statement_amount(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        amount = float(value)
        if amount == 0:
            return None
        return amount
    text = str(value).strip()
    if not text:
        return None

    text_upper = text.upper()
    force_negative = False
    if text_upper.endswith(" DR") or text_upper.endswith("DR"):
        force_negative = True
        text = re.sub(r"\s*DR$", "", text, flags=re.IGNORECASE).strip()
    elif text_upper.endswith(" CR") or text_upper.endswith("CR"):
        text = re.sub(r"\s*CR$", "", text, flags=re.IGNORECASE).strip()

    is_negative = False
    if text.startswith("(") and text.endswith(")"):
        is_negative = True
        text = text[1:-1]
    text = text.replace("$", "").replace(",", "").strip()
    try:
        amount = float(text)
    except ValueError:
        return None
    if (is_negative or force_negative) and amount > 0:
        amount = -amount
    if amount == 0:
        return None
    return amount


def _statement_file_to_dataframe(uploaded_file) -> tuple[pd.DataFrame, str, str]:
    """
    Parse supported statement files into a normalized dataframe.
    Returns (df, file_type, error_message).
    Normalized columns: date, amount, description, category
    """
    filename = (uploaded_file.name or "").lower()
    file_ext = filename.rsplit(".", 1)[-1] if "." in filename else ""

    if file_ext == "csv":
        try:
            df_csv = pd.read_csv(uploaded_file)
            return df_csv, "csv", ""
        except Exception as exc:
            return pd.DataFrame(), "csv", f"Could not read CSV: {exc}"

    if file_ext in {"ofx", "qfx"}:
        try:
            from io import BytesIO
            from ofxparse import OfxParser  # type: ignore[import-not-found]
        except Exception:
            return (
                pd.DataFrame(),
                file_ext,
                "OFX/QFX parser is unavailable. Install dependency: ofxparse.",
            )

        try:
            uploaded_file.seek(0)
            ofx = OfxParser.parse(BytesIO(uploaded_file.read()))
        except Exception as exc:
            return pd.DataFrame(), file_ext, f"Could not parse {file_ext.upper()} file: {exc}"

        normalized_rows: list[dict] = []
        accounts = []
        if getattr(ofx, "account", None) is not None:
            accounts.append(ofx.account)
        accounts.extend(getattr(ofx, "accounts", []) or [])
        if not accounts:
            accounts = [getattr(ofx, "account", None)]

        for acct in [a for a in accounts if a is not None]:
            for txn in getattr(acct, "statement", {}).transactions if getattr(acct, "statement", None) else []:
                txn_date = txn.date.date().isoformat() if getattr(txn, "date", None) else ""
                description = " ".join(
                    part for part in [
                        str(getattr(txn, "payee", "") or "").strip(),
                        str(getattr(txn, "memo", "") or "").strip(),
                        str(getattr(txn, "type", "") or "").strip(),
                    ]
                    if part
                )
                normalized_rows.append(
                    {
                        "date": txn_date,
                        "amount": float(getattr(txn, "amount", 0) or 0),
                        "description": description,
                        "category": "Other",
                    }
                )

        return pd.DataFrame(normalized_rows), file_ext, ""

    if file_ext == "pdf":
        try:
            from io import BytesIO
            import pdfplumber  # type: ignore[import-not-found]
        except Exception:
            return (
                pd.DataFrame(),
                file_ext,
                "PDF parser is unavailable. Install dependency: pdfplumber.",
            )

        def _extract_from_lines(lines: list[str]) -> list[dict]:
            out: list[dict] = []
            seen: set[tuple[str, float, str]] = set()
            date_pattern = re.compile(r"(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)")
            amt_pattern = re.compile(r"[-(]?\$?\d[\d,]*\.\d{2}\)?(?:\s*(?:DR|CR))?", re.IGNORECASE)

            for raw_line in lines:
                line = " ".join(str(raw_line or "").split())
                if not line:
                    continue
                if "balance" in line.lower() and "payment" not in line.lower():
                    continue

                date_match = date_pattern.search(line)
                if not date_match:
                    continue
                parsed_date = _parse_statement_date(date_match.group(1))
                if not parsed_date:
                    continue

                amount_matches = amt_pattern.findall(line)
                if not amount_matches:
                    continue
                parsed_amount = _parse_statement_amount(amount_matches[-1])
                if parsed_amount is None:
                    continue

                desc = line
                desc = desc.replace(date_match.group(1), " ", 1)
                desc = desc.replace(amount_matches[-1], " ", 1)
                desc = " ".join(desc.split()).strip("-: ")
                if not desc:
                    desc = "PDF statement transaction"

                key = (parsed_date, float(parsed_amount), _normalize_text(desc))
                if key in seen:
                    continue
                seen.add(key)

                out.append(
                    {
                        "date": parsed_date,
                        "amount": float(parsed_amount),
                        "description": desc,
                        "category": "Other",
                    }
                )
            return out

        try:
            uploaded_file.seek(0)
            raw_bytes = uploaded_file.read()
            all_lines: list[str] = []
            with pdfplumber.open(BytesIO(raw_bytes)) as pdf:
                for page in pdf.pages:
                    for table in page.extract_tables() or []:
                        for row in table:
                            if not row:
                                continue
                            row_line = " ".join(str(cell or "").strip() for cell in row if str(cell or "").strip())
                            if row_line:
                                all_lines.append(row_line)

                    page_text = page.extract_text() or ""
                    for tline in page_text.splitlines():
                        if tline.strip():
                            all_lines.append(tline.strip())

            rows = _extract_from_lines(all_lines)
            if not rows:
                return (
                    pd.DataFrame(),
                    file_ext,
                    "Could not detect transactions in PDF. Try CSV/OFX/QFX export for best results.",
                )
            return pd.DataFrame(rows), file_ext, ""
        except Exception as exc:
            return pd.DataFrame(), file_ext, f"Could not parse PDF file: {exc}"

    return pd.DataFrame(), file_ext or "unknown", "Unsupported file format. Use CSV, OFX, QFX, or PDF."


def _match_debt_target(description: str, debt_rows: list[dict]) -> dict | None:
    desc = _normalize_text(description)
    if not desc:
        return None
    for d in debt_rows:
        debt_name = _normalize_text(str(d.get("name", "")))
        if debt_name and debt_name in desc:
            return d
    debt_keywords = ["credit card", "cc payment", "loan payment", "mortgage payment", "student loan"]
    if any(kw in desc for kw in debt_keywords):
        return debt_rows[0] if debt_rows else None
    return None


def _route_statement_row(
    txn_date: str,
    signed_amount: float,
    description: str,
    mapped_category: str,
    mapped_recurring: bool,
    debt_rows: list[dict],
    savings_account: str,
    default_income_source: str,
) -> dict:
    desc = _normalize_text(description)
    amount_abs = abs(float(signed_amount))

    transfer_terms = ["transfer", "xfer", "internal transfer"]
    savings_terms = ["savings", "hysa", "high yield", "money market"]
    income_terms = ["payroll", "salary", "direct deposit", "refund", "interest", "dividend"]
    debt_terms = ["payment", "autopay", "credit card", "loan", "mortgage"]

    is_transfer = any(t in desc for t in transfer_terms)
    has_savings_term = any(t in desc for t in savings_terms)
    is_income_like = any(t in desc for t in income_terms)
    is_debt_like = any(t in desc for t in debt_terms)

    debt_target = _match_debt_target(description, debt_rows) if is_debt_like else None

    if signed_amount < 0:
        if is_transfer and has_savings_term:
            return {
                "route": "savings_transfer",
                "txn_date": txn_date,
                "amount": amount_abs,
                "description": description,
                "savings_account": savings_account,
                "savings_type": "deposit",
                "target": savings_account,
            }
        if debt_target is not None:
            return {
                "route": "debt_payment",
                "txn_date": txn_date,
                "amount": amount_abs,
                "description": description,
                "debt_id": int(debt_target["id"]),
                "target": str(debt_target["name"]),
            }
        return {
            "route": "variable_expense",
            "txn_date": txn_date,
            "amount": amount_abs,
            "description": description,
            "category": mapped_category if mapped_category in VARIABLE_EXPENSE_CATEGORIES else "Other",
            "is_recurring": bool(mapped_recurring),
            "target": mapped_category if mapped_category in VARIABLE_EXPENSE_CATEGORIES else "Other",
        }

    # Positive inflows
    if is_transfer and has_savings_term:
        return {
            "route": "savings_transfer",
            "txn_date": txn_date,
            "amount": amount_abs,
            "description": description,
            "savings_account": savings_account,
            "savings_type": "withdrawal",
            "target": savings_account,
        }
    if is_income_like or not is_debt_like:
        income_category = mapped_category if mapped_category in INCOME_CATEGORIES else "Other"
        return {
            "route": "income",
            "txn_date": txn_date,
            "amount": amount_abs,
            "description": description,
            "category": income_category,
            "source": default_income_source,
            "target": f"{default_income_source}:{income_category}",
        }
    income_category = mapped_category if mapped_category in INCOME_CATEGORIES else "Other"
    return {
        "route": "income",
        "txn_date": txn_date,
        "amount": amount_abs,
        "description": description,
        "category": income_category,
        "source": default_income_source,
        "target": f"{default_income_source}:{income_category}",
    }


def _merge_ai_statement_route(
    base_row: dict,
    ai_row: dict | None,
    fallback_route: dict,
) -> dict:
    merged = dict(fallback_route)
    if not ai_row:
        merged["ai_route_used"] = False
        return merged

    route = str(ai_row.get("route", "unknown") or "unknown")
    merged["ai_route_used"] = route != "unknown"
    merged["ai_confidence"] = float(ai_row.get("confidence", 0.5) or 0.5)

    if route == "fixed_expense":
        merged.update(
            {
                "route": "fixed_expense",
                "category": ai_row.get("category", merged.get("category", "Other")),
                "is_recurring": True if ai_row.get("is_recurring", True) else False,
                "frequency": ai_row.get("frequency", "monthly") or "monthly",
                "fixed_name": ai_row.get("fixed_name") or base_row.get("description") or "Fixed expense",
                "target": ai_row.get("fixed_name") or base_row.get("description") or "Fixed expense",
            }
        )
        return merged

    if route == "income":
        merged.update(
            {
                "route": "income",
                "category": ai_row.get("category", merged.get("category", "Other")),
                "source": ai_row.get("source", merged.get("source", "Shared Checking")),
                "target": f"{ai_row.get('source', merged.get('source', 'Shared Checking'))}:{ai_row.get('category', merged.get('category', 'Other'))}",
            }
        )
        return merged

    if route == "variable_expense":
        merged.update(
            {
                "route": "variable_expense",
                "category": ai_row.get("category", merged.get("category", "Other")),
                "is_recurring": bool(ai_row.get("is_recurring", merged.get("is_recurring", False))),
                "target": ai_row.get("category", merged.get("category", "Other")),
            }
        )
        return merged

    if route == "savings_transfer":
        merged.update(
            {
                "route": "savings_transfer",
                "savings_account": ai_row.get("savings_account", merged.get("savings_account", "Joint Savings")),
                "savings_type": ai_row.get("savings_type", merged.get("savings_type", "deposit")),
                "target": ai_row.get("savings_account", merged.get("savings_account", "Joint Savings")),
            }
        )
        return merged

    if route == "debt_payment":
        merged.update(
            {
                "route": "debt_payment",
                "debt_name": ai_row.get("debt_name", merged.get("debt_name", "")),
                "target": ai_row.get("debt_name", merged.get("debt_name", "")),
            }
        )
        return merged

    merged["ai_route_used"] = False
    return merged


def _statement_owner_defaults(statement_owner: str) -> tuple[str, str]:
    owner = (statement_owner or "Joint").strip().lower()
    if owner == "caleb":
        return "Caleb", "Caleb Savings"
    if owner == "jamie":
        return "Jamie", "Jamie Savings"
    return "Shared Checking", "Joint Savings"


def _statement_route_fingerprint(route_payload: dict) -> str:
    route = str(route_payload.get("route", ""))
    txn_date = str(route_payload.get("txn_date", ""))
    amount = float(route_payload.get("amount", 0.0))
    desc = _normalize_text(str(route_payload.get("description", "")))
    target = str(route_payload.get("target", ""))
    category = str(route_payload.get("category", ""))
    frequency = str(route_payload.get("frequency", ""))

    if route == "fixed_expense":
        raw = f"{route}|{target}|{amount:.2f}|{category}|{frequency}"
    elif route == "debt_payment":
        raw = f"{route}|{txn_date}|{amount:.2f}|{desc}|{target}"
    else:
        raw = f"{route}|{txn_date}|{amount:.2f}|{desc}|{target}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _import_fingerprint(route_payload: dict) -> str:
    return _statement_route_fingerprint(route_payload)


# ==========================================================================
# PAGE: PLANNING
# ==========================================================================
if page == "🧭 Planning":
    _page_header("🧭 Planning", "Forward-looking cash flow, guardrails, debt strategy, net worth, and bulk imports.")

    tab_forecast, tab_guardrails, tab_debt_worth, tab_imports = st.tabs(
        ["📅 Forecast", "⏰ Bills & Guardrails", "💳 Debt + Net Worth", "📥 Import + Rules"]
    )

    with tab_forecast:
        with _section_card("Cash Flow Forecast", "Projects income, expenses, and safe-to-spend for upcoming months."):
            horizon = st.slider("Forecast Horizon (months)", min_value=1, max_value=12, value=3)
            forecast_rows = _cashflow_forecast(sel_year, sel_month, horizon_months=int(horizon))
            df_fc = pd.DataFrame(forecast_rows)

            if not df_fc.empty:
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Projected Net (Next Month)", f"${df_fc.iloc[0]['projected_net']:,.2f}")
                with c2:
                    st.metric("Safe To Spend (Next Month)", f"${df_fc.iloc[0]['safe_to_spend']:,.2f}")
                with c3:
                    st.metric("Horizon Net Total", f"${df_fc['projected_net'].sum():,.2f}")

                fig_fc = go.Figure()
                fig_fc.add_trace(go.Bar(name="Projected Income", x=df_fc["label"], y=df_fc["projected_income"]))
                fig_fc.add_trace(go.Bar(name="Projected Outflow", x=df_fc["label"], y=(df_fc["fixed_cost"] + df_fc["recurring_variable"] + df_fc["discretionary_variable"] + df_fc["debt_minimum"])))
                fig_fc.add_trace(go.Scatter(name="Projected Net", x=df_fc["label"], y=df_fc["projected_net"], mode="lines+markers"))
                fig_fc.update_layout(barmode="group", height=340, margin=dict(t=20, b=0), yaxis_title="Amount ($)")
                st.plotly_chart(fig_fc, width="stretch")

                df_show = df_fc.copy()
                for col in ["projected_income", "fixed_cost", "recurring_variable", "discretionary_variable", "debt_minimum", "projected_net", "safe_to_spend"]:
                    df_show[col] = df_show[col].map(lambda x: f"{x:,.2f}")
                df_show = df_show.rename(
                    columns={
                        "label": "Month",
                        "projected_income": "Income ($)",
                        "fixed_cost": "Fixed ($)",
                        "recurring_variable": "Recurring Var ($)",
                        "discretionary_variable": "Discretionary Var ($)",
                        "debt_minimum": "Debt Minimums ($)",
                        "projected_net": "Projected Net ($)",
                        "safe_to_spend": "Safe To Spend ($)",
                    }
                )
                st.dataframe(df_show[["Month", "Income ($)", "Fixed ($)", "Recurring Var ($)", "Discretionary Var ($)", "Debt Minimums ($)", "Projected Net ($)", "Safe To Spend ($)"]], width="stretch", hide_index=True)

    with tab_guardrails:
        with _section_card("Bill Calendar & Reminders", f"Bills for {MONTHS[sel_month]} {sel_year} with due-soon and overdue flags."):
            bill_items = _build_bill_calendar(sel_year, sel_month)
            if bill_items:
                df_bills = pd.DataFrame(bill_items)
                status_order = {"Overdue": 0, "Due soon": 1, "Upcoming": 2}
                df_bills["status_rank"] = df_bills["status"].map(status_order).fillna(3)
                df_bills = df_bills.sort_values(["status_rank", "due_date"]).drop(columns=["status_rank"])
                st.dataframe(df_bills.rename(columns={"type": "Type", "name": "Name", "due_date": "Due Date", "amount": "Amount ($)", "status": "Status"}), width="stretch", hide_index=True)
            else:
                _notify("info", "No upcoming bills detected for this month.")

        with _section_card("Budget Guardrails", "Set category spending limits and monitor usage against monthly caps."):
            lim_c1, lim_c2 = st.columns([1, 2])
            with lim_c1:
                with st.form("add_guardrail_form", clear_on_submit=True):
                    guard_cat = st.selectbox("Category", VARIABLE_EXPENSE_CATEGORIES)
                    guard_limit = st.number_input("Monthly Limit ($)", min_value=1.0, step=1.0, format="%.2f")
                    guard_submit = st.form_submit_button("Save Guardrail", width="stretch")
                    if guard_submit:
                        db.upsert_budget_limit(guard_cat, float(guard_limit))
                        _notify("success", f"Guardrail saved for {guard_cat}.")
                        st.rerun()

            with lim_c2:
                limits = db.get_budget_limits()
                month_rows = db.get_variable_expenses(year=sel_year, month=sel_month)
                spent_by_cat: dict[str, float] = {}
                for row in month_rows:
                    spent_by_cat[row["category"]] = spent_by_cat.get(row["category"], 0.0) + float(row["amount"])

                if limits:
                    limit_rows = []
                    for l in limits:
                        spent = float(spent_by_cat.get(l["category"], 0.0))
                        cap = float(l["monthly_limit"])
                        usage = (spent / cap * 100) if cap > 0 else 0.0
                        status = "Good"
                        if usage >= 100:
                            status = "Over"
                        elif usage >= 90:
                            status = "Near limit"
                        limit_rows.append(
                            {
                                "ID": int(l["id"]),
                                "Category": l["category"],
                                "Limit ($)": f"{cap:,.2f}",
                                "Spent ($)": f"{spent:,.2f}",
                                "Usage": f"{usage:.1f}%",
                                "Status": status,
                                "Safe To Spend ($)": f"{max(cap - spent, 0.0):,.2f}",
                            }
                        )
                    st.dataframe(pd.DataFrame(limit_rows), width="stretch", hide_index=True)

                    del_id = st.number_input("Delete guardrail by ID", min_value=1, step=1, key="del_guardrail_id")
                    if st.button("Delete Guardrail", key="del_guardrail_btn"):
                        db.delete_budget_limit(int(del_id))
                        _notify("success", "Guardrail deleted.")
                        st.rerun()
                else:
                    st.caption("No guardrails set yet.")

    with tab_debt_worth:
        with _section_card("Debt Payoff Optimizer", "Compare snowball vs avalanche and model extra monthly payments."):
            debts = [d for d in db.get_debts() if float(d["current_balance"]) > 0]
            if debts:
                strategy = st.radio("Payoff Strategy", ["Snowball (smallest balance first)", "Avalanche (highest APR first)"], horizontal=True)
                extra_payment = st.number_input("Extra Monthly Payment ($)", min_value=0.0, step=10.0, value=100.0)

                sim_debts = [
                    {
                        "name": d["name"],
                        "balance": float(d["current_balance"]),
                        "apr": float(d.get("interest_rate", 0) or 0),
                        "min": float(d.get("minimum_payment", 0) or 0),
                    }
                    for d in debts
                ]

                def debt_sort_key(item: dict):
                    if strategy.startswith("Snowball"):
                        return (item["balance"], -item["apr"])
                    return (-item["apr"], item["balance"])

                months = 0
                total_interest = 0.0
                sim_cap = 600
                while months < sim_cap and any(d["balance"] > 0.01 for d in sim_debts):
                    months += 1
                    for d in sim_debts:
                        if d["balance"] <= 0:
                            continue
                        monthly_rate = d["apr"] / 100 / 12
                        interest = d["balance"] * monthly_rate
                        d["balance"] += interest
                        total_interest += interest

                    for d in sim_debts:
                        if d["balance"] <= 0:
                            continue
                        pay = min(d["balance"], d["min"])
                        d["balance"] -= pay

                    remaining_extra = float(extra_payment)
                    for d in sorted([x for x in sim_debts if x["balance"] > 0], key=debt_sort_key):
                        if remaining_extra <= 0:
                            break
                        pay = min(d["balance"], remaining_extra)
                        d["balance"] -= pay
                        remaining_extra -= pay

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Projected Payoff Time", f"{months} months" if months < sim_cap else "> 600 months")
                with c2:
                    st.metric("Estimated Interest", f"${total_interest:,.2f}")
                with c3:
                    st.metric("Current Debt", f"${sum(float(d['current_balance']) for d in debts):,.2f}")
            else:
                st.caption("No debt balances to optimize yet.")

        with _section_card("Net Worth Tracker", "Track assets, liabilities, and historical net worth snapshots."):
            asset_rows = db.get_asset_accounts()
            savings_total = sum(db.get_all_savings_balances().values())
            debt_total = db.get_total_debt()
            assets_total = savings_total + sum(float(a["balance"]) for a in asset_rows)
            net_worth_now = assets_total - debt_total

            nw1, nw2, nw3 = st.columns(3)
            with nw1:
                st.metric("Total Assets", f"${assets_total:,.2f}")
            with nw2:
                st.metric("Total Liabilities", f"${debt_total:,.2f}")
            with nw3:
                st.metric("Net Worth", f"${net_worth_now:,.2f}")

            with st.expander("Manage Asset Accounts"):
                with st.form("asset_add_form", clear_on_submit=True):
                    a1, a2, a3 = st.columns(3)
                    with a1:
                        asset_name = st.text_input("Account Name")
                    with a2:
                        asset_type = st.selectbox("Type", db.ASSET_ACCOUNT_TYPES)
                    with a3:
                        asset_balance = st.number_input("Balance ($)", step=10.0, format="%.2f")
                    add_asset = st.form_submit_button("Add Asset Account")
                    if add_asset and asset_name.strip():
                        db.add_asset_account(asset_name.strip(), asset_type, float(asset_balance))
                        _notify("success", "Asset account added.")
                        st.rerun()

                if asset_rows:
                    for a in asset_rows:
                        with st.form(f"asset_edit_{int(a['id'])}"):
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                e_name = st.text_input("Name", value=a["name"], key=f"asset_name_{int(a['id'])}")
                            with c2:
                                type_opts = db.ASSET_ACCOUNT_TYPES
                                e_type = st.selectbox("Type", type_opts, index=type_opts.index(a["account_type"]) if a["account_type"] in type_opts else 0, key=f"asset_type_{int(a['id'])}")
                            with c3:
                                e_bal = st.number_input("Balance ($)", step=10.0, format="%.2f", value=float(a["balance"]), key=f"asset_bal_{int(a['id'])}")
                            b1, b2 = st.columns(2)
                            with b1:
                                save_asset = st.form_submit_button("Save")
                            with b2:
                                del_asset = st.form_submit_button("Delete")
                            if save_asset:
                                db.update_asset_account(int(a["id"]), e_name.strip(), e_type, float(e_bal))
                                st.rerun()
                            if del_asset:
                                db.delete_asset_account(int(a["id"]))
                                st.rerun()

            snap_c1, snap_c2 = st.columns([1, 2])
            with snap_c1:
                snap_notes = st.text_input("Snapshot Note (optional)", key="nw_snap_note")
                if st.button("Save Net Worth Snapshot", key="save_nw_snapshot"):
                    db.add_net_worth_snapshot(str(date.today()), float(assets_total), float(debt_total), snap_notes)
                    _notify("success", "Snapshot saved.")
                    st.rerun()
            with snap_c2:
                snapshots = db.get_net_worth_snapshots(limit=48)
                if snapshots:
                    df_snap = pd.DataFrame(snapshots)
                    df_snap["net_worth"] = df_snap["total_assets"] - df_snap["total_liabilities"]
                    df_snap = df_snap.sort_values("snapshot_date")
                    fig_nw = px.line(df_snap, x="snapshot_date", y="net_worth", markers=True, title="Net Worth Trend")
                    fig_nw.update_layout(height=280, margin=dict(t=40, b=0))
                    st.plotly_chart(fig_nw, width="stretch")

    with tab_imports:
        with _section_card("Import Rules Engine", "Define auto-categorization rules applied during CSV imports."):
            with st.form("add_import_rule_form", clear_on_submit=True):
                r1, r2, r3, r4, r5 = st.columns(5)
                with r1:
                    rule_field = st.selectbox("Field", ["description", "category"])
                with r2:
                    rule_pattern = st.text_input("Pattern", placeholder="e.g. starbucks")
                with r3:
                    rule_target = st.selectbox("Target Category", VARIABLE_EXPENSE_CATEGORIES)
                with r4:
                    rule_rec = st.checkbox("Recurring")
                with r5:
                    rule_priority = st.number_input("Priority", min_value=1, max_value=9999, value=100, step=1)
                add_rule = st.form_submit_button("Add Rule")
                if add_rule and rule_pattern.strip():
                    db.add_import_rule(rule_field, rule_pattern.strip(), rule_target, bool(rule_rec), int(rule_priority))
                    _notify("success", "Import rule added.")
                    st.rerun()

            rules = db.get_import_rules()
            if rules:
                df_rules = pd.DataFrame(rules)
                st.dataframe(df_rules[["id", "field", "pattern", "target_category", "recurring_flag", "priority"]], width="stretch", hide_index=True)
                del_rule_id = st.number_input("Delete rule by ID", min_value=1, step=1, key="del_rule_id")
                if st.button("Delete Rule", key="del_rule_btn"):
                    db.delete_import_rule(int(del_rule_id))
                    _notify("success", "Rule deleted.")
                    st.rerun()

        with _section_card("Statement Import Pipeline", "Import CSV/OFX/QFX/PDF statements into income, expenses, savings transfers, and debt payments with dedupe."):
            up_file = st.file_uploader("Upload Statement", type=["csv", "ofx", "qfx", "pdf"], key="import_csv")
            if up_file is not None:
                df_raw, file_type, parse_error = _statement_file_to_dataframe(up_file)
                if parse_error:
                    _notify("error", parse_error)
                elif file_type in {"ofx", "qfx", "pdf"}:
                    st.caption(f"Detected {file_type.upper()} format. Column mapping was auto-applied.")

                if not df_raw.empty:
                    cols = list(df_raw.columns)
                    c1, c2, c3, c4, c5, c6 = st.columns(6)
                    if file_type == "csv":
                        with c1:
                            col_date = st.selectbox("Date Column", cols, index=cols.index("date") if "date" in cols else 0)
                        with c2:
                            col_amount = st.selectbox("Amount Column", cols, index=cols.index("amount") if "amount" in cols else min(1, len(cols)-1))
                        with c3:
                            col_desc = st.selectbox("Description Column", cols, index=cols.index("description") if "description" in cols else min(2, len(cols)-1))
                        with c4:
                            col_cat = st.selectbox("Category Column", ["(none)"] + cols)
                    else:
                        col_date = "date"
                        col_amount = "amount"
                        col_desc = "description"
                        col_cat = "category" if "category" in cols else "(none)"
                        with c1:
                            st.text_input("Date Column", value=col_date, disabled=True)
                        with c2:
                            st.text_input("Amount Column", value=col_amount, disabled=True)
                        with c3:
                            st.text_input("Description Column", value=col_desc, disabled=True)
                        with c4:
                            st.text_input("Category Column", value=col_cat, disabled=True)
                    with c5:
                        import_savings_account = st.selectbox("Savings Account", db.SAVINGS_ACCOUNTS, index=min(2, len(db.SAVINGS_ACCOUNTS) - 1))
                    with c6:
                        import_income_source = st.selectbox("Income Source", INCOME_SOURCES, index=min(2, len(INCOME_SOURCES) - 1))

                    if file_type == "pdf":
                        pdf_owner = st.selectbox(
                            "PDF Statement Owner",
                            ["Caleb", "Jamie", "Joint"],
                            index=2,
                            help="Choose which household account this PDF statement belongs to so routing defaults match the right source and savings account.",
                        )
                        owner_income_source, owner_savings_account = _statement_owner_defaults(pdf_owner)
                        import_income_source = owner_income_source
                        import_savings_account = owner_savings_account
                        st.caption(
                            f"Default routing for this PDF: income source = {owner_income_source}, savings account = {owner_savings_account}."
                        )

                        pdf_ai_enabled = st.checkbox(
                            "Use AI-assisted PDF parsing",
                            value=ai.is_ai_available(),
                            help="AI helps classify each PDF row as fixed expense, variable expense, income, savings transfer, or debt payment.",
                            key="pdf_ai_enabled",
                        )
                    else:
                        pdf_ai_enabled = False

                    debt_rows = db.get_debts()
                    debt_names = [str(d.get("name", "")) for d in debt_rows if str(d.get("name", ""))]
                    staged_rows: list[dict] = []
                    invalid_rows = 0
                    for _, row in df_raw.iterrows():
                        parsed_date = _parse_statement_date(row.get(col_date))
                        parsed_amount = _parse_statement_amount(row.get(col_amount))
                        if not parsed_date or parsed_amount is None:
                            invalid_rows += 1
                            continue
                        raw_desc = str(row.get(col_desc, "") or "")
                        raw_category = "Other" if col_cat == "(none)" else str(row.get(col_cat, "Other") or "Other")
                        mapped_category, mapped_recurring = _apply_import_rules(
                            raw_desc, raw_category, rules
                        )
                        staged_rows.append(
                            {
                                "row_id": len(staged_rows),
                                "txn_date": parsed_date,
                                "amount": float(parsed_amount),
                                "description": raw_desc,
                                "raw_category": raw_category,
                                "mapped_category": mapped_category,
                                "mapped_recurring": mapped_recurring,
                            }
                        )

                    ai_classifications: dict[int, dict] = {}
                    if file_type == "pdf" and pdf_ai_enabled and ai.is_ai_available() and staged_rows:
                        ai_rows = ai.classify_statement_rows(
                            staged_rows,
                            pdf_owner,
                            import_income_source,
                            import_savings_account,
                            debt_names,
                        )
                        ai_classifications = {
                            int(item.get("row_id", idx)): item
                            for idx, item in enumerate(ai_rows)
                            if isinstance(item, dict)
                        }
                        if not ai_classifications:
                            _notify("warning", "AI PDF classification could not be parsed. Falling back to heuristic routing.")

                    routed_rows: list[dict] = []
                    for base_row in staged_rows:
                        fallback = _route_statement_row(
                            txn_date=base_row["txn_date"],
                            signed_amount=float(base_row["amount"]),
                            description=base_row["description"],
                            mapped_category=str(base_row["mapped_category"]),
                            mapped_recurring=bool(base_row["mapped_recurring"]),
                            debt_rows=debt_rows,
                            savings_account=import_savings_account,
                            default_income_source=import_income_source,
                        )

                        ai_row = ai_classifications.get(int(base_row["row_id"])) if ai_classifications else None
                        payload = _merge_ai_statement_route(base_row, ai_row, fallback)
                        payload["fingerprint"] = _import_fingerprint(payload)
                        routed_rows.append(payload)

                    if routed_rows:
                        preview_limit = min(300, len(routed_rows))
                        st.caption(
                            f"Prepared {len(routed_rows)} valid rows, {invalid_rows} invalid rows skipped during parsing. Showing first {preview_limit}."
                        )

                        summary_counts: dict[str, int] = {}
                        for rr in routed_rows:
                            summary_counts[rr["route"]] = summary_counts.get(rr["route"], 0) + 1
                        st.write(
                            "Routing summary: "
                            + ", ".join(f"{route}={count}" for route, count in sorted(summary_counts.items()))
                        )

                        debt_id_to_name = {int(d["id"]): str(d["name"]) for d in debt_rows}
                        debt_name_to_id = {v: k for k, v in debt_id_to_name.items()}
                        debt_name_options = ["", *sorted(debt_name_to_id.keys())]

                        editable_rows: list[dict] = []
                        for idx, rr in enumerate(routed_rows[:preview_limit]):
                            editable_rows.append(
                                {
                                    "row_id": idx,
                                    "txn_date": rr.get("txn_date", ""),
                                    "amount": float(rr.get("amount", 0.0)),
                                    "description": rr.get("description", ""),
                                    "route": rr.get("route", "variable_expense"),
                                    "category": rr.get("category", "Other"),
                                    "source": rr.get("source", import_income_source),
                                    "savings_account": rr.get("savings_account", import_savings_account),
                                    "savings_type": rr.get("savings_type", "deposit"),
                                    "is_recurring": bool(rr.get("is_recurring", False)),
                                    "frequency": rr.get("frequency", "monthly"),
                                    "fixed_name": rr.get("fixed_name", ""),
                                    "debt_name": debt_id_to_name.get(int(rr.get("debt_id", 0)), "") if rr.get("debt_id") else "",
                                    "ai_confidence": float(rr.get("ai_confidence", 0.0) or 0.0),
                                    "ai_route_used": bool(rr.get("ai_route_used", False)),
                                }
                            )

                        st.caption("Per-row overrides: adjust route/fields before import.")
                        edited_df = st.data_editor(
                            pd.DataFrame(editable_rows),
                            width="stretch",
                            hide_index=True,
                            key="import_route_editor",
                            column_config={
                                "row_id": st.column_config.NumberColumn("Row", disabled=True),
                                "txn_date": st.column_config.TextColumn("Date", disabled=True),
                                "amount": st.column_config.NumberColumn("Amount", disabled=True, format="%.2f"),
                                "description": st.column_config.TextColumn("Description", disabled=True, width="large"),
                                "route": st.column_config.SelectboxColumn(
                                    "Route",
                                    options=["income", "variable_expense", "fixed_expense", "savings_transfer", "debt_payment"],
                                    required=True,
                                ),
                                "category": st.column_config.SelectboxColumn(
                                    "Category",
                                    options=sorted(set(VARIABLE_EXPENSE_CATEGORIES + INCOME_CATEGORIES + FIXED_EXPENSE_CATEGORIES + ["Other"])),
                                ),
                                "source": st.column_config.SelectboxColumn("Income Source", options=INCOME_SOURCES),
                                "savings_account": st.column_config.SelectboxColumn("Savings Account", options=db.SAVINGS_ACCOUNTS),
                                "savings_type": st.column_config.SelectboxColumn("Savings Type", options=["deposit", "withdrawal"]),
                                "is_recurring": st.column_config.CheckboxColumn("Recurring"),
                                "frequency": st.column_config.SelectboxColumn("Frequency", options=["monthly", "yearly", "one_time"]),
                                "fixed_name": st.column_config.TextColumn("Fixed Name"),
                                "debt_name": st.column_config.SelectboxColumn("Debt", options=debt_name_options),
                                "ai_confidence": st.column_config.NumberColumn("AI Confidence", disabled=True, format="%.2f"),
                                "ai_route_used": st.column_config.CheckboxColumn("AI Used", disabled=True),
                            },
                        )
                        st.caption("Import uses the edited rows shown above.")

                        if st.button("Import Routed Rows", key="import_preview_rows"):
                            imported = 0
                            duplicates = 0
                            failed = 0

                            edited_rows = edited_df.to_dict("records") if isinstance(edited_df, pd.DataFrame) else []
                            for er in edited_rows:
                                route = str(er.get("route", "variable_expense"))
                                amount = float(er.get("amount", 0.0))
                                txn_date = str(er.get("txn_date", ""))
                                description = str(er.get("description", "") or "")

                                rr: dict = {
                                    "route": route,
                                    "txn_date": txn_date,
                                    "amount": amount,
                                    "description": description,
                                }
                                if route == "income":
                                    cat = str(er.get("category", "Other"))
                                    rr["category"] = cat if cat in INCOME_CATEGORIES else "Other"
                                    rr["source"] = str(er.get("source", import_income_source))
                                    rr["target"] = f"{rr['source']}:{rr['category']}"
                                elif route == "variable_expense":
                                    cat = str(er.get("category", "Other"))
                                    rr["category"] = cat if cat in VARIABLE_EXPENSE_CATEGORIES else "Other"
                                    rr["is_recurring"] = bool(er.get("is_recurring", False))
                                    rr["target"] = rr["category"]
                                elif route == "fixed_expense":
                                    fixed_name = str(er.get("fixed_name", "") or description or "Fixed expense")
                                    rr["fixed_name"] = fixed_name
                                    rr["category"] = str(er.get("category", "Other"))
                                    rr["frequency"] = str(er.get("frequency", "monthly") or "monthly")
                                    rr["is_recurring"] = True
                                    rr["target"] = fixed_name
                                elif route == "savings_transfer":
                                    rr["savings_account"] = str(er.get("savings_account", import_savings_account))
                                    rr["savings_type"] = str(er.get("savings_type", "deposit"))
                                    rr["target"] = rr["savings_account"]
                                elif route == "debt_payment":
                                    debt_name = str(er.get("debt_name", "") or "")
                                    rr["debt_id"] = int(debt_name_to_id.get(debt_name, 0)) if debt_name else 0
                                    rr["target"] = debt_name or ""
                                else:
                                    failed += 1
                                    continue

                                rr["fingerprint"] = _import_fingerprint(rr)
                                fp = str(rr["fingerprint"])
                                if db.has_import_fingerprint(fp):
                                    duplicates += 1
                                    continue

                                try:
                                    if rr["route"] == "income":
                                        db.add_income(
                                            rr["txn_date"],
                                            float(rr["amount"]),
                                            rr.get("category", "Other"),
                                            rr.get("source", "Shared Checking"),
                                            rr.get("description", ""),
                                        )
                                    elif rr["route"] == "variable_expense":
                                        db.add_variable_expense(
                                            rr["txn_date"],
                                            float(rr["amount"]),
                                            rr.get("category", "Other"),
                                            rr.get("description", ""),
                                            bool(rr.get("is_recurring", False)),
                                        )
                                    elif rr["route"] == "fixed_expense":
                                        fixed_name = rr.get("fixed_name") or rr.get("description") or "Imported fixed expense"
                                        fixed_category = rr.get("category", "Other")
                                        fixed_frequency = rr.get("frequency", "monthly")
                                        db.add_fixed_expense(
                                            str(fixed_name),
                                            float(rr["amount"]),
                                            str(fixed_category),
                                            str(fixed_frequency if fixed_frequency in {"monthly", "yearly"} else "monthly"),
                                            rr["txn_date"],
                                            None,
                                            rr.get("description", "Statement import fixed expense"),
                                        )
                                    elif rr["route"] == "savings_transfer":
                                        db.add_savings_transaction(
                                            rr.get("savings_account", import_savings_account),
                                            rr["txn_date"],
                                            float(rr["amount"]),
                                            rr.get("savings_type", "deposit"),
                                            rr.get("description", "Statement import transfer"),
                                        )
                                    elif rr["route"] == "debt_payment":
                                        debt_id = int(rr.get("debt_id", 0))
                                        debt = next((d for d in debt_rows if int(d["id"]) == debt_id), None)
                                        if debt is None:
                                            failed += 1
                                            continue
                                        new_balance = max(float(debt["current_balance"]) - float(rr["amount"]), 0.0)
                                        db.update_debt_balance(debt_id, new_balance)
                                        debt["current_balance"] = new_balance
                                    else:
                                        failed += 1
                                        continue

                                    db.add_import_history(
                                        fp,
                                        rr["route"],
                                        rr["txn_date"],
                                        float(rr["amount"]),
                                        rr.get("description", ""),
                                    )
                                    imported += 1
                                except Exception:
                                    failed += 1

                            _notify(
                                "success",
                                f"Imported {imported} row(s). Duplicates skipped: {duplicates}. Failed: {failed}.",
                            )
                            st.rerun()


# ==========================================================================
# PAGE: DASHBOARD
# ==========================================================================
elif page == "📊 Dashboard":
    _page_header("📊 Dashboard", f"{MONTHS[sel_month]} {sel_year}")

    # --- gather data --------------------------------------------------------
    income_rows = db.get_income(year=sel_year, month=sel_month)
    var_rows = db.get_variable_expenses(year=sel_year, month=sel_month)
    fixed_cost = db.get_monthly_fixed_cost(sel_year, sel_month)
    goals = db.get_financial_goals()

    total_income = sum(r["amount"] for r in income_rows)
    total_variable = sum(r["amount"] for r in var_rows)
    total_expenses = fixed_cost + total_variable
    net = total_income - total_expenses

    with _section_card("Monthly Snapshot", "Core KPIs for your selected period."):
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

    with _section_card("Spending Composition", "Where money came from and where it went."):
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
                _notify("info", "No expenses recorded this month.")

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

    # --- recurring vs discretionary breakdown ---------------------------------------
    all_var_rows = db.get_variable_expenses(year=sel_year, month=sel_month)
    recurring_amount = sum(r["amount"] for r in all_var_rows if r.get("is_recurring"))
    discretionary_amount = sum(r["amount"] for r in all_var_rows if not r.get("is_recurring"))
    
    if all_var_rows:
        with _section_card("Recurring vs Discretionary", "Habit spend vs one-off spend and forward view."):
            col_rec_left, col_rec_right = st.columns(2)
            with col_rec_left:
                st.subheader("💰 Spending Type Breakdown")
                if recurring_amount > 0 or discretionary_amount > 0:
                    rec_data = {
                        "Type": [],
                        "Amount": [],
                    }
                    if recurring_amount > 0:
                        rec_data["Type"].append("Recurring Habits")
                        rec_data["Amount"].append(recurring_amount)
                    if discretionary_amount > 0:
                        rec_data["Type"].append("Discretionary")
                        rec_data["Amount"].append(discretionary_amount)

                    if rec_data["Type"]:
                        fig_rec = px.pie(
                            rec_data,
                            names="Type",
                            values="Amount",
                            color_discrete_sequence=["#FF6B6B", "#4ECDC4"],
                        )
                        fig_rec.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=300)
                        st.plotly_chart(fig_rec, width="stretch")

            with col_rec_right:
                st.subheader("📊 Monthly Forecast")
                st.markdown("**Based on recurring habits:**")
                if recurring_amount > 0:
                    st.metric("Recurring Habits This Month", f"${recurring_amount:,.2f}")
                    projected_next = recurring_amount
                    st.metric("Projected Next Month", f"${projected_next:,.2f}", delta=f"${projected_next - discretionary_amount:+,.2f}", delta_color="off")
                    st.caption(f"*Assumes {len([r for r in all_var_rows if r.get('is_recurring')])} recurring habits continue at same rate*")
                else:
                    _notify("info", "Mark variable expenses as 'recurring habits' to see forecasts.")

    # --- upcoming fixed expenses for current month (today onwards) --------------------
    upcoming_fixed_expenses = []
    fixed_expenses_all = db.get_fixed_expenses(active_only=True)
    
    today_date = today
    last_day_of_month = calendar.monthrange(sel_year, sel_month)[1]
    
    for fe in fixed_expenses_all:
        start_date = date.fromisoformat(fe["start_date"])
        end_date = date.fromisoformat(fe["end_date"]) if fe.get("end_date") else None
        
        # Calculate due date in current month
        if fe["frequency"] == "monthly":
            # Due on the same day of month as start_date
            try:
                due_date = date(sel_year, sel_month, start_date.day)
            except ValueError:
                # Handle case where day doesn't exist (e.g., Feb 30)
                due_date = date(sel_year, sel_month, min(start_date.day, last_day_of_month))
        else:  # yearly
            # Due on the anniversary in current month
            try:
                due_date = date(sel_year, start_date.month, start_date.day)
            except ValueError:
                due_date = date(sel_year, start_date.month, min(start_date.day, calendar.monthrange(sel_year, start_date.month)[1]))
        
        # Only show if: active, due date is in current month, and today or later
        if start_date <= today_date and (end_date is None or end_date >= today_date):
            if due_date.year == sel_year and due_date.month == sel_month and due_date >= today_date:
                upcoming_fixed_expenses.append((due_date, fe))
    
    # Sort by due date
    upcoming_fixed_expenses.sort(key=lambda x: x[0])
    
    if upcoming_fixed_expenses:
        with _section_card(f"⏰ Upcoming Fixed Expenses — Rest of {MONTHS[sel_month]}"):
            for due_date_val, fe in upcoming_fixed_expenses:
                monthly_eq = fe["amount"] if fe["frequency"] == "monthly" else fe["amount"] / 12
                days_until = (due_date_val - today_date).days

                if days_until == 0:
                    due_text = "🔴 DUE TODAY"
                else:
                    due_text = f"📅 {due_date_val.strftime('%b %d')}"

                st.write(f"• **{fe['name']}** — ${monthly_eq:,.2f} — {due_text}")

    # --- goals summary ------------------------------------------------------
    if goals:
        with _section_card("🎯 Goals Progress"):
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
        with _section_card("💵 Savings Snapshot"):
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
        with _section_card("💳 Debt Snapshot"):
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
    _page_header("💰 Income", "Track source-by-source earnings and edit entries quickly.")

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
            _kpi_tile(f"{src} — {MONTHS[sel_month]}", f"${src_mo:,.2f}")
    with kpi_cols[-1]:
        _kpi_tile("Total This Month", f"${total_month:,.2f}")

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
                    _kpi_tile(MONTHS[sel_month], f"${month_total:,.2f}")
                with m2:
                    _kpi_tile(f"{sel_year} Total", f"${year_total:,.2f}")

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
                            _notify("error", "Amount must be greater than zero.")
                        else:
                            db.add_income(str(inc_date), inc_amount, inc_cat,
                                          source, inc_desc)
                            _notify("success", f"✅ Added ${inc_amount:,.2f} to {source}.")
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
                                    _notify("success", "Entry updated.")
                                    st.rerun()
                                if del_it:
                                    db.delete_income(int(entry["id"]))
                                    _notify("success", "Entry deleted.")
                                    st.rerun()
                else:
                    st.caption(f"No income recorded for {MONTHS[sel_month]}.")


# ===========================================================================
# PAGE: FIXED EXPENSES
# ===========================================================================
elif page == "📌 Fixed Expenses":
    _page_header("📌 Fixed Expenses", "Recurring costs by category with monthly equivalents.")
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
        category_total = sum(
            float(expense["amount"])
            if expense["frequency"] == "monthly"
            else float(expense["amount"]) / 12
            for expense in category_rows
        )
        with card_columns[idx % 3]:
            with st.container(border=True):
                title_col, total_col = st.columns([3, 2])
                with title_col:
                    st.markdown(f"### {category}")
                with total_col:
                    _inline_stat(f"${category_total:,.2f}/mo")
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
                            _notify("error", "Name is required.")
                        elif fix_amount <= 0:
                            _notify("error", "Amount must be greater than zero.")
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
                            _notify("success", f"✅ Added fixed expense: {fix_name}")
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
                                        _notify("error", "Name is required.")
                                    elif edit_amount <= 0:
                                        _notify("error", "Amount must be greater than zero.")
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
                                        _notify("success", f"Updated {edit_name.strip()}.")
                                        st.rerun()

                                if delete_expense:
                                    db.delete_fixed_expense(int(expense["id"]))
                                    _notify("success", f"Deleted {expense['name']}.")
                                    st.rerun()
                else:
                    empty_message = "No active expenses in this category yet." if show_active else "No expenses in this category yet."
                    st.caption(empty_message)

    if not rows:
        _notify("info", "No fixed expenses found for the current filter.")


# ===========================================================================
# PAGE: VARIABLE EXPENSES
# ===========================================================================
elif page == "🛒 Variable Expenses":
    _page_header("🛒 Variable Expenses", "Log ad-hoc spending with trend and category insights.")

    rows = db.get_variable_expenses(year=sel_year, month=sel_month)
    all_var_rows = db.get_variable_expenses()

    entry_col, review_col = st.columns([1, 2])
    with entry_col:
        with st.container(border=True):
            st.subheader("Quick Add")

            # --- Live category suggestion (outside the form so it reacts instantly) ---
            suggest_desc = st.text_input(
                "Description",
                key="var_desc_suggest",
                placeholder="e.g. Starbucks, Walmart, Netflix",
                help="Type a description to get an AI-powered category suggestion.",
            )
            suggest_amount = st.number_input(
                "Amount ($)", min_value=0.01, step=0.01, format="%.2f", key="var_amount_suggest"
            )
            
            suggested_cat = ""
            suggestion_source = "none"
            if suggest_desc.strip():
                suggested_cat, suggestion_source = ai.suggest_category(
                    suggest_desc.strip(), suggest_amount, all_var_rows
                )
            
            source_labels = {"history": "📜 from your history", "keyword": "🔑 keyword match", "ai": "🤖 AI suggestion", "none": ""}
            if suggested_cat:
                st.caption(f"Suggested: **{suggested_cat}** {source_labels.get(suggestion_source, '')}")
            
            with st.form("var_form", clear_on_submit=True):
                # Pre-select the suggested category if available
                default_cat_idx = VARIABLE_EXPENSE_CATEGORIES.index(suggested_cat) if suggested_cat in VARIABLE_EXPENSE_CATEGORIES else 0
                var_cat = st.selectbox("Category", VARIABLE_EXPENSE_CATEGORIES, index=default_cat_idx)
                var_date = st.date_input("Date", value=today)
                var_desc = st.text_input("Description (optional)", value=suggest_desc)
                var_is_recurring = st.checkbox("🔄 Recurring habit (projects forward)")
                submitted = st.form_submit_button("Add Expense", width="stretch")
                if submitted:
                    var_amount = suggest_amount
                    if var_amount <= 0:
                        _notify("error", "Amount must be greater than zero.")
                    else:
                        duplicates = [
                            r for r in all_var_rows
                            if r["date"] == str(var_date)
                            and float(r["amount"]) == float(var_amount)
                            and r["category"] == var_cat
                        ]
                        if duplicates:
                            _notify("warning", "A similar expense already exists for this date/category/amount.")
                        db.add_variable_expense(str(var_date), var_amount, var_cat, var_desc, var_is_recurring)
                        _notify("success", f"✅ Added ${var_amount:,.2f} expense on {var_date}.")
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
                    window_start = pd.Timestamp(today) - pd.Timedelta(days=59)
                    df_30 = df_all[df_all["date"] >= window_start].copy()
                else:
                    df_30 = pd.DataFrame()

                if not df_30.empty:
                    df_trend = df_30.groupby("date")["amount"].sum().reset_index()
                    fig_trend = px.line(
                        df_trend,
                        x="date",
                        y="amount",
                        title="Last 60 Days Spend",
                        labels={"amount": "Amount ($)", "date": "Date"},
                        markers=True,
                    )
                    fig_trend.update_layout(height=280, margin=dict(t=40, b=0))
                    st.plotly_chart(fig_trend, width="stretch")
                else:
                    _notify("info", "No variable expenses in the last 60 days.")

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
                        _notify("info", "No expenses match this filter.")
                    else:
                        df_show = df_tab[["date", "amount", "category", "description"]].copy()
                        df_show.columns = ["Date", "Amount ($)", "Category", "Description"]
                        df_show["Amount ($)"] = df_show["Amount ($)"].map(lambda x: f"{x:,.2f}")
                        st.dataframe(df_show, width="stretch", hide_index=True)

                        st.caption("Inline Actions")
                        for expense in df_tab.sort_values("date", ascending=False).to_dict("records"):
                            row_label = f"{expense['date']} • ${expense['amount']:,.2f} • {expense['category']}"
                            is_recurring_badge = " 🔄" if expense.get("is_recurring") else ""
                            with st.expander(row_label + is_recurring_badge):
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
                                    
                                    edit_is_recurring = st.checkbox(
                                        "🔄 Recurring habit (projects forward)",
                                        value=bool(expense.get("is_recurring", 0)),
                                        key=f"edit_var_recurring_{idx}_{int(expense['id'])}",
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
                                            edit_is_recurring,
                                        )
                                        _notify("success", "Expense updated.")
                                        st.rerun()

                                    if delete_item:
                                        db.delete_variable_expense(int(expense["id"]))
                                        _notify("success", "Expense deleted.")
                                        st.rerun()
        else:
            _notify("info", "No variable expenses for this period.")


# ===========================================================================
# PAGE: SAVINGS
# ===========================================================================
elif page == "💵 Savings":
    _page_header("💵 Savings", "Monitor balances and activity across savings accounts.")

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
                        _notify("error", "Amount must be greater than zero.")
                    else:
                        current_bal = db.get_savings_balance(sav_account)
                        if sav_type == "withdrawal" and sav_amount > current_bal:
                            _notify("error", 
                                f"Withdrawal of ${sav_amount:,.2f} exceeds the current "
                                f"{sav_account} balance of ${current_bal:,.2f}."
                            )
                        else:
                            db.add_savings_transaction(
                                sav_account, str(sav_date), sav_amount, sav_type, sav_desc
                            )
                            action = "Deposited" if sav_type == "deposit" else "Withdrew"
                            _notify("success", 
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
                                    _notify("success", "Transaction updated.")
                                    st.rerun()
                                if del_it:
                                    db.delete_savings_transaction(int(row["id"]))
                                    _notify("success", "Transaction deleted.")
                                    st.rerun()
                else:
                    _notify("info", "No savings transactions recorded for this view.")


# ===========================================================================
# PAGE: DEBT
# ===========================================================================
elif page == "💳 Debt":
    _page_header("💳 Debt", "Track payoff progress, linked expenses, and payment cadence.")

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
                    _notify("error", "Debt name is required.")
                elif debt_original <= 0:
                    _notify("error", "Original amount must be greater than zero.")
                elif debt_balance > debt_original:
                    _notify("error", "Current balance cannot exceed the original amount.")
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
                    _notify("success", f"✅ Added debt: {debt_name}")
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
                                _notify("error", "Payment exceeds remaining balance.")
                            else:
                                new_balance = max(d["current_balance"] - payment_amt, 0.0)
                                db.update_debt_balance(d["id"], new_balance)
                                _notify("success", f"Payment of ${payment_amt:,.2f} applied.")
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
                                            _notify("error", "Payment exceeds remaining balance.")
                                        else:
                                            db.apply_debt_payment(
                                                d["id"], fe["id"], sel_year, sel_month, fe["amount"]
                                            )
                                            _notify("success", 
                                                f"Applied ${fe['amount']:,.2f} from '{fe['name']}' for {MONTHS[sel_month]} {sel_year}."
                                            )
                                            st.rerun()
                                if st.button(
                                    "Unlink",
                                    key=f"unlink_fe_{d['id']}_{fe['id']}",
                                    width="stretch",
                                ):
                                    db.unlink_fixed_expense_from_debt(int(fe["id"]))
                                    _notify("success", f"Unlinked '{fe['name']}' from {d['name']}.")
                                    st.rerun()
                    else:
                        st.caption("No fixed expenses linked to this debt.")

                    if st.button("Delete Debt", key=f"delete_debt_{d['id']}", width="stretch"):
                        db.delete_debt(int(d["id"]))
                        _notify("success", f"Deleted {d['name']}.")
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
        _notify("info", "No debts recorded yet.")


# ===========================================================================
# PAGE: FINANCIAL GOALS
# ===========================================================================
elif page == "🎯 Financial Goals":
    _page_header("🎯 Financial Goals", "Set targets and monitor progress toward each milestone.")

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
                    _notify("error", "Goal name is required.")
                elif goal_target <= 0:
                    _notify("error", "Target amount must be greater than zero.")
                else:
                    db.add_financial_goal(
                        goal_name.strip(),
                        goal_target,
                        goal_current,
                        str(goal_date) if goal_date else None,
                        goal_desc,
                    )
                    _notify("success", f"✅ Goal '{goal_name}' added.")
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
            _notify("success", "Goal deleted.")
            st.rerun()
    else:
        _notify("info", "No financial goals set yet.")


# ===========================================================================
# PAGE: REPORTS
# ===========================================================================
elif page == "📈 Reports":
    _page_header("📈 Reports", "Monthly and yearly rollups across income, spend, savings, and debt.")

    report_type = st.radio("Report Type", ["Monthly Summary", "Yearly Summary"], horizontal=True)

    if report_type == "Monthly Summary":
        with _section_card(f"Monthly Summary — {MONTHS[sel_month]} {sel_year}"):

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
        with _section_card("Budget Summary Table"):
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
            with _section_card(
                "💡 Surplus Allocation Suggestions",
                f"You have a surplus of ${net:,.2f} this month. Adjust the sliders to model different splits.",
            ):

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
                        _notify("info", hint)

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
            with _section_card("💳 Debt Overview", "Debt balances are shown for reference and are not included in net calculation."):
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
        with _section_card(f"Yearly Summary — {sel_year}"):

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
            with _section_card("💳 Debt Overview", "Debt balances are shown for reference and are not included in net calculation."):
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


# ===========================================================================
# PAGE: AI INSIGHTS
# ===========================================================================
elif page == "🤖 AI Insights":
    _page_header(
        "🤖 AI Insights",
        "Powered by OpenAI GPT-4o-mini. Only aggregated summary data is sent, never raw transaction descriptions.",
    )

    ai_available = ai.is_ai_available()

    if not ai_available:
        _notify("warning", 
            "OpenAI API key not configured. Enter your key in the **🤖 AI Settings** panel in the sidebar to enable AI features."
        )
        _notify("info", 
            "You can still use **Anomaly Detection** below — it runs locally without any API calls."
        )

    # --- gather data for the selected period --------------------------------
    ai_income_rows = db.get_income(year=sel_year, month=sel_month)
    ai_var_rows = db.get_variable_expenses(year=sel_year, month=sel_month)
    ai_fixed_cost = db.get_monthly_fixed_cost(sel_year, sel_month)
    ai_goals = db.get_financial_goals()
    ai_savings_balances = db.get_all_savings_balances()
    ai_total_savings = sum(ai_savings_balances.values())
    ai_total_debt = db.get_total_debt()

    ai_total_income = sum(r["amount"] for r in ai_income_rows)
    ai_total_variable = sum(r["amount"] for r in ai_var_rows)
    ai_net = ai_total_income - ai_fixed_cost - ai_total_variable

    ai_cat_breakdown: dict[str, float] = {}
    for r in ai_var_rows:
        ai_cat_breakdown[r["category"]] = ai_cat_breakdown.get(r["category"], 0.0) + r["amount"]

    # Previous month variable expenses for comparison
    prev_month = sel_month - 1 if sel_month > 1 else 12
    prev_year = sel_year if sel_month > 1 else sel_year - 1
    prev_var_rows = db.get_variable_expenses(year=prev_year, month=prev_month)
    prev_variable = sum(r["amount"] for r in prev_var_rows) if prev_var_rows else None

    financial_context = {
        "month": sel_month,
        "year": sel_year,
        "total_income": ai_total_income,
        "fixed_cost": ai_fixed_cost,
        "variable_cost": ai_total_variable,
        "net": ai_net,
        "category_breakdown": ai_cat_breakdown,
        "total_savings": ai_total_savings,
        "total_debt": ai_total_debt,
    }

    # -------------------------------------------------------------------------
    # Tabs: Insights, weekly brief, anomaly detection, scenario planner, chat
    # -------------------------------------------------------------------------
    tab_insights, tab_weekly, tab_anomalies, tab_scenario, tab_chat = st.tabs(
        [
            "📊 Spending Insights",
            "🗓 Weekly Brief",
            "⚠️ Anomaly Detection",
            "🧪 Scenario Planner",
            "💬 Chat Advisor",
        ]
    )

    # ----- TAB: SPENDING INSIGHTS -------------------------------------------
    with tab_insights:
        with _section_card(f"Spending Insights — {MONTHS[sel_month]} {sel_year}"):

            col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)
            with col_kpi1:
                st.metric("Income", f"${ai_total_income:,.2f}")
            with col_kpi2:
                st.metric("Fixed", f"${ai_fixed_cost:,.2f}")
            with col_kpi3:
                st.metric("Variable", f"${ai_total_variable:,.2f}")
            with col_kpi4:
                st.metric("Net", f"${ai_net:,.2f}", delta=f"${ai_net:+,.2f}", delta_color="normal" if ai_net >= 0 else "inverse")

            if prev_variable is not None and ai_total_variable > 0:
                delta_var = ai_total_variable - prev_variable
                pct = (delta_var / prev_variable * 100) if prev_variable > 0 else 0
                direction = "up" if delta_var > 0 else "down"
                st.caption(
                    f"Variable spending is **{direction} {abs(pct):.1f}%** vs {MONTHS[prev_month]} {prev_year} "
                    f"(${prev_variable:,.2f} → ${ai_total_variable:,.2f})"
                )

        if ai_available:
            if not ai_total_income and not ai_var_rows and not ai_fixed_cost:
                _notify("info", f"No financial data recorded for {MONTHS[sel_month]} {sel_year}. Add some income and expenses first.")
            else:
                cache_key = f"ai_insights_{sel_year}_{sel_month}"
                if st.button("✨ Generate AI Insights", type="primary"):
                    with st.spinner("Analysing your finances…"):
                        insight_text = ai.generate_insights(
                            month=sel_month,
                            year=sel_year,
                            total_income=ai_total_income,
                            fixed_cost=ai_fixed_cost,
                            variable_cost=ai_total_variable,
                            category_breakdown=ai_cat_breakdown,
                            total_savings=ai_total_savings,
                            total_debt=ai_total_debt,
                            goals=ai_goals,
                            prev_month_variable=prev_variable,
                        )
                        st.session_state[cache_key] = insight_text

                if cache_key in st.session_state:
                    with st.container(border=True):
                        st.markdown(st.session_state[cache_key])
                    st.caption("*Generated by GPT-4o-mini. This is informational only, not financial advice.*")
        else:
            _notify("info", "Configure your OpenAI API key in the sidebar to generate AI insights.")

    # ----- TAB: WEEKLY BRIEF ------------------------------------------------
    with tab_weekly:
        with _section_card("🗓 Weekly Financial Brief", "A concise weekly digest with actions and momentum."):
            if not ai_available:
                _notify("info", "Configure your OpenAI API key in the sidebar to generate weekly briefs.")
            else:
                weekly_events = []
                if prev_variable is not None:
                    delta_var = ai_total_variable - prev_variable
                    weekly_events.append(
                        {
                            "label": "Variable spending change vs previous month",
                            "value": f"${delta_var:+,.2f}",
                        }
                    )
                weekly_events.append(
                    {
                        "label": "Current net",
                        "value": f"${ai_net:,.2f}",
                    }
                )

                if st.button("Generate Weekly Brief", key="generate_weekly_brief"):
                    with st.spinner("Writing your weekly brief..."):
                        weekly_text = ai.generate_weekly_brief(financial_context, recent_events=weekly_events)
                        st.session_state[f"weekly_brief_{sel_year}_{sel_month}"] = weekly_text

                cache_key_week = f"weekly_brief_{sel_year}_{sel_month}"
                if cache_key_week in st.session_state:
                    st.markdown(st.session_state[cache_key_week])

    # ----- TAB: ANOMALY DETECTION -------------------------------------------
    with tab_anomalies:
        with _section_card(
            "⚠️ Anomaly Detection",
            "Runs entirely locally with no API calls. Flags category spend outliers using standard deviation.",
        ):

            # Use last 12 months for a meaningful sample
            all_recent_var: list[dict] = []
            for m_offset in range(12):
                m = (sel_month - 1 - m_offset) % 12 + 1
                y = sel_year if sel_month - m_offset > 0 else sel_year - 1
                all_recent_var.extend(db.get_variable_expenses(year=y, month=m))

            threshold = st.slider(
                "Sensitivity (standard deviations above average to flag)",
                min_value=1.0, max_value=4.0, value=2.0, step=0.5,
                help="Lower = more sensitive (more flags). Higher = only extreme outliers.",
            )

            anomalies = ai.detect_anomalies(all_recent_var, threshold_stdev=float(threshold))

            if anomalies:
                _notify("warning", f"Found **{len(anomalies)}** unusual transaction(s) in the last 12 months:")
                for a in anomalies:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([2, 1, 1])
                        with c1:
                            st.markdown(f"**{a['date']}** — {a['category']}")
                            if a["description"]:
                                st.caption(a["description"])
                        with c2:
                            st.metric("Amount", f"${a['amount']:,.2f}")
                        with c3:
                            st.metric("Avg for Category", f"${a['avg_for_category']:,.2f}")
                        st.caption(f"This is **{a['z_score']:.1f}×** standard deviations above your average {a['category']} spend.")
            else:
                _notify("success", "✅ No unusual transactions detected in the last 12 months at the current sensitivity level.")

    # ----- TAB: SCENARIO PLANNER -------------------------------------------
    with tab_scenario:
        with _section_card("🧪 What-If Scenario Planner", "Model lifestyle or income/expense changes before committing."):
            if not ai_available:
                _notify("info", "Configure your OpenAI API key in the sidebar to run scenarios.")
            else:
                scenario_input = st.text_area(
                    "Scenario",
                    value="What if we reduce takeout by $120/month and add an extra $150/month to debt payments?",
                    height=100,
                )
                if st.button("Run Scenario", key="run_ai_scenario"):
                    with st.spinner("Simulating scenario..."):
                        scenario_text = ai.run_scenario_plan(financial_context, scenario_input)
                        st.session_state[f"scenario_plan_{sel_year}_{sel_month}"] = scenario_text

                cache_key_scn = f"scenario_plan_{sel_year}_{sel_month}"
                if cache_key_scn in st.session_state:
                    st.markdown(st.session_state[cache_key_scn])

    # ----- TAB: CHAT ADVISOR ------------------------------------------------
    with tab_chat:
        with _section_card("💬 Chat with Your Financial Advisor", f"Ask anything about your finances for {MONTHS[sel_month]} {sel_year}."):

            chat_history: list[dict] = st.session_state.get("ai_chat_history", [])

            if not ai_available:
                _notify("info", "Configure your OpenAI API key in the sidebar to use the Chat Advisor.")
            else:
                # Initialise conversation history in session state
                if "ai_chat_history" not in st.session_state:
                    st.session_state["ai_chat_history"] = []

                chat_history = st.session_state["ai_chat_history"]

                # Display conversation
                for turn in chat_history:
                    with st.chat_message(turn["role"]):
                        st.markdown(turn["content"])

                # Input
                user_input = st.chat_input("Ask a question, e.g. 'Am I overspending on food?' or 'How can I save more?'")
                if user_input:
                    chat_history.append({"role": "user", "content": user_input})
                    with st.chat_message("user"):
                        st.markdown(user_input)

                    with st.chat_message("assistant"):
                        with st.spinner("Thinking…"):
                            reply = ai.chat_with_advisor(user_input, chat_history[:-1], financial_context)
                        st.markdown(reply)

                    chat_history.append({"role": "assistant", "content": reply})
                    st.session_state["ai_chat_history"] = chat_history

            if chat_history:
                if st.button("🗑 Clear conversation", key="clear_chat"):
                    st.session_state["ai_chat_history"] = []
                    st.rerun()
