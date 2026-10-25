import imaplib
import email
import email.header
import email.message
import re
from html.parser import HTMLParser

from config import IMAP_SERVER, IMAP_PORT, BODY_PREVIEW_CHARS, MAX_EMAILS_PER_POLL

# Inline styles that hide text from the human reader but not from a tag stripper — a classic
# way to smuggle instructions to the model.
_HIDDEN_STYLE_RE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\.0+)?\s*(?:;|$)"
    r"|font-size\s*:\s*[01](?:\.\d+)?\s*(?:px|pt)?\s*(?:;|$)"
    r"|(?<![-\w])color\s*:\s*(?:#fff\b|#ffffff\b|white\b|transparent\b)"
    r"|(?:left|top|right|text-indent|margin-left|margin-top)\s*:\s*-\d{3,}"
    r"|(?:max-)?height\s*:\s*0(?:px)?\s*(?:;|$)",
    re.IGNORECASE,
)
# Same trick through a stylesheet: <style>.x{display:none}</style> ... <div class="x">
_HIDDEN_CLASS_RE = re.compile(r"\.([\w-]+)\s*\{([^}]*)\}")
_STYLE_BLOCK_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_SKIP_TAGS = {"script", "style", "head", "title"}


def _hidden_classes(raw_html: str) -> set[str]:
    classes = set()
    for block in _STYLE_BLOCK_RE.findall(raw_html):
        for name, rules in _HIDDEN_CLASS_RE.findall(block):
            if _HIDDEN_STYLE_RE.search(rules):
                classes.add(name)
    return classes


class _VisibleTextParser(HTMLParser):
    """Collects only the text a human would see, dropping hidden elements and their children."""

    def __init__(self, hidden_classes: set[str]):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._hidden_classes = hidden_classes
        # Only tags with the same name as the hidden element count toward its nesting, so an
        # unclosed <p> inside a hidden <div> can't swallow the rest of the email.
        self._skip_tag = None
        self._skip_depth = 0

    def _is_hidden(self, tag, attrs) -> bool:
        style = attrs.get("style") or ""
        classes = set((attrs.get("class") or "").split())
        return (
            tag in _SKIP_TAGS
            or "hidden" in attrs
            or bool(_HIDDEN_STYLE_RE.search(style))
            or bool(classes & self._hidden_classes)
        )

    def handle_starttag(self, tag, attrs):
        if tag in _VOID_TAGS:
            return
        if self._skip_tag:
            if tag == self._skip_tag:
                self._skip_depth += 1
            return
        if self._is_hidden(tag, dict(attrs)):
            self._skip_tag = tag
            self._skip_depth = 1

    def handle_endtag(self, tag):
        if self._skip_tag and tag == self._skip_tag:
            self._skip_depth -= 1
            if not self._skip_depth:
                self._skip_tag = None

    def handle_data(self, data):
        if not self._skip_tag:
            self.parts.append(data)


def _html_to_text(raw_html: str) -> str:
    parser = _VisibleTextParser(_hidden_classes(raw_html))
    parser.feed(raw_html)
    parser.close()
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def _decode_header_value(raw_value: str) -> str:
    parts = email.header.decode_header(raw_value)
    decoded_parts = []
    for part_bytes, charset in parts:
        if isinstance(part_bytes, bytes):
            charset = charset or "utf-8"
            try:
                decoded_parts.append(part_bytes.decode(charset, errors="replace"))
            except (LookupError, UnicodeDecodeError):
                decoded_parts.append(part_bytes.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(part_bytes)
    return "".join(decoded_parts)


def _decode_payload(payload: bytes, charset: str | None) -> str:
    charset = charset or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        # Fallback to windows-1255 (Hebrew Windows encoding) then utf-8
        try:
            return payload.decode("windows-1255", errors="replace")
        except Exception:
            return payload.decode("utf-8", errors="replace")


def _extract_body(msg: email.message.Message) -> str:
    plain_parts = []
    html_parts = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            text = _decode_payload(payload, part.get_content_charset())
            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            text = _decode_payload(payload, msg.get_content_charset())
            if msg.get_content_type() == "text/html":
                html_parts.append(text)
            else:
                plain_parts.append(text)

    # Prefer HTML: it's what mail clients render, so a plain-text alternative can say something
    # the reader never sees.
    if html_parts:
        return _html_to_text(" ".join(html_parts))

    if plain_parts:
        return " ".join(plain_parts)

    return ""


def fetch_unread_emails(imap_user: str, imap_pass: str) -> list[dict]:
    """
    Fetch unread emails over IMAP without marking them as read.
    Returns up to MAX_EMAILS_PER_POLL emails, newest first.
    """
    emails = []

    try:
        with imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT) as mail:
            mail.login(imap_user, imap_pass)
            mail.select("INBOX", readonly=True)

            status, uid_data = mail.uid("SEARCH", None, "UNSEEN")
            if status != "OK" or not uid_data[0]:
                return []

            uid_list = uid_data[0].split()
            uid_list = uid_list[::-1][:MAX_EMAILS_PER_POLL]

            for uid_bytes in uid_list:
                uid_str = uid_bytes.decode("ascii")
                status, full_data = mail.uid("FETCH", uid_bytes, "(BODY.PEEK[])")
                if status != "OK" or not full_data or not isinstance(full_data[0], tuple):
                    continue

                raw_email = full_data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject = _decode_header_value(msg.get("Subject", "(No Subject)"))
                sender = _decode_header_value(msg.get("From", ""))
                body = _extract_body(msg)

                emails.append({
                    "uid": uid_str,
                    "subject": subject,
                    "body_preview": body[:BODY_PREVIEW_CHARS].strip(),
                    "from": sender,
                })

    except imaplib.IMAP4.error:
        raise
    except OSError as e:
        raise ConnectionError(f"Network error connecting to IMAP: {e}") from e

    return emails
