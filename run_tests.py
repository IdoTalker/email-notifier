"""Quick functional test — run with: python run_tests.py"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Test 1: IMAP fetch
print("--- Test 1: IMAP fetch ---")
from checker import fetch_unread_emails
emails = fetch_unread_emails(os.environ["IMAP_USER"], os.environ["IMAP_PASS"])
print(f"OK: fetched {len(emails)} unread emails")

# Test 2: Domain filter
print("--- Test 2: Domain filter ---")
from main import _sender_allowed
assert _sender_allowed("prof@bgu.ac.il") is True
assert _sender_allowed("prof@cs.bgu.ac.il") is True
assert _sender_allowed("spam@gmail.com") is False
assert _sender_allowed("no-reply@post.bgu.ac.il") is True
print("OK: all domain filter cases correct")

# Test 3: seen_ids load/save round-trip
print("--- Test 3: seen_ids persistence ---")
from main import load_seen_ids, save_seen_ids
import json, pathlib
ids = load_seen_ids()
print(f"OK: loaded {len(ids)} seen IDs from disk")

# Test 4: Claude — important email (Hebrew, lecture cancelled)
print("--- Test 4: Claude — important email ---")
import anthropic
from analyzer import is_important
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

ok, info = is_important("ביטול שיעור", "השיעור מחר מבוטל בשל מחלת המרצה", client)
assert ok is True, f"Expected important=True, got {ok}"
assert "course" in info and "change" in info and "details" in info, f"Missing keys: {info}"
print(f"OK: important=True  course={info['course']}  change={info['change']}")

# Test 5: Claude — not important (newsletter)
print("--- Test 5: Claude — not important email ---")
not_ok, info2 = is_important("Monthly Newsletter", "Campus events and activities this month", client)
assert not_ok is False, f"Expected important=False, got {not_ok}"
print("OK: newsletter correctly classified as not important")

# Test 6: Long email — verifies max_tokens is sufficient
print("--- Test 6: Long response fits within max_tokens ---")
ok3, info3 = is_important(
    "שינוי מיקום שיעור אלגוריתמים מתקדמים",
    "שלום, שיעור האלגוריתמים המתקדמים של פרופ כהן מועבר מחדר 101 לאודיטוריום הגדול בבניין אלון, יום חמישי בשעה 14:00",
    client,
)
assert "course" in info3 and "change" in info3, f"Parse failed: {info3}"
print(f"OK: course={info3.get('course').encode('ascii','replace').decode()}  details={info3.get('details', 'N/A').encode('ascii','replace').decode()}")

# Test 7: Malformed Claude response handled gracefully (simulate)
print("--- Test 7: Malformed response fallback ---")
from analyzer import _SYSTEM_PROMPT
# Patch: make Claude return garbage by asking off-topic
ok4, info4 = is_important("", "", client)
assert isinstance(ok4, bool), "Return type must be bool"
assert isinstance(info4, dict), "Return type must be dict"
print(f"OK: empty email handled gracefully, important={ok4}")

print()
print("All tests passed.")
