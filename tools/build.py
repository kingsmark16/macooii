"""Build a relocatable Windows folder and ZIP. Run: uv run python tools/build.py"""
from __future__ import annotations

import hashlib
import importlib.metadata
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    arguments = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--windowed",
                 "--name", "Macooii", "--paths", str(ROOT / "src"),
                 "--add-data", str(ROOT / "src/macooii/ui") + ";macooii/ui",
                 "--collect-data", "faster_whisper", "--hidden-import", "keyring.backends.Windows",
                 "--collect-all", "espeakng_loader", "--collect-data", "kokoro_onnx",
                 "--copy-metadata", "kokoro-onnx",
                 "--hidden-import", "win32timezone", "--hidden-import", "pythoncom",
                 "--exclude-module", "PySide6.QtWebEngineWidgets", "--exclude-module", "PySide6.QtWebEngineCore",
                 "--exclude-module", "PySide6.QtWebEngineQuick", "--exclude-module", "torch",
                 "--exclude-module", "tensorflow", "--exclude-module", "matplotlib",
                 "--exclude-module", "tkinter", "--exclude-module", "pytest", str(ROOT / "tools/entry.py")]
    subprocess.run(arguments, cwd=ROOT, check=True)
    destination = ROOT / "dist/Macooii"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--console",
                    "--name", "MacooiiBrowserHost", "--paths", str(ROOT / "src"),
                    "--distpath", str(ROOT / "build/browser-host-dist"),
                    "--workpath", str(ROOT / "build/browser-host-work"),
                    "--specpath", str(ROOT / "build/browser-host-spec"),
                    str(ROOT / "tools/browser_host.py")], cwd=ROOT, check=True)
    shutil.copytree(ROOT / "browser-extension", destination / "browser-extension", dirs_exist_ok=True)
    (destination / "browser-bridge").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "build/browser-host-dist/MacooiiBrowserHost.exe", destination / "browser-bridge/MacooiiBrowserHost.exe")
    (destination / "Install Browser Bridge.cmd").write_text(
        '@echo off\ncd /d "%~dp0"\nstart "" /wait "%~dp0Macooii.exe" --install-browser-bridge\n'
        'if errorlevel 1 (echo Bridge setup failed. Keep the complete Macooii folder together.) else (echo Browser bridge installed. Load the browser-extension folder in Chrome.)\npause\n', encoding="utf-8")
    license_dir = destination / "licenses"
    license_dir.mkdir(exist_ok=True)
    inventory = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name", "unknown")
        inventory.append(f"{name}=={distribution.version}\nLicense: " +
                         distribution.metadata.get("License-Expression", distribution.metadata.get("License", "See package notices")))
        for item in distribution.files or []:
            if ".dist-info/licenses/" in str(item).replace("\\", "/"):
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    target = license_dir / name / Path(item).name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    (license_dir / "DEPENDENCIES.txt").write_text("\n\n".join(inventory), encoding="utf-8")
    shutil.copy2(ROOT / "src/macooii/ui/fonts/OFL.txt", license_dir / "Figtree-OFL.txt")
    shutil.copy2(ROOT / "README.md", destination / "README.md")
    shutil.copytree(ROOT / "docs", destination / "docs", dirs_exist_ok=True)
    archive = shutil.make_archive(str(ROOT / "dist/Macooii-Windows-x64"), "zip", ROOT / "dist", "Macooii")
    with open(archive, "rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    (ROOT / "dist/SHA256.txt").write_text(digest + "  Macooii-Windows-x64.zip\n", encoding="utf-8")
    print(f"Built {archive}", flush=True)


if __name__ == "__main__":
    main()
