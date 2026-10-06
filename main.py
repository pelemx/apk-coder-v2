import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gui.app import AppWindow

def main():
    print("Starting JuprisX Web-to-Android Builder...")
    AppWindow().run()

if __name__ == "__main__":
    main()
