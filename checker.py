import imaplib
import email
import email.header
import email.message
import re

from config import IMAP_SERVER, IMAP_PORT, BODY_PREVIEW_CHARS, MAX_EMAILS_PER_POLL


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

    if plain_parts:
        return " ".join(plain_parts)

    if html_parts:
        raw_html = " ".join(html_parts)
        clean = re.sub(r"<[^>]+>", " ", raw_html)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean

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
