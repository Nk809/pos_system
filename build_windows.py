from pathlib import Path
import os
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parent


def main():
    if os.name != "nt":
        print("Windows build must be run on Windows.")
        print("Use this script on a Windows machine after copying the project there.")
        sys.exit(1)

    assets_dir = PROJECT_ROOT / "assets"
    data_dir = PROJECT_ROOT / "data"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "MatchlessGiftPOS",
        "--add-data",
        f"{assets_dir};assets",
        "--add-data",
        f"{data_dir};data",
        "--hidden-import",
        "sqlite_web",
        "--hidden-import",
        "qrcode",
        "--hidden-import",
        "PIL.Image",
        "--hidden-import",
        "PIL.ImageTk",
        "--hidden-import",
        "PIL._tkinter_finder",
        "--hidden-import",
        "usb.core",
        "--hidden-import",
        "usb.util",
        "--hidden-import",
        "win32print",
        "--collect-submodules",
        "qrcode",
        "--collect-submodules",
        "pyzbar",
        "--collect-submodules",
        "matplotlib",
        "main.py",
    ]

    print("Running:", " ".join(command))
    subprocess.run(command, check=True, cwd=PROJECT_ROOT)


if __name__ == "__main__":
    main()
