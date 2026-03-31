# Task tracker (Streamlit)

A simple Streamlit app to manage tasks, statuses, and general notes (with tags), backed by SQLite.

## Features

- **Login required** (credentials come from Streamlit secrets)
- **Tasks**
  - Fields: Title, Description, Status, Due date, Priority (integer)
  - **Sorted by Priority** (lower number first), then recency (as stored in the DB query)
  - View tasks as **cards** filtered by a selected status
  - Open task details in a modal and update status/priority/due date + comments
- **Statuses**
  - Manage statuses via a **popup dialog** (add/rename/delete)
  - Deleting a status is blocked if tasks still use it
- **General notes**
  - Notes are shown newest-first
  - Tag notes, create/delete tags in a **popup dialog**
  - Filter notes by tag

## Local setup

### 1) Create a virtual environment

```bash
cd my_tasks
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure login credentials (required)

Create the secrets file:

```bash
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml` and set your own credentials:

```toml
[auth]
username = "your_username"
password = "your_strong_password"
```

Important:
- **Do not commit** `.streamlit/secrets.toml` (it is ignored by `.gitignore`).
- Use a **strong** password. Anyone with these credentials can access the app.

### 3) Run the app

```bash
streamlit run app.py
```

## Data / database

- The app uses a local SQLite file: `tasks.db`
- It is created automatically on first run (via `db.init_db()`).
- `tasks.db` is intentionally **not committed** (ignored in `.gitignore`).

## Deployment to Streamlit Community Cloud

### 1) Push your repo to GitHub

Your repository must be accessible to Streamlit Cloud (public repo, or a connected GitHub account with access).

### 2) Create the app in Streamlit Cloud

1. Go to Streamlit Community Cloud and create a new app.
2. Select:
   - **Repository**: your GitHub repo (e.g. `sergioeval/myTasksApp`)
   - **Branch**: `main`
   - **Main file path**: `app.py`

### 3) Add secrets (credentials) in Streamlit Cloud

In the app settings, open **Secrets** and add:

```toml
[auth]
username = "your_username"
password = "your_strong_password"
```

This is required because the app blocks access until a user logs in.

### 4) Deploy

Save the secrets and deploy. Streamlit Cloud will install dependencies from `requirements.txt` automatically.

### Notes about persistence on Streamlit Cloud

This app uses SQLite (`tasks.db`). On Streamlit Cloud, the filesystem is **ephemeral**, so your database may reset when the app restarts/redeploys.

If you need persistent storage, typical options are:
- Postgres / MySQL (managed DB)
- Hosted SQLite solution
- A managed service (Supabase, Neon, etc.)

## Troubleshooting

- **Login screen says “Authentication is not configured”**:
  - Local: ensure `.streamlit/secrets.toml` exists and has an `[auth]` block.
  - Cloud: ensure the same `[auth]` block is present in Streamlit Cloud Secrets.

