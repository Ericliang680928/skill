#!/usr/bin/env python3
"""Desktop notification: notify.py TITLE [MESSAGE]. macOS → Notification Center, Linux → notify-send,
Windows → toast via PowerShell; always also prints to stdout."""
import platform
import shutil
import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: notify.py TITLE [MESSAGE]")
    title, msg = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")
    print(f"🔔 {title}: {msg}")
    system = platform.system()
    try:
        if system == "Darwin":
            esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(["osascript", "-e",
                            f'display notification "{esc(msg)}" with title "{esc(title)}" sound name "Glass"'],
                           check=False, timeout=10)
        elif system == "Linux" and shutil.which("notify-send"):
            subprocess.run(["notify-send", title, msg], check=False, timeout=10)
        elif system == "Windows":
            q = lambda s: "'" + s.replace("'", "''") + "'"
            ps = ("[reflection.assembly]::loadwithpartialname('System.Windows.Forms')|Out-Null;"
                  "$n=New-Object System.Windows.Forms.NotifyIcon;$n.Icon=[System.Drawing.SystemIcons]::Information;"
                  f"$n.Visible=$true;$n.ShowBalloonTip(8000,{q(title)},{q(msg)},'Info');Start-Sleep 9")
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps])
    except Exception as e:  # notification is best-effort
        print(f"(通知失敗：{e})", file=sys.stderr)


if __name__ == "__main__":
    main()
