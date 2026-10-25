# University Email Notifier

A Windows tray app that watches a Gmail inbox for university emails and uses an LLM to decide which ones actually matter — cancelled lectures, rescheduled exams, changed deadlines — then pops a desktop notification. Everything else (newsletters, events, routine updates) is silently ignored.

## How it works

```
Gmail (IMAP, read-only)  →  domain allowlist  →  Claude Haiku classifier  →  Windows toast
        every 5 min            bgu.ac.il only       IMPORTANT / NOT_IMPORTANT    click → inbox
```

1. **Fetch** — every 5 minutes, pulls up to 20 unread emails over IMAP using `BODY.PEEK`, so nothing is marked as read. Handles multipart, HTML-only, and Hebrew (windows-1255) encodings. HTML is preferred over the plain-text alternative (it's what the reader actually sees), and text hidden from the reader — `display:none`, hidden CSS classes, off-screen positioning, tiny or white text — is dropped before anything reaches the model.
2. **Filter** — only senders on an allowlist of university domains (including subdomains) reach the model; already-seen message IDs are skipped.
3. **Classify** — the subject and a 500-character preview go to Claude Haiku inside `<email>` delimiters, with a system prompt that treats the email as untrusted data and forces a strict output format:
   ```
   IMPORTANT
   course: <course name or "General">
   change: cancelled / postponed / rescheduled / deadline changed / exam update / emergency / other
   details: <new time, location, or deadline — or N/A>
   ```
   The output is validated: only these three fields are kept, `change` must come from the allowed set, lengths are capped, and links, email addresses and phone numbers (including spelled-out and look-alike forms) are stripped. A reply with no label line is treated as not important.
4. **Notify** — important emails become a Windows toast (`Algorithms — Postponed`, with the new time) that opens the inbox when clicked.

Runs in the system tray with a single-instance lock and an optional "start with Windows" toggle (registry Run key, no admin rights).

## Prompt-injection red team

Every email body is attacker-controlled text fed to an LLM, so the classifier was attacked directly. Threat model: someone who can email the inbox from an allowlisted domain wants to **suppress** a real alert, **fake** an alert, or **inject** their own text (a phishing link or phone number) into the toast.

`tests/injection_cases.json` holds 44 attacks in Hebrew, English and mixed — direct instructions, fake system messages, fake conversations, fake output blocks, role-play, base64, hidden HTML, subject-line injection, delimiter escapes, many-shot examples, obfuscated links — plus 6 benign controls. `tests/run_injection.py` sends each through the real extraction and classification path, 3 runs per case (Claude Haiku 4.5), and also checks offline what text reaches the model.

| | Before | After |
|---|---|---|
| Round 1 — 30 attacks, 90 runs | 9/90 succeeded (10%) | 0/90 |
| Round 2 — 14 attacks written against the round-1 defenses, 42 runs | 6/42 succeeded (14%); hidden text reached the model in 5/9 extraction checks | 0/42; 9/9 |
| Controls (benign emails classified correctly) | 18/18 | 18/18 |

What actually broke, and the fix:

- **Chatty replies dropped real alerts.** A fake transcript in the body made the model correctly answer `IMPORTANT` — after a paragraph of commentary. The parser only read line 1, so the alert was lost. Fix: find the label line anywhere; the prompt forbids commentary.
- **Hidden HTML reached the model.** Tag-stripping kept `display:none` text, so an invisible instruction put a phishing link in the toast. Fix: a visibility-aware HTML parser. Round 2 then found CSS-class hiding, off-screen text, and an unclosed tag that silently wiped the whole body; all fixed.
- **The plain-text part can lie.** In `multipart/alternative` mail the client shows the HTML, but the code preferred the unseen plain part — 6/6 success for both suppressing and faking alerts. Fix: prefer HTML.
- **Links and phone numbers in the toast.** Fix: strict output validation. Obfuscated forms (`dot net`, `。`, odd digit grouping) were only stopped by the model obeying the prompt, so the sanitizer now catches them as a second layer.

Caveats: a small, self-written attack set against one model; 0% here means these attacks fail, not that the pipeline is injection-proof. The sanitizer can over-strip dotted names like `Node.js`.

Run it: `py tests/run_injection.py --runs 3` (options: `--model`, `--only S1,A3`). Raw replies are saved to `tests/results/` (gitignored).

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
| `setup_autostart.py` | One-off: register the app to start at login (same as the tray menu option) |
| `tests/run_tests.py` | End-to-end checks (IMAP, allowlist, persistence, live classification); run with `python tests/run_tests.py` |
| `tests/injection_cases.json` | Prompt-injection attack set and benign controls |
| `tests/run_injection.py` | Red-team runner: attack success rate per goal and technique |
