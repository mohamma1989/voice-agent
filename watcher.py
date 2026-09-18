import time
import subprocess
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

WATCH_FILE = "task.py"
PROJECT_DIR = os.path.abspath("./test-project")

class ExecutionHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_run = 0

    def on_modified(self, event):
        if not event.is_directory and os.path.basename(event.src_path) == WATCH_FILE:
            # Debounce rapid file writes
            if time.time() - self.last_run < 1:
                return
            self.last_run = time.time()

            print(f"\n[⚡ DETECTED] {WATCH_FILE} modified! Executing inside {PROJECT_DIR}...")
            
            # Run the newly generated script inside test-project/
            result = subprocess.run(
                ["python3", os.path.abspath(WATCH_FILE)],
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True
            )

            if result.stdout:
                print(f"[STDOUT]:\n{result.stdout.strip()}")
            if result.stderr:
                print(f"[STDERR]:\n{result.stderr.strip()}")
            print("-" * 50)

if __name__ == "__main__":
    # Ensure task.py exists
    if not os.path.exists(WATCH_FILE):
        with open(WATCH_FILE, "w") as f:
            f.write("# Pending voice command\n")

    event_handler = ExecutionHandler()
    observer = Observer()
    observer.schedule(event_handler, path=".", recursive=False)
    observer.start()
    print(f"[*] Watching '{WATCH_FILE}' for changes. Press Ctrl+C to exit.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
