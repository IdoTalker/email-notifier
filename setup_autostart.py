"""
Run this once to enable auto-start at login via the Windows Registry.
Same as clicking "Enable auto-start at login" from the tray icon.

Usage: python setup_autostart.py
"""
import sys
import winreg
from pathlib import Path

TASK_NAME = "UniversityEmailNotifier"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def main() -> None:
    python_dir = Path(sys.executable).parent
    pythonw = python_dir / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)

    script = (Path(__file__).parent / "main.py").absolute()
    value = f'"{pythonw}" "{script}"'

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, TASK_NAME, 0, winreg.REG_SZ, value)
        print("Done. The notifier will start automatically (no window) at every login.")
        print(f"Command registered: {value}")
        print("\nTo remove auto-start, use the tray icon menu or run:")
        print("  python -c \"import winreg; k=winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Run', 0, winreg.KEY_SET_VALUE); winreg.DeleteValue(k, 'UniversityEmailNotifier')\"")
    except OSError as e:
        print(f"Failed to write registry key: {e}")


if __name__ == "__main__":
    main()
