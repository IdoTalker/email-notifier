# University Email Notifier

A Windows tray app that watches a Gmail inbox for university emails and uses an LLM to decide which ones actually matter — cancelled lectures, rescheduled exams, changed deadlines — then pops a desktop notification. Everything else (newsletters, events, routine updates) is silently ignored.

## How it works

```
Gmail (IMAP, read-only)  →  domain allowlist  →  Claude Haiku classifier  →  Windows toast
        every 5 min            bgu.ac.il only       IMPORTANT / NOT_IMPORTANT    click → inbox
```

1. **Fetch** — every 5 minutes, pulls up to 20 unread emails over IMAP using `BODY.PEEK`, so nothing is marked as read. Handles multipart, HTML-only, and Hebrew (windows-1255) encodings.
2. **Filter** — only senders on an allowlist of university domains (including subdomains) reach the model; already-seen message IDs are skipped.
3. **Classify** — the subject and a 500-character preview go to Claude Haiku with a system prompt that forces a strict output format:
   ```
   IMPORTANT
   course: <course name or "General">
   change: cancelled / postponed / rescheduled / deadline changed / exam update / emergency / other
   details: <new time, location, or deadline — or N/A>
   ```
   Anything that doesn't match the format is treated as not important, so malformed model output fails safe. The system prompt is prompt-cached to cut cost and latency.
4. **Notify** — important emails become a Windows toast (`Algorithms — Postponed`, with the new time) that opens the inbox when clicked.

Runs in the system tray with a single-instance lock and an optional "start with Windows" toggle (registry Run key, no admin rights).

## Setup

```
pip install -r requirements.txt
cp .env.example .env    # then fill in your values
python main.py
```

`.env` needs a Gmail address, a [Gmail app password](https://myaccount.google.com/apppasswords), and an Anthropic API key. Edit `ALLOWED_DOMAINS` in `config.py` for your own university.

## Files

| File | Purpose |
|------|---------|
| `main.py` | Tray app, polling loop, allowlist, seen-ID tracking, autostart |
| `checker.py` | IMAP fetch and MIME/encoding handling |
| `analyzer.py` | Claude classification prompt and output parsing |
| `notifier.py` | Windows toast notifications |
| `config.py` | Poll interval, model, allowlist |
| `run_tests.py` | End-to-end checks (IMAP, allowlist, persistence, live classification) |
