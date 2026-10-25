import json
import re
import time
import logging
import sys
import os
import threading
import ctypes
import winreg
from pathlib import Path

import anthropic
import pystray
from PIL import Image, ImageDraw
from dotenv import load_dotenv

from config import POLL_INTERVAL_SECONDS, SEEN_IDS_FILE, ALLOWED_DOMAINS
from checker import fetch_unread_emails
from analyzer import is_important
from notifier import send_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("email_notifier.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

_stop_event = threading.Event()
TASK_NAME = "UniversityEmailNotifier"
_autostart_cache: bool | None = None  # cached so menu renders don't spawn subprocesses
_mutex_handle = None  # kept alive for the process lifetime to enforce single instance


# ── Icon ──────────────────────────────────────────────────────────────────────

def _create_icon_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([0, 0, 63, 63], fill=(30, 100, 210))          # blue circle
    draw.rectangle([12, 22, 52, 44], fill=(255, 255, 255))     # envelope body
    draw.polygon([(12, 22), (32, 36), (52, 22)], fill=(190, 215, 245))  # flap
    return img


# ── Autostart (Registry Run key — no admin rights required) ───────────────────

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _refresh_autostart_cache() -> None:
    global _autostart_cache
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, TASK_NAME)
            _autostart_cache = True
    except FileNotFoundError:
        _autostart_cache = False
    log.info(f"Autostart state on startup: {'enabled' if _autostart_cache else 'disabled'}")


def _is_autostart_enabled() -> bool:
    return bool(_autostart_cache)


def _enable_autostart() -> None:
    python_dir = Path(sys.executable).parent
    pythonw = python_dir / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    script = Path(__file__).absolute()
    value = f'"{pythonw}" "{script}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, TASK_NAME, 0, winreg.REG_SZ, value)


def _disable_autostart() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, TASK_NAME)
    except FileNotFoundError:
        pass


def _toggle_autostart(icon, item) -> None:
    global _autostart_cache
    if _is_autostart_enabled():
        _disable_autostart()
        _autostart_cache = False
        log.info("Auto-start disabled.")
    else:
        _enable_autostart()
        _autostart_cache = True
        log.info("Auto-start enabled.")
    icon.update_menu()


# ── Email state ───────────────────────────────────────────────────────────────

def load_seen_ids() -> set[str]:
    path = Path(SEEN_IDS_FILE)
    if not path.exists():
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return set(str(uid) for uid in json.load(f))
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"Could not load {SEEN_IDS_FILE}: {e}. Starting fresh.")
        return set()


def save_seen_ids(seen_ids: set[str]) -> None:
    try:
        with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(seen_ids, key=lambda x: int(x) if x.isdigit() else x), f, indent=2)
    except OSError as e:
        log.error(f"Could not save {SEEN_IDS_FILE}: {e}")


def _sender_allowed(from_header: str) -> bool:
    if not ALLOWED_DOMAINS:
        return True
    match = re.search(r"@([\w.-]+)", from_header)
    if not match:
        return True
    domain = match.group(1).lower()
    return any(domain == d or domain.endswith("." + d) for d in ALLOWED_DOMAINS)


# ── Poll cycle ────────────────────────────────────────────────────────────────

def poll_once(
    imap_user: str,
    imap_pass: str,
    claude_client: anthropic.Anthropic,
    seen_ids: set[str],
    inbox_url: str,
) -> set[str]:
    log.info("Polling for unread emails...")

    try:
        emails = fetch_unread_emails(imap_user, imap_pass)
    except Exception as e:
        log.error(f"IMAP fetch failed: {e}")
        return seen_ids

    log.info(f"Found {len(emails)} unread email(s).")
    new_ids: set[str] = set()

    for mail in emails:
        uid = mail["uid"]

        if uid in seen_ids:
            continue

        if not _sender_allowed(mail["from"]):
            log.info(f"Skipping UID {uid} — domain not allowed: {mail['from'][:60]}")
            new_ids.add(uid)
            continue

        log.info(f"Analyzing UID {uid}: {mail['subject'][:60]}")

        try:
            important, info = is_important(
                subject=mail["subject"],
                body_preview=mail["body_preview"],
                client=claude_client,
            )
        except anthropic.APIError as e:
            log.error(f"Claude API error for UID {uid}: {e}")
            continue
        except Exception as e:
            log.error(f"Unexpected error for UID {uid}: {e}")
            continue

        new_ids.add(uid)

        if important:
            log.info(f"IMPORTANT UID {uid}: course={info.get('course')} change={info.get('change')}")
            try:
                send_notification(info=info, sender=mail["from"], inbox_url=inbox_url)
            except Exception as e:
                log.error(f"Notification failed for UID {uid}: {e}")
        else:
            log.info(f"Not important UID {uid}")

    updated = seen_ids | new_ids
    if new_ids:
        save_seen_ids(updated)
    return updated


# ── Background polling thread ─────────────────────────────────────────────────

def _polling_loop(imap_user: str, imap_pass: str, claude_client: anthropic.Anthropic, inbox_url: str) -> None:
    seen_ids = load_seen_ids()
    log.info(f"Polling thread started. Domain filter: {ALLOWED_DOMAINS or 'disabled'}")
    while not _stop_event.is_set():
        try:
            seen_ids = poll_once(imap_user, imap_pass, claude_client, seen_ids, inbox_url)
        except Exception as e:
            log.error(f"Unhandled error in poll loop: {e}")
        _stop_event.wait(POLL_INTERVAL_SECONDS)


# ── Entry point ───────────────────────────────────────────────────────────────

def _ensure_single_instance() -> None:
    """Exit immediately if another instance is already running."""
    global _mutex_handle
    _mutex_handle = ctypes.windll.kernel32.CreateMutexW(None, False, "UniversityEmailNotifier_Mutex")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)


def main() -> None:
    _ensure_single_instance()

    # Anchor all relative paths to the script's directory, not the launch CWD.
    # Without this, Task Scheduler (or any other launcher) can start the process
    # with a different working directory, causing .env / seen_ids.json / log to be lost.
    os.chdir(Path(__file__).parent)

    load_dotenv()

    imap_user = os.environ.get("IMAP_USER")
    imap_pass = os.environ.get("IMAP_PASS")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    missing = [k for k, v in [
        ("IMAP_USER", imap_user),
        ("IMAP_PASS", imap_pass),
        ("ANTHROPIC_API_KEY", anthropic_key),
    ] if not v]

    if missing:
        log.error(f"Missing env vars: {', '.join(missing)}. Fill in .env file.")
        sys.exit(1)

    inbox_url = f"https://mail.google.com/mail/u/{imap_user}/#inbox"
    claude_client = anthropic.Anthropic(api_key=anthropic_key)

    # Start polling in background thread
    thread = threading.Thread(
        target=_polling_loop,
        args=(imap_user, imap_pass, claude_client, inbox_url),
        daemon=True,
    )
    thread.start()

    # Read autostart state once at startup (no subprocess on every menu render)
    _refresh_autostart_cache()

    def _autostart_label(item) -> str:
        return "Disable auto-start at login" if _is_autostart_enabled() else "Enable auto-start at login"

    def on_quit(icon, item):
        _stop_event.set()
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem(_autostart_label, _toggle_autostart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )

    icon = pystray.Icon(
        name="university_email_notifier",
        icon=_create_icon_image(),
        title="University Email Notifier",
        menu=menu,
    )
    icon.run()  # blocks on main thread until Quit is clicked


if __name__ == "__main__":
    main()
