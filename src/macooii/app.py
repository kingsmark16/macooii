from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, QLockFile, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .bridge import Bridge
from .config import data_dir, resource_path
from .storage import Store


def make_icon() -> QIcon:
    image = QPixmap(128, 128)
    image.fill(QColor("transparent"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#101b25"))
    painter.setPen(QPen(QColor("#35dec6"), 4))
    painter.drawEllipse(12, 12, 104, 104)
    painter.setPen(QPen(QColor("#35dec6"), 7))
    painter.drawArc(30, 30, 68, 68, 20 * 16, 285 * 16)
    painter.setBrush(QColor("#35dec6"))
    painter.setPen(QPen(QColor("#35dec6"), 1))
    painter.drawEllipse(53, 53, 22, 22)
    painter.end()
    return QIcon(image)


class Hotkeys(QAbstractNativeEventFilter):
    def __init__(self, bridge: Bridge, show):
        super().__init__()
        self.bridge = bridge
        self.show = show
        self.registered = []
        self.selection = None
        self.talk_key = 0x20
        self.poll = QTimer()
        self.poll.setInterval(35)
        self.poll.timeout.connect(self._released)
        self.reconfigure()
        bridge.settingsChanged.connect(self.reconfigure)

    def reconfigure(self):
        selected = (self.bridge.store.setting("open_shortcut"), self.bridge.store.setting("talk_shortcut"))
        if selected == self.selection:
            return
        self.close()
        self.selection = selected
        open_key = ord(selected[0].split("+")[-1])
        talk = selected[1].split("+")[-1]
        self.talk_key = 0x20 if talk == "Space" else ord(talk)
        if os.name == "nt":
            for identity, key in ((1, open_key), (2, self.talk_key)):
                if ctypes.windll.user32.RegisterHotKey(None, identity, 0x4000 | 0x0002 | 0x0001, key):
                    self.registered.append(identity)
                else:
                    self.bridge.toast.emit("A shortcut is already in use. Choose another in Settings.")

    def _released(self):
        held = all(ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000
                   for key in (self.talk_key, 0x11, 0x12))
        if not held:
            self.poll.stop()
            self.bridge.stopRecording()

    def nativeEventFilter(self, event_type, message):
        if os.name == "nt" and event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312:
                if msg.wParam == 1:
                    self.show()
                elif msg.wParam == 2:
                    self.show()
                    self.bridge.startRecording()
                    self.poll.start()
                return True, 0
        return False, 0

    def close(self):
        self.poll.stop()
        if os.name == "nt":
            for identity in self.registered:
                ctypes.windll.user32.UnregisterHotKey(None, identity)
        self.registered = []


def main() -> int:
    if "--download-speech" in sys.argv:
        from .model_setup import download
        index = sys.argv.index("--download-speech")
        download(sys.argv[index + 1], sys.argv[index + 2] if len(sys.argv) > index + 2 else "small")
        return 0
    parser = argparse.ArgumentParser(description="Macooii Windows personal assistant")
    parser.add_argument("--data-dir", type=Path, help="Override local data directory")
    parser.add_argument("--screenshot", type=Path, help="Save a UI screenshot and exit (for QA)")
    parser.add_argument("--smoke-test", action="store_true", help="Load the interface, verify it, then exit")
    parser.add_argument("--verify-runtime", type=Path, help="Write an explicit runtime diagnostic JSON report")
    parser.add_argument("--verify-voice", type=Path, help="Play a public test sentence and report speaker playback")
    parser.add_argument("--verify-voice-order", type=Path, help="Verify speech, disposable note action, then speech")
    parser.add_argument("--verify-neural-voice", type=Path, help="Play a public neural voice sample and report the actual engine")
    parser.add_argument("--verify-response-speed", type=Path, help="Time synthetic recognition, quick receipt, and chunked speech; no microphone or cloud")
    parser.add_argument("--diagnostic-audio", type=Path, help="Optional public English test WAV for diagnostics")
    parser.add_argument("--diagnostic-web", action="store_true", help="Include a public example.com browser check")
    parser.add_argument("--install-browser-bridge", action="store_true", help="Register the local Chrome native messaging host")
    options = parser.parse_args()
    if options.verify_response_speed:
        from .latency_diagnostic import verify_response_speed
        return verify_response_speed(options.verify_response_speed)
    if options.verify_neural_voice:
        from .diagnostics import verify_voice
        return verify_voice(options.verify_neural_voice, neural=True)
    if options.install_browser_bridge:
        from .browser_capture import install_bridge
        folder = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2] / "dist/Macooii"
        install_bridge(folder)
        return 0
    if options.verify_voice_order:
        from .diagnostics import verify_voice
        return verify_voice(options.verify_voice_order, command=True)
    if options.verify_voice:
        from .diagnostics import verify_voice
        return verify_voice(options.verify_voice)
    if options.verify_runtime:
        from .diagnostics import verify
        return verify(options.verify_runtime, options.diagnostic_audio, options.diagnostic_web)
    root = options.data_dir or data_dir()
    root.mkdir(parents=True, exist_ok=True)
    QQuickStyle.setStyle("Basic")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Macooii")
    app.setOrganizationName("MacooiiDesktop")
    QFontDatabase.addApplicationFont(str(resource_path("fonts/Figtree.ttf")))
    # Also expose Windows symbol fallback to Qt's offscreen QA platform.
    symbol_font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/seguisym.ttf"
    if symbol_font.is_file():
        QFontDatabase.addApplicationFont(str(symbol_font))
    app.setFont(QFont("Figtree", 10))
    lock = QLockFile(str(root / "macooii.lock"))
    if not lock.tryLock(0):
        QMessageBox.information(None, "Macooii is already running", "Use the tray icon or your configured shortcut to open Macooii.")
        return 1
    icon = make_icon()
    app.setWindowIcon(icon)
    store = Store(root)
    bridge = Bridge(store)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", bridge)
    warnings = []
    engine.warnings.connect(lambda values: warnings.extend(str(value) for value in values))
    engine.load(QUrl.fromLocalFile(str(resource_path("Main.qml"))))
    if not engine.rootObjects():
        print("Could not load Macooii interface.\n" + "\n".join(warnings), file=sys.stderr)
        return 1
    window = engine.rootObjects()[0]
    window.setIcon(icon)

    def show():
        window.showNormal()
        window.raise_()
        window.requestActivate()

    bridge.showRequested.connect(show)
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("Macooii · " + store.setting("open_shortcut"))
    bridge.settingsChanged.connect(lambda: tray.setToolTip("Macooii · " + store.setting("open_shortcut")))
    menu = QMenu()
    show_action = QAction("Open Macooii", menu)
    show_action.triggered.connect(show)
    menu.addAction(show_action)
    stop_action = QAction("Stop current task", menu)
    stop_action.triggered.connect(bridge.cancel)
    menu.addAction(stop_action)
    menu.addSeparator()
    quit_action = QAction("Quit Macooii", menu)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: show() if reason in {
        QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick} else None)
    available = QSystemTrayIcon.isSystemTrayAvailable() and not options.smoke_test and not options.screenshot
    window.setProperty("trayAvailable", available)
    if available:
        app.setQuitOnLastWindowClosed(False)
        tray.show()
    keys = Hotkeys(bridge, show) if not options.smoke_test and not options.screenshot else None
    if keys:
        app.installNativeEventFilter(keys)

    def quit_app():
        bridge.shutdown()
        if keys:
            keys.close()
        tray.hide()
        app.quit()

    quit_action.triggered.connect(quit_app)
    app.aboutToQuit.connect(bridge.shutdown)
    if options.screenshot or options.smoke_test:
        def finish_qa():
            if options.screenshot:
                options.screenshot.parent.mkdir(parents=True, exist_ok=True)
                if not window.grabWindow().save(str(options.screenshot)):
                    app.exit(2)
                    return
            print(json.dumps({"loaded": True, "qml_warnings": warnings, "width": window.width(),
                              "height": window.height()}))
            app.exit(2 if warnings else 0)
        QTimer.singleShot(1200, finish_qa)
    else:
        QTimer.singleShot(150, bridge.refreshStatus)
        QTimer.singleShot(750, bridge.prepareVoice)
    result = app.exec()
    bridge.shutdown()
    if keys:
        keys.close()
    bridge.pool.waitForDone(65_000)
    lock.unlock()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
