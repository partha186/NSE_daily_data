# GitHub Setup & Daily Workflow

## One-Time Setup

### Step 1 — Create a new empty repo on GitHub



### Step 2 — Configure Git credentials (if not done already)

```bash
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
```

If you use HTTPS (password/token), store credentials so you don't get prompted every push:

```bash
git config --global credential.helper store
```

The first push will ask for your GitHub username and a **Personal Access Token** (not your password).
To create a token: GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token. Tick `repo` scope.

---

### Step 3 — Run the one-time setup script

```bash
cd d:\partha_python\NSE_EOD_data
python setup_github.py
```

The script will:
- Ask for your GitHub username and repo name
- Point `origin` to **your** new repo
- Keep `BennyThadikaran/eod2` as `upstream` (for pulling future bug fixes)
- Do the first push of all code + data

This first push may take a few minutes because it includes all the stock CSV files in `src/NSE_eod_data/`.

---

## Daily Evening Workflow (after 7 PM)

### Option A — Double-click (Windows)

Double-click `push_update.bat` in the project folder.

### Option B — Command line

```bash
cd d:\partha_python\NSE_EOD_data
python push_update.py
```

### What it does automatically

1. Runs `src/init.py` — downloads today's NSE data into `src/NSE_eod_data/`
2. Stages all changed files (`git add --all`)
3. Commits with the message `EOD data update: 2026-04-12 (Sunday)`
4. Pushes to `origin main` on GitHub

---

## Viewing Changes on GitHub

After each evening push, go to:
```
https://github.com/YOURNAME/eod2-personal/commits/main
```

Each commit shows exactly which CSV files changed and how many rows were added.

---

## Pulling Fixes from the Original EOD2 Project

When BennyThadikaran releases improvements to the original `eod2` repo:

```bash
git fetch upstream
git merge upstream/main
```

Resolve any conflicts (your customisations vs upstream changes), then push:

```bash
python push_update.py
```

---

## Automating the Evening Push (Windows Task Scheduler)

To run the update automatically every weekday at 9:30 PM:

1. Open **Task Scheduler** (search in Start menu)
2. Click **Create Basic Task**
3. Name: `EOD2 Daily Update`
4. Trigger: **Daily**, at **7:00 PM**, repeat on weekdays
5. Action: **Start a program**
   - Program: `python`
   - Arguments: `push_update.py`
   - Start in: `d:\partha_python\NSE_EOD_data`
6. Finish

Or use this PowerShell command to create the task:

```powershell
$action = New-ScheduledTaskAction -Execute "python" `
    -Argument "push_update.py" `
    -WorkingDirectory "d:\partha_python\NSE_EOD_data"

$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At 7pm

Register-ScheduledTask -TaskName "EOD2 Daily Update" `
    -Action $action -Trigger $trigger -RunLevel Highest
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `git push` asks for username/password | Use a Personal Access Token as the password, not your GitHub password |
| `remote: Repository not found` | Check the URL: `git remote -v`. Fix with: `git remote set-url origin YOUR_URL` |
| `failed to push — non-fast-forward` | Someone else pushed or you have diverged: `git pull --rebase origin main` then push again |
| `init.py` exits with "delivery data pending" | Normal — NSE hasn't published it yet. It will be retried on the next run |
| Large first push is slow | Normal — first push includes all historical CSV data. Subsequent pushes are tiny (one new row per stock per day) |

---

## Repository Structure on GitHub

```
eod2-personal/
├── src/
│   ├── NSE_eod_data/       ← daily updated stock data (committed each evening)
│   ├── funcdefs/           ← core library
│   ├── init.py, plot.py, data_get.py, ...
├── push_update.py          ← evening workflow script
├── push_update.bat         ← Windows convenience wrapper
├── setup_github.py         ← this one-time setup script
├── pyproject.toml
└── README.md
```
