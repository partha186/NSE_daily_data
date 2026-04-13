"""
setup_github.py — One-time script to connect this repo to YOUR GitHub account.

Run this ONCE after creating a new empty repo on GitHub:

    python setup_github.py

It will:
    1. Ask for your GitHub username and new repo name
    2. Set your new repo as 'origin'
    3. Stage all files
    4. Create initial commit
    5. Push to GitHub

Prerequisites:
    - Git installed and on PATH
    - GitHub account created
    - New EMPTY repo created on GitHub (no README, no .gitignore)
    - Git credentials configured (gh auth login, or SSH key, or stored password)
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def run(cmd: list, check: bool = True) -> subprocess.CompletedProcess:
    print(f">>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT, text=True)
    if check and result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}.")
        sys.exit(result.returncode)
    return result


def git(*args, check: bool = True):
    return run(["git", *args], check=check)


print("=" * 60)
print("EOD2 — GitHub One-Time Setup")
print("=" * 60)

print("\nHave you already created an EMPTY repo on GitHub? (y/n): ", end="")
if input().strip().lower() != "y":
    print("\nPlease create an empty repo on GitHub first, then rerun this script.")
    print("Steps:")
    print("  1. Go to https://github.com/new")
    print("  2. Enter a repo name (e.g. 'NSE-personal')")
    print("  3. Set visibility (Public or Private)")
    print("  4. Do NOT add README, .gitignore, or license")
    print("  5. Click 'Create repository'")
    print("  6. Rerun:  python setup_github.py")
    sys.exit(0)

print("\nEnter your GitHub username: ", end="")
username = input().strip()

print("Enter your new repo name (e.g. NSE-personal): ", end="")
repo_name = input().strip()

new_url = f"https://github.com/{username}/{repo_name}.git"

print(f"\nYour repo URL will be: {new_url}")
print("Confirm? (y/n): ", end="")
if input().strip().lower() != "y":
    print("Aborted.")
    sys.exit(0)

# ── Step 1: Set remote origin ────────────────────────────────────────────────
print("\n[1/5] Setting remote origin ...")
existing = subprocess.run(
    ["git", "remote", "get-url", "origin"],
    cwd=ROOT, capture_output=True, text=True
)
if existing.returncode == 0:
    git("remote", "set-url", "origin", new_url)
else:
    git("remote", "add", "origin", new_url)

# ── Step 2: Verify remote ────────────────────────────────────────────────────
print("\n[2/5] Verifying remote ...")
git("remote", "-v")

# ── Step 3: Stage all files ──────────────────────────────────────────────────
print("\n[3/5] Staging all files ...")
git("add", "--all")

# ── Step 4: Commit ───────────────────────────────────────────────────────────
print("\n[4/5] Creating initial commit ...")
result = subprocess.run(
    ["git", "diff", "--cached", "--stat"],
    cwd=ROOT, capture_output=True, text=True
)
if not result.stdout.strip():
    print("Nothing new to stage — already committed.")
else:
    git("commit", "-m", "Initial commit: NSE_daily_data with personal customisations")

# ── Step 5: Force push ───────────────────────────────────────────────────────
print("\n[5/5] Pushing to GitHub (this may take a while for large data files) ...")
git("push", "-u", "origin", "main", "--force")

print()
print("=" * 60)
print("Setup complete!")
print(f"\n  Your repo : {new_url}")
print("\nDaily evening workflow:")
print("  python push_update.py    (or double-click push_update.bat)")
print("=" * 60)