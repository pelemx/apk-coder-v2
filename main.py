import sys
import os

# Add the project root to sys.path so that absolute imports work correctly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import AppWindow

def main():
    print("Starting JuprisX Pygame Agentic Desktop...")
    app = AppWindow()
    app.run()

if __name__ == "__main__":
    main()
