"""
Codifies the "secrets drill (repo half)" PROGRESS.md already describes
doing by hand (`git grep` across the tracked repo for key-shaped strings,
confirm .env is untracked). Two checks:

  1. .env is not tracked by git (staged, committed, or in history).
  2. No tracked, non-binary file contains a key-shaped assignment for any
     of the secret names in .env.example.

This only covers the repo half. The other half PROGRESS.md calls out --
confirming no key leaks into a deployed Streamlit page's source -- needs a
running deploy and isn't something a static script can check; run that
manually against the live URL before judging, the way the checklist says.

Exit code 0 and a clean report on success; exit code 1 and the offending
file/line on failure, so this is safe to wire into a pre-commit hook or CI
later without anyone having to read output to know whether it passed.
"""

from __future__ import annotations

import re
import subprocess
import sys

# Names pulled from .env.example, not hardcoded independently, so this
# script and that file can't silently drift apart.
_ENV_EXAMPLE_PATH = ".env.example"

_KEY_SHAPED_VALUE = re.compile(r"""^[A-Za-z0-9_\-/+]{16,}={0,2}$""")


def _tracked_secret_names() -> list[str]:
    names = []
    with open(_ENV_EXAMPLE_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                names.append(line.split("=", 1)[0])
    return names


def check_env_untracked() -> tuple[bool, str]:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".env"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return False, ".env IS tracked by git -- remove it from the index immediately (git rm --cached .env)"

    result = subprocess.run(
        ["git", "log", "--all", "--", ".env"],
        capture_output=True, text=True,
    )
    if result.stdout.strip():
        return False, ".env appears in git history even though it isn't in the current tree -- history rewrite needed"

    return True, ".env confirmed untracked (not in index, not in history)"


def check_no_hardcoded_keys() -> tuple[bool, list[str]]:
    names = _tracked_secret_names()
    result = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
    tracked_files = [f for f in result.stdout.splitlines() if f]

    findings = []
    for path in tracked_files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue  # binary or gone (e.g. a submodule entry) -- not a plaintext-secret risk
        for lineno, line in enumerate(lines, start=1):
            for name in names:
                if name in line and "=" in line:
                    # crude but deliberate: flag `NAME=<something key-shaped>`,
                    # not `NAME=your_..._here` (the placeholder pattern used
                    # throughout .env.example) or a bare mention in a comment.
                    rhs = line.split("=", 1)[1].strip().strip('"\'')
                    if _KEY_SHAPED_VALUE.match(rhs) and "your_" not in rhs and "_here" not in rhs:
                        findings.append(f"{path}:{lineno}: looks like a real value for {name}")
    return len(findings) == 0, findings


if __name__ == "__main__":
    ok_env, msg_env = check_env_untracked()
    print(("PASS: " if ok_env else "FAIL: ") + msg_env)

    ok_keys, findings = check_no_hardcoded_keys()
    if ok_keys:
        print("PASS: no key-shaped hardcoded values found in tracked files")
    else:
        print("FAIL: possible hardcoded secret(s):")
        for f in findings:
            print(f"  {f}")

    if not (ok_env and ok_keys):
        sys.exit(1)
    print("\nSecurity preflight PASSED (repo half only -- see module docstring for what this does not cover).")
