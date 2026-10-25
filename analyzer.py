import anthropic

from config import CLAUDE_MODEL, CLAUDE_MAX_TOKENS

_SYSTEM_PROMPT = """You are an assistant that classifies university emails for an Israeli university student.

If the email is NOT important (newsletter, promotional, social event, routine update with no action needed), respond with exactly:
NOT_IMPORTANT

If the email IS important (lecture/class cancelled or postponed, exam rescheduled, deadline changed, emergency announcement, registration deadline, grade release), respond with exactly these 4 lines and nothing else:
IMPORTANT
course: <name of the course or subject, or "General" if university-wide>
change: <one short phrase: cancelled / postponed / rescheduled / deadline changed / exam update / emergency / other>
details: <new time, location, or deadline if mentioned — otherwise N/A>"""


def is_important(subject: str, body_preview: str, client: anthropic.Anthropic) -> tuple[bool, dict]:
    """
    Ask Claude Haiku whether this email is important for a university student.
    Returns (True, info_dict) if important, (False, {}) otherwise.
    info_dict keys: course, change, details
    """
    user_content = f"Subject: {subject}\nPreview: {body_preview}"

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=CLAUDE_MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {"role": "user", "content": user_content}
        ],
    )

    raw = response.content[0].text.strip()
    lines = raw.splitlines()

    if not lines:
        return False, {}

    if lines[0].strip().upper() == "NOT_IMPORTANT":
        return False, {}

    if lines[0].strip().upper() == "IMPORTANT":
        info = {"course": "Unknown", "change": "update", "details": "N/A"}
        for line in lines[1:]:
            if ":" in line:
                key, _, val = line.partition(":")
                info[key.strip().lower()] = val.strip()
        return True, info

    return False, {}
