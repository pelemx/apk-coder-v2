import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import AppWindow
from gui.web_compat import apply_web_compat

apply_web_compat(AppWindow)


def main():
    print("Starting JuprisX HTML/JS Android Builder...")
    app = AppWindow()
    app.run()


if __name__ == "__main__":
    main()
