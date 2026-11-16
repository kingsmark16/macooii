"""Synthetic Facebook DOM → native protocol → local review, without private account access."""
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.route("https://www.facebook.com/**", lambda route: route.fulfill(body='''<!doctype html>
            <title>Professional Dashboard - QA sample</title><nav>Navigation excluded</nav>
            <main><h1>Professional dashboard - QA sample</h1><p>Last 28 days</p>
            <p>Views</p><strong>1200</strong><p>Followers</p><strong>42</strong>
            <span style="display:none">Hidden private value</span><input value="Secret input">
            <textarea>Private draft</textarea><div contenteditable="true">Unsent draft</div></main>''', content_type="text/html"))
        page.goto("https://www.facebook.com/professional_dashboard?private=not-shared")
        page.add_script_tag(path=str(ROOT / "browser-extension/capture.js"))
        capture = page.evaluate("captureFacebook()")
        assert "1200" in capture["text"] and "42" in capture["text"]
        assert not any(value in capture["text"] for value in ("Hidden private", "Secret input", "Private draft", "Unsent draft", "Navigation excluded"))
        assert "?" not in capture["url"]
        page.evaluate("const r=document.createRange(); r.selectNodeContents(document.querySelector('strong')); const s=getSelection(); s.removeAllRanges(); s.addRange(r)")
        selected = page.evaluate("captureFacebook()")
        assert selected["selection"] and selected["text"] == "1200"
        browser.close()
    body = json.dumps(capture).encode()
    with tempfile.TemporaryDirectory(prefix="macooii-capture-qa-") as folder:
        env = dict(os.environ, MACOOII_DATA_DIR=folder)
        host = ROOT / "dist/Macooii/browser-bridge/MacooiiBrowserHost.exe"
        command = [str(host)] if "--frozen-host" in sys.argv else [sys.executable, str(ROOT / "tools/browser_host.py")]
        response = subprocess.run(command + ["chrome-extension://echjcjmpfcgiockeaofblhpjncanccfg/"],
                                  input=struct.pack("=I", len(body)) + body, capture_output=True, env=env, check=True)
        size = struct.unpack("=I", response.stdout[:4])[0]
        answer = json.loads(response.stdout[4:4 + size])
        assert answer["ok"]
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
        from PySide6.QtCore import QTimer, QUrl
        from PySide6.QtGui import QFont, QFontDatabase
        from PySide6.QtQml import QQmlApplicationEngine
        from PySide6.QtQuick import QQuickWindow
        from PySide6.QtWidgets import QApplication

        from macooii.bridge import Bridge
        from macooii.config import resource_path
        from macooii.storage import Store

        app = QApplication([])
        QFontDatabase.addApplicationFont(str(resource_path("fonts/Figtree.ttf")))
        QFontDatabase.addApplicationFont("C:/Windows/Fonts/seguisym.ttf")
        app.setFont(QFont("Figtree"))
        bridge = Bridge(Store(Path(folder)))
        bridge._poll_capture()
        assert bridge.browserCapture["text"] == capture["text"]
        assert bridge.store.messages() == []
        engine = QQmlApplicationEngine()
        warnings = []
        engine.warnings.connect(lambda values: warnings.extend(str(value) for value in values))
        engine.rootContext().setContextProperty("backend", bridge)
        engine.load(QUrl.fromLocalFile(str(resource_path("Main.qml"))))
        assert engine.rootObjects()

        def finish():
            try:
                window: QQuickWindow = engine.rootObjects()[0]
                assert window.grabWindow().save(str(ROOT / "output/browser-capture-preview.png"))
                bridge.dismissBrowserCapture()
            finally:
                bridge.shutdown()
                app.quit()

        QTimer.singleShot(500, finish)
        app.exec()
        assert not warnings, warnings
    print(json.dumps({"visible_text": "passed", "selection": "passed", "hidden_and_drafts_excluded": "passed",
                      "native_protocol": "passed", "review_without_cloud": "passed", "qml_warnings": warnings}))


if __name__ == "__main__":
    main()
