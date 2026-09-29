"""Chrome headless screenshots of the class-169 preview pages."""
import pathlib
import subprocess

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def shoot(page, out, width, height):
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
           "--virtual-time-budget=8000", "--window-size=" + str(width) + "," + str(height),
           "--screenshot=" + str(pathlib.Path(out).resolve()), str(pathlib.Path(page).resolve())]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        print("failed", page, result.stderr[-500:])
        return False
    print("saved", out, pathlib.Path(out).stat().st_size)
    return True


ok = shoot("preview/dashboard-169.html", "docs/preview-dashboard-history/html-169-all.png", 1600, 1060)
ok &= shoot("preview/dashboard-169-focus.html", "docs/preview-dashboard-history/html-169-focus.png", 1600, 1060)
print("both ok" if ok else "one failed")
