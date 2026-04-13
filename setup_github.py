"""
setup_github.py — One-time script to connect this repo to YOUR GitHub account.

Run this ONCE after creating a new empty repo on GitHub:

    python setup_github.py

It will:
    1. Ask for your GitHub username and new repo name
    3. Set your new repo as 'origin'
    5. Do the first push of all your code + data

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
print()
print("Have you already created an EMPTY repo on GitHub? (y/n): ", end="")
if input().strip().lower() != "y":
    print()
    print("Please create an empty repo on GitHub first, then rerun this script.")
    print("Steps:")
    print("  1. Go to https://github.com/new")
    print("  2. Enter a repo name (e.g. 'partha-personal')")
    print("  3. Set visibility (Public or Private)")
    print("  4. Do NOT add README, .gitignore, or license")
    print("  5. Click 'Create repository'")
    print("  6. Rerun:  python setup_github.py")
    sys.exit(0)

print()
print("Enter your GitHub username: ", end="")
username = input().strip()

print("Enter your new repo name (e.g. eod2-personal): ", end="")
repo_name = input().strip()

new_url = f"https://github.com/{username}/{repo_name}.git"

print()
print(f"Your repo URL will be: {new_url}")
print("Confirm? (y/n): ", end="")
if input().strip().lower() != "y":
    print("Aborted.")
    sys.exit(0)

print()
# print("[1/5] Removing stale submodule cache ...")
# git("rm", "--cached", "src/eod2_data", check=False)  # ignore if not present

print("\n[2/5] Setting your repo as 'origin' ...")
git("remote", "set-url", "origin", new_url, check=False)
# If set-url fails (no origin yet), add it
result = subprocess.run(
    ["git", "remote", "get-url", "origin"],
    cwd=ROOT, capture_output=True, text=True
)
if result.returncode != 0:
    git("remote", "add", "origin", new_url)

print("\n[3/5] Keeping BennyThadikaran/eod2 as 'upstream' ...")
git("remote", "remove", "upstream", check=False)  # remove if exists
# git("remote", "add", "upstream", upstream_url)

print("\n[4/5] Staging all files for first commit ...")
git("add", "--all")

# Check if there's anything to commit
result = subprocess.run(
    ["git", "diff", "--cached", "--stat"],
    cwd=ROOT, capture_output=True, text=True
)
if not result.stdout.strip():
    print("Nothing new to stage — already committed.")
else:
    print("\n[4/5] Creating initial commit ...")
    git("commit", "-m", "Initial commit: EOD2 with personal customisations")

print("\n[5/5] Pushing to GitHub (this may take a while for the data files) ...")
git("push", "-u", "origin", "main")

print()
print("=" * 60)
print("Setup complete!")
print()
print(f"  Your repo : {new_url}")
# print(f"  Upstream  : {upstream_url}")
print()
print("Daily evening workflow:")
print("  python push_update.py    (or double-click push_update.bat)")
print()
print("To pull future fixes from the original EOD2 project:")
print("  git fetch upstream")
print("  git merge upstream/main")
print("=" * 60)
