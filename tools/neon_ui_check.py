"""Verify the neon dashboard with disposable data, without opening the microphone."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"

from PySide6.QtCore import QObject, Qt, QUrl
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from macooii.bridge import Bridge
from macooii.config import resource_path
from macooii.storage import Store


def main():
    app = QApplication([])
    QFontDatabase.addApplicationFont(str(resource_path("fonts/Figtree.ttf")))
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/seguisym.ttf")
    app.setFont(QFont("Figtree"))
    output = Path("output/neon-ui")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="macooii-neon-qa-") as directory:
        store = Store(Path(directory))
        store.set_setting("speech_enabled", False)
        store.save_note("Command center redesign - QA sample", "Review the new neon interface.")
        store.remember("QA sample: keep explanations clear and practical.")
        store.log("create_note", "completed")
        store.log("search_files", "completed")
        bridge = Bridge(store)
        qml = QQmlApplicationEngine()
        warnings = []
        qml.warnings.connect(lambda rows: warnings.extend(str(row) for row in rows))
        qml.rootContext().setContextProperty("backend", bridge)
        qml.load(QUrl.fromLocalFile(str(resource_path("Main.qml"))))
        assert qml.rootObjects(), warnings
        window = qml.rootObjects()[0]
        window.setWidth(1500)
        window.setHeight(900)
        page = window.findChild(QObject, "assistantPage")
        composer = window.findChild(QQuickItem, "composer")
        right = window.findChild(QObject, "dashboardRight")

        def visual_item(name, parent=None):
            parent = parent or window.contentItem()
            if parent.objectName() == name:
                return parent
            for child in parent.childItems():
                found = visual_item(name, child)
                if found is not None:
                    return found
            return None

        def capture(name):
            QTest.qWait(350)
            assert window.grabWindow().save(str(output / f"{name}.png"))

        def click(name):
            item = visual_item(name)
            assert item and item.isVisible(), name
            point = item.mapToScene(item.boundingRect().center()).toPoint()
            QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
            QTest.qWait(80)

        capture("dashboard")
        assert sum(right.property("dailyActivity").toVariant()) == 2
        bar = visual_item("activityBar6")
        assert bar.height() > 30, bar.height()
        click("quickCommand1")
        assert composer.property("text") == "/find "
        assert composer.hasActiveFocus()
        composer.setProperty("text", "/help")
        click("sendButton")
        for _ in range(100):
            if not bridge.busy:
                break
            QTest.qWait(50)
        assert len(store.messages()) == 2
        assert page.property("currentReply")
        capture("response")
        page.setProperty("detailsOpen", True)
        capture("full-response")
        page.setProperty("detailsOpen", False)
        page.setProperty("historyOpen", True)
        capture("history")
        page.setProperty("historyOpen", False)
        for mode in ("listening", "thinking", "speaking"):
            bridge._recording = mode == "listening"
            bridge._busy = mode == "thinking"
            bridge.stateChanged.emit()
            state = QMediaPlayer.PlaybackState.PlayingState if mode == "speaking" else QMediaPlayer.PlaybackState.StoppedState
            # Visual-only fixture: no audio device is opened.
            with patch.object(bridge.player, "playbackState", return_value=state):
                bridge._voice_level = 0.6 if mode == "speaking" else 0
                bridge.voiceStateChanged.emit()
                bridge.voiceLevelChanged.emit()
                assert page.property("mode") == mode
                capture(mode)
            bridge.voiceStateChanged.emit()
        bridge._recording = False
        bridge._busy = False
        bridge.stateChanged.emit()
        for width, height in ((1250, 780), (1000, 700)):
            window.setWidth(width)
            window.setHeight(height)
            capture(f"compact-{width}")
            assert not right.property("visible")
            for name in ("composer", "talkButton", "conversationButton", "sendButton"):
                item = window.findChild(QQuickItem, name)
                point = item.mapToScene(item.boundingRect().center())
                assert 0 < point.x() < width and 0 < point.y() < height, (name, point)
            assert window.findChild(QQuickItem, "talkButton").width() >= 80
        window.setWidth(1500)
        window.setHeight(900)
        for index, name in enumerate(("voice", "notes", "memory", "activity", "settings")):
            window.setProperty("currentPage", index)
            capture(name)
        window.setVisible(False)
        bridge.shutdown()
        assert not warnings, warnings
        print("Verified: real data and chart, quick-command focus, command submission, response/history, voice states, five pages, and compact layouts. QML warnings: 0")


if __name__ == "__main__":
    main()
