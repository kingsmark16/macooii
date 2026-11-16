"""Render voice console states with isolated QA fixtures; microphone is never opened."""
import os
import shutil
import tempfile
from pathlib import Path

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


def main():
    app = QApplication([])
    QFontDatabase.addApplicationFont(str(resource_path("fonts/Figtree.ttf")))
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/seguisym.ttf")
    app.setFont(QFont("Figtree"))
    output = Path("output/voice-interface")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="macooii-voice-ui-") as folder:
        store = Store(Path(folder))
        store.set_setting("provider", "codex")
        store.set_setting("voice_conversation", True)
        store.set_setting("language", "en")
        bridge = Bridge(store)
        bridge.neural.ready = lambda: True
        bridge.transcriber.ready = lambda: True
        qml = QQmlApplicationEngine()
        warnings = []
        qml.warnings.connect(lambda values: warnings.extend(str(value) for value in values))
        qml.rootContext().setContextProperty("backend", bridge)
        qml.load(QUrl.fromLocalFile(str(resource_path("Main.qml"))))
        window: QQuickWindow = qml.rootObjects()[0]
        # QObject selection avoids depending on a specific Qt Quick subclass wrapper.
        from PySide6.QtCore import QObject
        page = window.findChild(QObject, "assistantPage")
        stages = iter(["idle", "listening", "thinking", "speaking", "response", "details", "history", "compact"])
        captures = []

        def next_stage():
            try:
                name = next(stages)
            except StopIteration:
                bridge.shutdown()
                app.quit()
                return
            bridge.stopAudio()
            bridge._recording = name == "listening"
            bridge._busy = name == "thinking"
            bridge.recorder.level = 0.12
            bridge.stateChanged.emit()
            bridge.microphoneLevelChanged.emit()
            bridge._set_status("Thinking through your request" if name == "thinking" else "Ready when you are")
            page.setProperty("historyOpen", name == "history")
            page.setProperty("detailsOpen", name == "details")
            if name == "speaking":
                clip = Path(folder) / "public-voice.wav"
                shutil.copy2("output/voice-conversation-input.wav", clip)
                bridge._play_audio(str(clip))
            if name == "response":
                store.add_message("user", "Help me get started with my workspace.")
                store.add_message("assistant", "I'm ready to help. Ask me to open a website, research a topic, or save a note. Your complete written responses will stay available whenever you need them.")
                bridge.messagesChanged.emit()
            if name == "compact":
                window.setWidth(1000)
                window.setHeight(700)
            QTimer.singleShot(480 if name != "speaking" else 800, lambda: capture(name))

        def capture(name):
            assert window.grabWindow().save(str(output / (name + ".png")))
            captures.append(name)
            if name == "speaking":
                assert bridge.speaking and bridge.voiceLevel > 0
            QTimer.singleShot(30, next_stage)

        QTimer.singleShot(400, next_stage)
        QTimer.singleShot(18000, app.quit)
        app.exec()
        bridge._recording = False
        bridge.shutdown()
        assert len(captures) == 8, captures
        assert not warnings, warnings
        print({"screens": captures, "qml_warnings": warnings})


if __name__ == "__main__":
    main()
