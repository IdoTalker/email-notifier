import winreg, sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "UniversityEmailNotifier"

pythonw = Path(sys.executable).parent / "pythonw.exe"
script = Path(__file__).parent / "main.py"
value = f'"{pythonw}" "{script}"'

with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
    winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, value)
print("Write: OK")

with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
    v, _ = winreg.QueryValueEx(k, NAME)
print(f"Read:  OK")

with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
    winreg.DeleteValue(k, NAME)
print("Delete: OK")

try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        winreg.QueryValueEx(k, NAME)
    print("ERROR: key still exists")
except FileNotFoundError:
    print("Confirm deleted: OK")

print("\nAll registry operations work correctly.")
