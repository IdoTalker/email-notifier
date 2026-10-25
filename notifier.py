from winotify import Notification, audio

from config import APP_NAME


def send_notification(info: dict, sender: str, inbox_url: str) -> None:
    """Show a Windows 10/11 toast notification. Clicking it opens the correct Gmail inbox."""
    course = info.get("course", "Unknown")
    change = info.get("change", "update").title()
    details = info.get("details", "N/A")

    title = f"{course} — {change}"[:64]

    body = f"From: {sender[:50]}"
    if details and details.upper() != "N/A":
        body += f"\n{details[:100]}"

    toast = Notification(
        app_id=APP_NAME,
        title=title,
        msg=body,
        duration="long",
        launch=inbox_url,
    )
    toast.set_audio(audio.Default, loop=False)
    toast.show()
