"""
push_update.py — Evening EOD2 update and push script.

Run this every evening after 7 PM (after NSE data is published):

    python push_update.py

What it does:
    1. Runs src/init.py to download and sync today's NSE data
    2. Stages all changed/new files
    3. Commits with today's date and a summary of what changed
    4. Pushes to the 'main' branch on GitHub

Requirements:
    - git must be installed and on PATH
    - GitHub remote must be set (run setup_github.py once to configure)
    - Dependencies installed:  pip install -r requirements.txt
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "src"

# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd: list, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a shell command, printing it first. Exits on failure if check=True."""
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=capture,
        text=True,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip() if capture else ""
        print(f"ERROR (exit {result.returncode}): {stderr or 'command failed'}")
        sys.exit(result.returncode)
    return result


def git(*args, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", *args], check=check, capture=capture)


# ── Step 1: Sync NSE data ─────────────────────────────────────────────────────

print("=" * 60)
print("EOD2 Evening Update")
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

print("\n[1/4] Syncing NSE data ...")
run([sys.executable, str(SRC / "init.py")], check=False)
# init.py exits 0 when up to date and exits 0 after sync — we don't fail hard here
# because a missing delivery report is normal and tracked for retry.

# ── Step 2: Stage all changes ─────────────────────────────────────────────────

print("\n[2/4] Staging changes ...")

# Check if there's anything to commit
status = git("status", "--porcelain", capture=True, check=False)
if not status.stdout.strip():
    print("Nothing changed — repository is already up to date.")
    sys.exit(0)

# Stage everything except what .gitignore excludes
git("add", "--all")

# ── Step 3: Build commit message ─────────────────────────────────────────────

today = datetime.now().strftime("%Y-%m-%d")
day_name = datetime.now().strftime("%A")

# Count changed files for a meaningful summary
diff_stat = git("diff", "--cached", "--stat", capture=True).stdout.strip()
changed_files = [
    line for line in diff_stat.splitlines()
    if "file" in line  # summary line: "N files changed …"
]
summary = changed_files[0] if changed_files else "data update"

commit_msg = f"EOD data update: {today} ({day_name})\n\n{summary}"

print(f"\n[3/4] Committing:\n  {commit_msg.splitlines()[0]}")
git("commit", "-m", commit_msg)

# ── Step 4: Push to GitHub ────────────────────────────────────────────────────

print("\n[4/4] Pushing to GitHub ...")
git("push", "origin", "main")

print("\n" + "=" * 60)
print(f"Done! Pushed at {datetime.now().strftime('%H:%M:%S')}")
print("=" * 60)
