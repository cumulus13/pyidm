#!/usr/bin/env python3
#coding:utf-8

# File        : idm/watcher.py
# Author      : Hadi Cahyadi <cumulus13@gmail.com>
# Description : Tracks IDM download state (added / downloading / complete / error / cancelled)
#               by tailing IDM's own log files in %APPDATA%\IDM\DwnlData\<USERNAME>.
#               COM (SendLinkToIDM2) only hands a link over to IDM, it never reports back,
#               so the log files are the only source of truth. Standard library only.
# Repo        : https://github.com/cumulus13/pyidm

import collections
import getpass
import os
import re
import threading
import time
from urllib.parse import unquote

FINAL_STATES = ('complete', 'error', 'cancelled', 'failed')

RE_URL = re.compile(r'Url ((?:https?|ftp)://\S+)')
RE_SAVEAS = re.compile(r'to file (.+)')
RE_PROGRESS = re.compile(r'time (\d+), speed (\d+), downl (\d+)')

EVENT_STATE = {
    'adding': 'added',
    'downloading': 'downloading',
    'download_complete': 'complete',
    'rebuilding_complete': 'complete',
    'rename': 'finishing',
    'deleting': 'finishing',
    'last_chunk': 'finishing',
    'connecting': 'connecting',
    'cancel': 'cancelled',
}


def default_log_dir():
    appdata = os.getenv('APPDATA') or ''
    if not appdata:
        return ''
    user = os.getenv('USERNAME') or ''
    if not user:
        try:
            user = getpass.getuser()
        except Exception:
            return ''
    return os.path.join(appdata, 'IDM', 'DwnlData', user)


def normalize_url(url):
    return unquote(str(url).strip()).split('#', 1)[0].rstrip('/').lower()


def is_final(state, stable_for=0.0, grace=10.0):
    """'complete'/'failed' are final at once. 'error'/'cancelled' only when they stayed
    unchanged for `grace` seconds (IDM logs some of those lines during normal retries)."""
    if state in ('complete', 'failed'):
        return True
    if state in ('error', 'cancelled'):
        return stable_for >= grace
    return False


