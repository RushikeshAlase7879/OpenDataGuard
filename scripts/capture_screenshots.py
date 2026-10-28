"""Automated high-fidelity screenshot capture for OpenDataGuard using Chrome DevTools Protocol."""

import asyncio
import base64
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
import websockets

SCREENSHOT_DIR = Path("D:/OpenDataGuard/docs/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA = Path(os.environ.get("TEMP", "C:/Temp")) / "chrome_odg_snap"
if USER_DATA.exists():
    try:
        shutil.rmtree(USER_DATA, ignore_errors=True)
    except Exception:
        pass

PAGES = [
    ("01_overview_dashboard.png", "http://127.0.0.1:8506/?page=overview"),
    ("02_dataset_explorer.png", "http://127.0.0.1:8506/?page=explorer&sample=1"),
    ("03_data_quality_validation.png", "http://127.0.0.1:8506/?page=validation&sample=1"),
    ("04_dataset_reconciliation.png", "http://127.0.0.1:8506/?page=reconciliation&sample=1"),
    ("05_sql_database_validation.png", "http://127.0.0.1:8506/?page=database"),
    ("06_validation_history.png", "http://127.0.0.1:8506/?page=history"),
]

def main():
    if not Path(CHROME_PATH).exists():
        print("Chrome not found at", CHROME_PATH)
        return

    print("Launching Chrome headless with remote debugging...")
    proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        f"--user-data-dir={USER_DATA}",
        "--remote-debugging-port=9222",
        "--window-size=1440,900"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    time.sleep(3)
    try:
        req = urllib.request.Request("http://127.0.0.1:9222/json")
        with urllib.request.urlopen(req, timeout=5) as r:
            targets = json.loads(r.read())

        page_targets = [t for t in targets if t.get("type") == "page"]
        if not page_targets:
            print("No browser page targets available in Chrome")
            return

        ws_url = page_targets[0]["webSocketDebuggerUrl"].replace("localhost", "127.0.0.1")
        print("Connecting to CDP WebSocket target:", ws_url)

        async def capture_all():
            async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
                msg_id = 1
                for filename, url in PAGES:
                    print(f"Navigating to {filename} ({url})...", flush=True)
                    msg_id += 1
                    await ws.send(json.dumps({
                        "id": msg_id,
                        "method": "Page.navigate",
                        "params": {"url": url}
                    }))
                    
                    # Wait for Streamlit React / DOM to finish rendering
                    await asyncio.sleep(5)

                    out_path = SCREENSHOT_DIR / filename
                    msg_id += 1
                    capture_id = msg_id
                    await ws.send(json.dumps({
                        "id": capture_id,
                        "method": "Page.captureScreenshot",
                        "params": {"format": "png"}
                    }))

                    while True:
                        msg = json.loads(await ws.recv())
                        if msg.get("id") == capture_id:
                            if "result" in msg and "data" in msg["result"]:
                                img_data = base64.b64decode(msg["result"]["data"])
                                with open(out_path, "wb") as f:
                                    f.write(img_data)
                                print(f"Successfully saved {filename} ({len(img_data)} bytes)", flush=True)
                            else:
                                print(f"Error capturing {filename}: {msg}", flush=True)
                            break

        asyncio.run(capture_all())

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()

if __name__ == "__main__":
    main()
