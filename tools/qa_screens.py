"""Render all application screens using isolated, clearly labeled QA data."""
import os
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
    output = Path("output/screens")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="macooii-ui-qa-") as directory:
        store = Store(Path(directory))
        store.save_note("Project ideas · QA sample", "Build something useful, then make it reliable.\n\nKeep the first version focused on research, documents, and everyday tasks.")
        store.remember("QA sample: explain ideas clearly in English and Taglish.")
        store.log("search_files", "completed")
        bridge = Bridge(store)
        qml = QQmlApplicationEngine()
        warnings = []
        qml.warnings.connect(lambda values: warnings.extend(str(value) for value in values))
        qml.rootContext().setContextProperty("backend", bridge)
        qml.load(QUrl.fromLocalFile(str(resource_path("Main.qml"))))
        window: QQuickWindow = qml.rootObjects()[0]
        pages = iter(enumerate(["home", "notes", "memory", "activity", "settings"]))

        def capture():
            try:
                index, name = next(pages)
                window.setProperty("currentPage", index)
                QTimer.singleShot(180, lambda: save(name))
            except StopIteration:
                bridge._pending_approval = {"label": "Document excerpt · QA sample", "provider": "Google Gemini",
                                            "allowLocal": True, "text": "Example proposal.txt\n\nThis is a sample excerpt used only to verify the approval screen.\n\nNo personal file has been read."}
                bridge.approvalChanged.emit()
                QTimer.singleShot(180, lambda: save("approval", done=True))

        def save(name, done=False):
            window.grabWindow().save(str(output / f"{name}.png"))
            if done:
                print("QML warnings:", warnings)
                bridge.shutdown()
                app.exit(1 if warnings else 0)
            else:
                capture()

        QTimer.singleShot(300, capture)
        return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