class LogWatcher(object):
    """Background thread that tails IDM log files and keeps one status dict per log file."""

    def __init__(self, log_dir=None, interval=1.0, recent=300, max_items=500):
        self.log_dir = log_dir or default_log_dir()
        self.interval = interval
        self.recent = recent          # at start only logs touched within N seconds are parsed
        self.max_items = max_items
        self._items = collections.OrderedDict()   # path -> status
        self._lines = {}                          # path -> deque of recent lines
        self._pos = {}
        self._history = set()                     # logs skipped at start (re-read once if they grow)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    # ---- lifecycle --------------------------------------------------------
    def available(self):
        return bool(self.log_dir) and os.path.isdir(self.log_dir)

    def start(self):
        if not self.available():
            return False
        if self._thread is not None:
            return True
        self.scan(initial=True)
        self._thread = threading.Thread(target=self._run, name='pyidm-watcher', daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                self.scan()
            except Exception:
                pass

    # ---- scanning ---------------------------------------------------------
    def scan(self, initial=False):
        now = time.time()
        for root, _dirs, files in os.walk(self.log_dir):
            for name in files:
                if not name.endswith('.log'):
                    continue
                path = os.path.join(root, name)
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                pos = self._pos.get(path)
                if pos is None:
                    if initial and now - st.st_mtime > self.recent:
                        self._pos[path] = st.st_size
                        self._history.add(path)
                        continue
                    pos = 0
                elif path in self._history and st.st_size > pos:
                    self._history.discard(path)
                    pos = 0
                if st.st_size < pos:
                    pos = 0
                    with self._lock:
                        self._items.pop(path, None)
                        self._lines.pop(path, None)
                if st.st_size == pos:
                    self._pos[path] = pos
                    continue
                try:
                    with open(path, 'rb') as fh:
                        fh.seek(pos)
                        data = fh.read()
                except OSError:
                    continue
                if now - st.st_mtime >= 2:
                    chunk = data                       # file is idle: take a last line without newline too
                else:
                    end = data.rfind(b'\n')
                    chunk = data[:end + 1] if end >= 0 else b''
                if not chunk:
                    continue
                self._pos[path] = pos + len(chunk)
                text = chunk.decode('utf-8', errors='replace').lstrip('\ufeff')
                self._apply(path, st, text.splitlines())

    def _apply(self, path, st, lines):
        with self._lock:
            s = self._items.get(path)
            if s is None:
                s = {'log': os.path.basename(path), 'url': None, 'saveas': None, 'state': 'unknown',
                     'event': None, 'time': None, 'speed': None, 'downloaded': None,
                     'complete': False, 'error': False, 'cancelled': False, 'retrying': False,
                     'created': st.st_ctime, 'updated': st.st_mtime}
                self._items[path] = s
                while len(self._items) > self.max_items:
                    old = next(iter(self._items))
                    self._items.pop(old, None)
                    self._lines.pop(old, None)
            recent = self._lines.setdefault(path, collections.deque(maxlen=20))
            changed = False
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                changed = True
                recent.append(line)
                m = RE_URL.search(line)
                if m:
                    s['url'] = m.group(1)
                m = RE_SAVEAS.search(line)
                if m:
                    s['saveas'] = m.group(1).strip()
                if 'downl ' in line:
                    if s['complete']:
                        continue
                    m = RE_PROGRESS.search(line)
                    if m:
                        s['time'], s['speed'], s['downloaded'] = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    s['cancelled'] = False
                    s['event'] = 'downloading'
                elif 'Download complete.' in line:
                    s['complete'] = True
                    s['event'] = 'download_complete'
                elif 'Rebuilding complete' in line:
                    s['complete'] = True
                    s['event'] = 'rebuilding_complete'
                elif 'Rename temp file' in line:
                    s['event'] = 'rename'
                elif 'Deleting temp' in line:
                    s['event'] = 'deleting'
                elif 'Adding file ' in line:
                    s['event'] = 'adding'
                    s['cancelled'] = False
                elif 'Connecting...' in line:
                    s['event'] = 'connecting'
                    s['cancelled'] = False
                elif 'This is the last chunk. End rebuilding.' in line:
                    s['event'] = 'last_chunk'
                elif 'Cancel by user.' in line:
                    s['cancelled'] = True
                    s['complete'] = False
                    s['event'] = 'cancel'
            if not changed:
                return
            if s['complete']:
                s['error'] = False
                s['retrying'] = False
                s['cancelled'] = False
            else:
                s['error'] = any('This is the last chunk' in l for l in recent)
                s['retrying'] = any('Connecting...' in l for l in recent)
            if s['complete']:
                s['state'] = 'complete'
            elif s['cancelled']:
                s['state'] = 'cancelled'
            elif s['error']:
                s['state'] = 'error'
            elif s['retrying']:
                s['state'] = 'connecting'
            else:
                s['state'] = EVENT_STATE.get(s['event'], 'unknown')
            s['updated'] = time.time()

    # ---- queries ----------------------------------------------------------
    def snapshot(self):
        with self._lock:
            items = [dict(s) for s in self._items.values()]
        items.sort(key=lambda s: s['updated'], reverse=True)
        return items

    def find(self, url, since=None):
        """Most recently updated log for `url` with activity after `since` (epoch seconds)."""
        key = normalize_url(url)
        best = None
        with self._lock:
            for s in self._items.values():
                if not s['url'] or normalize_url(s['url']) != key:
                    continue
                if since is not None and s['updated'] < since - 5:
                    continue
                if best is None or s['updated'] > best['updated']:
                    best = s
            return dict(best) if best else None

    def wait_final(self, url, since=None, timeout=3600, grace=10.0, interval=1.0, on_change=None):
        """Block until the download of `url` is final. Returns the last status (or None)."""
        deadline = time.time() + timeout if timeout else None
        last_sig, state_since, status = None, time.time(), None
        while True:
            status = self.find(url, since)
            if status:
                sig = (status['state'], status['downloaded'])
                if sig != last_sig:
                    if status['state'] != (last_sig or (None,))[0]:
                        state_since = time.time()
                    last_sig = sig
                    if on_change:
                        on_change(status)
                if is_final(status['state'], time.time() - state_since, grace):
                    return status
            if deadline and time.time() > deadline:
                return status
            time.sleep(interval)
