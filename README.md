# 💸 Budgeting Bot

A Streamlit web app for tracking income, fixed expenses, variable expenses, financial goals, and monthly/yearly budgets.

## Features

| Feature | Details |
|---------|---------|
| 📊 Dashboard | Monthly KPIs — income, fixed costs, variable costs, net balance |
| 💰 Income | Add & categorise one-off or recurring income entries |
| 📌 Fixed Expenses | Manage recurring fixed costs (rent, subscriptions, loans) by month or year |
| 🛒 Variable Expenses | Log ad-hoc spending with category breakdowns |
| 🎯 Financial Goals | Set savings targets, track progress with progress bars |
| 📈 Reports | Monthly pie/bar charts and yearly trend lines |

All data is stored in a local SQLite database (`budget.db`).

---

## Running Locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app opens at <http://localhost:8501>.

---

## Deploy on Railway

1. Push this repo to GitHub.
2. Create a new project in [Railway](https://railway.app) and connect the repo.
3. Railway detects `railway.toml` and runs:
   ```
   streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
   ```
4. Add a **Volume** (or use Railway's persistent storage) mounted at `/app` and set `DB_PATH=/app/budget.db` in environment variables so the SQLite database survives redeploys.

---

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub.
2. Go to <https://share.streamlit.io> → **New app** → select this repo.
3. Set **Main file path** to `app.py`.
4. Click **Deploy**.

> **Note:** Streamlit Community Cloud does not persist files between restarts. For persistent storage, consider Railway (with a volume) or a hosted database.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `budget.db` | Path to the SQLite database file |
| `PORT` | `8501` | Port for Railway / Heroku (set automatically) |
| `BUDGETBOT_USERNAME` | _(required)_ | Login username |
| `BUDGETBOT_PASSWORD_SALT` | _(required)_ | Hex-encoded random salt for password hashing |
| `BUDGETBOT_PASSWORD_HASH` | _(required)_ | Hex-encoded PBKDF2-SHA256 password hash |
| `BUDGETBOT_SESSION_TIMEOUT_MINUTES` | `30` | Session timeout after inactivity |

### Configure Login Credentials

The app now requires login before any budgeting data is shown. Configure these variables in your environment (or Streamlit secrets) before running/deploying.

Generate a secure salt + hash pair:

```bash
python - <<'PY'
import hashlib, os
password = input('Enter a strong password: ').encode()
salt = os.urandom(16)
pwd_hash = hashlib.pbkdf2_hmac('sha256', password, salt, 200000)
print('BUDGETBOT_PASSWORD_SALT=' + salt.hex())
print('BUDGETBOT_PASSWORD_HASH=' + pwd_hash.hex())
PY
```

Then set:

```bash
export BUDGETBOT_USERNAME="your-username"
export BUDGETBOT_PASSWORD_SALT="<hex from script>"
export BUDGETBOT_PASSWORD_HASH="<hex from script>"
export BUDGETBOT_SESSION_TIMEOUT_MINUTES="30"
```
