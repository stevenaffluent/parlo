"""Updates from the Parlo GitHub repository.

A copy installed with "Install Parlo.bat" is a git clone. Parlo fetches origin/stable now and then
(the branch that only ever points at a tested release; day-to-day work on main reaches nobody).
When stable has new commits it offers to update, which is a fast-forward pull, a library install if
requirements.txt changed, and a restart. Settings, history, notes and models are not in the
repository, so an update never touches them. A copy with its own edits or commits (a developer's)
is never updated automatically: it would mean merging, so Parlo says why and leaves it alone.
"""
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("parlo.update")
ROOT = Path(__file__).resolve().parent.parent
BRANCH = "stable"  # moved only when a release has been tested (README, "Publishing a release")
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW: no console flashes up for each git call


def _git_exe():
    found = shutil.which("git")
    if found:
        return found
    for p in (r"C:\Program Files\Git\cmd\git.exe", os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe")):
        if Path(p).exists():
            return p
    return None


def _git(*args, timeout=60):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")  # never pop up a sign-in in the background
    r = subprocess.run([_git_exe(), *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, env=env, creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip()
                           else f"git {args[0]} failed")
    return r.stdout.strip()


def supported():
    return bool(_git_exe()) and (ROOT / ".git").exists()


def check():
    """{"supported", "available", "behind", "changes": [commit subjects], "blocked": reason or "", "error"}"""
    if not supported():
        return {"supported": False, "available": False}
    try:
        _git("fetch", "--quiet", "origin", BRANCH, timeout=90)
        behind = int(_git("rev-list", "--count", f"HEAD..origin/{BRANCH}"))
        ahead = int(_git("rev-list", "--count", f"origin/{BRANCH}..HEAD"))
        dirty = [l for l in _git("status", "--porcelain", "--untracked-files=no").splitlines() if l.strip()]
        changes = _git("log", "--format=%s", f"HEAD..origin/{BRANCH}").splitlines()[:12] if behind else []
    except Exception as e:  # offline, signed out, or GitHub unreachable: try again later
        log.info("update check failed: %s", e)
        return {"supported": True, "available": False, "error": str(e)}
    blocked = ""
    if behind and (ahead or dirty):
        blocked = ("This copy of Parlo has its own changes" + (" (edited files)" if dirty else " (local commits)") +
                   ", so it can't be updated automatically. Use git to merge the update.")
    return {"supported": True, "available": behind > 0, "behind": behind, "changes": changes, "blocked": blocked}


def apply():
    """Fast-forward to origin/stable and install new libraries if needed. Returns None or an error message."""
    st = check()
    if not st.get("available"):
        return st.get("error") or "Parlo is already up to date."
    if st.get("blocked"):
        return st["blocked"]
    try:
        old = _git("rev-parse", "HEAD")
        _git("merge", "--ff-only", f"origin/{BRANCH}")
        changed = _git("diff", "--name-only", old, "HEAD").splitlines()
        log.info("updated %s -> %s (%d files)", old[:7], _git("rev-parse", "--short", "HEAD"), len(changed))
    except Exception as e:
        log.exception("update failed")
        return f"The update failed: {e}"
    if "requirements.txt" in changed:
        python = ROOT / ".venv" / "Scripts" / "python.exe"
        r = subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r",
                            str(ROOT / "requirements.txt")], cwd=ROOT, capture_output=True, text=True,
                           creationflags=NO_WINDOW)
        if r.returncode != 0:
            log.error("pip after update failed: %s", r.stderr[-2000:])
            return "Parlo was updated, but installing its new libraries failed. Run Setup.bat to finish."
    return None


def restart():
    """Start a fresh Parlo that waits for this one to exit (so the single-instance check passes)."""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(pythonw), str(ROOT / "app" / "main.py"), "--wait-pid", str(os.getpid()), "--updated"],
                     cwd=ROOT, creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | NEW_PROCESS_GROUP
