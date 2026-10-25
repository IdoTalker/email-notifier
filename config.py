IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
POLL_INTERVAL_SECONDS = 300

CLAUDE_MODEL = "claude-haiku-4-5"
CLAUDE_MAX_TOKENS = 200

BODY_PREVIEW_CHARS = 500
MAX_EMAILS_PER_POLL = 20

SEEN_IDS_FILE = "seen_ids.json"

APP_NAME = "University Email Notifier"

# Only analyze emails from these domains. Empty list = no filtering.
ALLOWED_DOMAINS = ["bgu.ac.il", "post.bgu.ac.il"]

# Constructed dynamically in main.py using IMAP_USER: mail.google.com/mail/u/{email}/#inbox
