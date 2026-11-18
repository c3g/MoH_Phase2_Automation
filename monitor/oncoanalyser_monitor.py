#!/usr/bin/env python3

import fnmatch
import glob
import subprocess
import threading
import time
import os
import logging
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

logging.basicConfig(format='%(levelname)s: %(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DIR_PATTERN = "/project/60007/MOH_PHASE2/MoHQ-*/MoHQ-*/results/pipeline_info"
FILE_PATTERN = "execution_report_*.html"
COMMAND = ["~/MoH_Phase2_Automation/analysis/onanalyser_post_run.sh"]   # parent folder appended as last argument
POLL_INTERVAL = 300       # how often watchdog stats files in watched dirs (s)
RESCAN_INTERVAL = 600     # how often to glob for new/removed dirs (s)
DEBOUNCE_SECONDS = 5


class ReportHandler(FileSystemEventHandler):
    def __init__(self):
        self._timers = {}
        self._lock = threading.Lock()

    def schedule_file(self, path):
        if not fnmatch.fnmatch(Path(path).name, FILE_PATTERN):
            return
        with self._lock:
            old = self._timers.pop(path, None)
            if old:
                old.cancel()
            t = threading.Timer(DEBOUNCE_SECONDS, self._run, args=(path,))
            self._timers[path] = t
            t.start()

    def _run(self, path):
        with self._lock:
            self._timers.pop(path, None)
        group_dir = os.path.dirname(os.path.dirname(os.path.dirname(path)))
        logger.info(f"{time.strftime('%F %T')} triggering for {group_dir}")
        try:
            COMMAND.append([group_dir])
            subprocess.run(COMMAND, check=True)
        except subprocess.CalledProcessError as e:
            logger.info(f"Command failed ({e.returncode}) for {group_dir}")

    def on_created(self, event):
        if not event.is_directory:
            self.schedule_file(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.schedule_file(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self.schedule_file(event.dest_path)


if __name__ == "__main__":
    observer = PollingObserver(timeout=POLL_INTERVAL)
    handler = ReportHandler()
    observer.start()

    watched = {}   # dir -> ObservedWatch
    try:
        while True:
            current = set(glob.glob(DIR_PATTERN))

            for d in current - watched.keys():
                watched[d] = observer.schedule(handler, d, recursive=False)

            for d in watched.keys() - current:
                observer.unschedule(watched.pop(d))

            time.sleep(RESCAN_INTERVAL)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
