#!/usr/bin/env python3
#coding:utf-8

# File        : idm/server.py
# Author      : Hadi Cahyadi <cumulus13@gmail.com>
# Description : Agent server for pyidm. Receives links over HTTP/JSON and forwards
#               them to Internet Download Manager through the COM interface
#               (IDMan.download). Also contains the client used by `idm --agent`.
# Repo        : https://github.com/cumulus13/pyidm

import collections
import hmac
import json
import os
import queue
import socket
import sys
import threading
import time
import uuid
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

try:
    from .webui import INDEX_HTML
    from .watcher import is_final, FINAL_STATES, LogWatcher
except ImportError:  # script mode
    from webui import INDEX_HTML
    from watcher import is_final, FINAL_STATES, LogWatcher

def default_jobs_file():
    """%APPDATA%\\pyidm\\jobs.json on Windows, ~/.pyidm/jobs.json elsewhere."""
    appdata = os.getenv('APPDATA')
    if sys.platform == 'win32' and appdata:
        return os.path.join(appdata, 'pyidm', 'jobs.json')
    return os.path.join(os.path.expanduser('~'), '.pyidm', 'jobs.json')


# only these request options are written to disk: never passwords, cookies, post data or user names
PERSIST_OPTS = ('path', 'output', 'add_only')

DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 8899
MAX_BODY = 1024 * 1024
MAX_URLS = 500
ALLOWED_SCHEMES = ('http', 'https', 'ftp')
LOOPBACK = ('127.0.0.1', 'localhost', '::1')

# JSON field -> IDMan.download() keyword
FIELD_MAP = {
    'path': 'path_to_save',
    'output': 'output',
    'referrer': 'referrer',
    'cookie': 'cookie',
    'post_data': 'postData',
    'username': 'user',
    'password': 'password',
    'confirm': 'confirm',
    'user_agent': 'user_agent',
    'add_only': 'add_only',
}
STR_FIELDS = ('path', 'output', 'referrer', 'username', 'password', 'user_agent')
STR_OR_DICT_FIELDS = ('cookie', 'post_data')
BOOL_FIELDS = ('confirm', 'add_only')


class AgentError(Exception):
    def __init__(self, message, code=None):
        super(AgentError, self).__init__(message)
        self.code = code          # HTTP status when the agent answered, None for network errors


def _clean_url(value):
    value = str(value).strip()
    parsed = urlparse(value)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES or not parsed.netloc:
        return None
    return value


def _parse_payload(data, force_add=False):
    """Validate request body. Returns (urls, opts) or raises ValueError."""
    if not isinstance(data, dict):
        raise ValueError('body must be a JSON object')

    raw = []
    if data.get('url') is not None:
        raw.append(data['url'])
    urls_field = data.get('urls')
    if urls_field is not None:
        if not isinstance(urls_field, list):
            raise ValueError('"urls" must be a list')
        raw.extend(urls_field)
    if not raw:
        raise ValueError('no "url" or "urls" given')
    if len(raw) > MAX_URLS:
        raise ValueError('too many urls (max %d)' % MAX_URLS)

    urls, invalid = [], []
    for item in raw:
        cleaned = _clean_url(item) if isinstance(item, str) else None
        if cleaned:
            urls.append(cleaned)
        else:
            invalid.append(str(item)[:200])
    if invalid:
        raise ValueError('invalid url (only http/https/ftp): %s' % ', '.join(invalid[:5]))

    opts = {}
    for key in FIELD_MAP:
        val = data.get(key)
        if val is None or val == '':
            continue
        if key in STR_FIELDS and not isinstance(val, str):
            raise ValueError('"%s" must be a string' % key)
        if key in STR_OR_DICT_FIELDS and not isinstance(val, (str, dict)):
            raise ValueError('"%s" must be a string or object' % key)
        if key in BOOL_FIELDS and not isinstance(val, bool):
            raise ValueError('"%s" must be true/false' % key)
        opts[key] = val
    if force_add:
        opts['add_only'] = True
    return urls, opts


class AgentServer(object):
    """HTTP agent. All COM calls are done on ONE worker thread (COM is thread-affine)."""

    def __init__(self, downloader, host=DEFAULT_HOST, port=DEFAULT_PORT, token=None,
                 defaults=None, history=200, verbose=False, watcher=None, webui=True, job_ttl=3600, jobs_file=None):
        if host not in LOOPBACK and not token:
            raise ValueError('Refusing to listen on %s without a token (use --token or PYIDM_TOKEN)' % host)
        self.downloader = downloader
        self.host = host
        self.port = int(port)
        self.token = token or None
        self.defaults = {k: v for k, v in (defaults or {}).items() if v not in (None, '')}
        self.history = history
        self.verbose = verbose
        self.watcher = watcher
        self.webui = webui
        self.job_ttl = job_ttl      # seconds a finished/failed job stays listed (0 = until removed)
        self.queue = queue.Queue()
        self.jobs = collections.OrderedDict()
        self.lock = threading.Lock()
        self.httpd = None
        self.worker = None
        self.sweeper = None
        self._stop_evt = threading.Event()
        self.jobs_file = jobs_file or None          # None = keep jobs in memory only
        self._dirty = False
        self._save_lock = threading.Lock()
        self._started_at = time.time()
        self.restored = 0
        if self.jobs_file:
            self._load()

    # ---- jobs -------------------------------------------------------------
    def submit(self, urls, opts):
        ids = []
        with self.lock:
            for url in urls:
                job = {'id': uuid.uuid4().hex[:12], 'url': url, 'opts': opts,
                       'status': 'queued', 'error': None, 'time': time.time(), 'started': None,
                       'final': None, 'ended': None}
                self.jobs[job['id']] = job
                ids.append(job['id'])
                self.queue.put(job)
            while len(self.jobs) > self.history:
                self.jobs.popitem(last=False)
        self.expire()
        self.save()
        return ids

    def expire(self):
        """Drop finished jobs older than job_ttl."""
        if not self.job_ttl:
            return
        now = time.time()
        with self.lock:
            gone = [j for j, job in self.jobs.items() if job['ended'] and now - job['ended'] > self.job_ttl]
            for jid in gone:
                self.jobs.pop(jid, None)
            if gone:
                self._dirty = True

    # ---- persistence ------------------------------------------------------
    def save(self):
        """Write the job list atomically (temp file + replace). Never raises."""
        if not self.jobs_file:
            return
        with self._save_lock:
            with self.lock:
                self._dirty = False
                data = {'version': 1, 'saved': time.time(), 'jobs': [
                    {'id': j['id'], 'url': j['url'], 'status': j['status'], 'error': j['error'],
                     'time': j['time'], 'started': j['started'], 'final': j['final'], 'ended': j['ended'],
                     'opts': {k: v for k, v in j['opts'].items() if k in PERSIST_OPTS}}
                    for j in self.jobs.values()]}
            tmp = self.jobs_file + '.tmp'
            try:
                folder = os.path.dirname(self.jobs_file)
                if folder and not os.path.isdir(folder):
                    os.makedirs(folder)
                with open(tmp, 'w', encoding='utf-8') as fh:
                    json.dump(data, fh)
                if os.name == 'posix':
                    os.chmod(tmp, 0o600)
                os.replace(tmp, self.jobs_file)
            except OSError as e:
                self._dirty = True
                if self.verbose:
                    sys.stderr.write('cannot save %s: %s\n' % (self.jobs_file, e))

    def _load(self):
        try:
            with open(self.jobs_file, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            items = data['jobs']
        except FileNotFoundError:
            return
        except (OSError, ValueError, KeyError, TypeError):
            try:                                      # unreadable: keep it for inspection, start clean
                os.replace(self.jobs_file, self.jobs_file + '.bad')
            except OSError:
                pass
            return
        now = time.time()
        for it in items[-self.history:]:
            try:
                job = {'id': str(it['id']), 'url': str(it['url']), 'opts': dict(it.get('opts') or {}),
                       'status': it.get('status') or 'done', 'error': it.get('error'), 'time': float(it.get('time') or now),
                       'started': it.get('started'), 'final': it.get('final'), 'ended': it.get('ended'),
                       'restored': now}
            except (KeyError, TypeError, ValueError):
                continue
            if job['status'] in ('queued', 'running'):
                # the agent died before / while sending: never resend automatically (could download twice)
                job['status'] = 'interrupted'
                job['error'] = 'agent stopped before the link was confirmed sent; check IDM, resend if needed'
                job['ended'] = now
            self.jobs[job['id']] = job
        self.restored = len(self.jobs)

    def _unfinished_span(self):
        """Seconds back to the oldest job whose download is still unresolved (for the watcher's start window)."""
        now = time.time()
        starts = [j['started'] for j in self.jobs.values()
                  if j['status'] == 'done' and not j['final'] and j.get('started')]
        return int(now - min(starts)) + 60 if starts else 0

    def _sweep(self):
        """Remember final states while IDM's log is still readable (job_view caches 'complete'/'removed'),
        and expire old finished jobs, even when nobody is looking at the web page."""
        while not self._stop_evt.wait(1.0):
            try:
                with self.lock:
                    for job in self.jobs.values():
                        if job['status'] == 'done' and not job['final']:
                            before = (job['final'], job['ended'])
                            view = self.job_view(job)
                            if (job['final'], job['ended']) != before:
                                self._dirty = True
                            elif job.get('restored') and view['download'] is None and not job['ended'] \
                                    and time.time() - self._started_at > 60:
                                # restored job, 60 s after start no log and no output file: cannot know
                                job['final'] = {'state': 'lost', 'speed': None, 'downloaded': None, 'saveas': None,
                                                'log': None, 'updated': time.time()}
                                job['ended'] = time.time()
                                self._dirty = True
                self.expire()
                if self._dirty:
                    self.save()
            except Exception:
                pass

    def job_view(self, job):
        """status = result of handing the link to IDM; state = what IDM does with it (needs the log watcher)."""
        download = job['final']      # 'complete' / 'removed' are remembered: IDM deletes its log files
        if download is None and self.watcher is not None and job['status'] == 'done' and job.get('started'):
            found = self.watcher.find(job['url'], since=job['started'])
            if found:
                download = {k: found.get(k) for k in ('state', 'speed', 'downloaded', 'saveas', 'log', 'updated')}
                if download['state'] in ('complete', 'removed'):
                    job['final'] = download
                    job['ended'] = time.time()
                    self._dirty = True
        add_only = job['opts'].get('add_only', self.defaults.get('add_only', False))
        if download is None and job['status'] == 'done' and job.get('started') and not add_only \
                and time.time() - job['started'] > 3:
            # tiny downloads: IDM may create and delete its log between two polls, so the watcher never
            # saw it. Fall back to the file on disk (save path + output name or the url's file name).
            probe = self._probe_output(job)
            if probe:
                download = {'state': 'complete', 'speed': None, 'downloaded': probe[1], 'saveas': probe[0],
                            'log': None, 'updated': time.time()}
                job['final'] = download
                job['ended'] = time.time()
                self._dirty = True
        if self.watcher is None and job['status'] == 'done' and not job['ended']:
            job['ended'] = time.time()        # nothing will ever resolve it: let it expire
            self._dirty = True
        if job['status'] == 'interrupted':
            state = 'interrupted'
        elif job['status'] == 'failed':
            state = 'failed'
        elif job['status'] == 'queued':
            state = 'queued'
        elif job['status'] == 'running':
            state = 'sending'
        elif download and download['state'] != 'unknown':
            state = download['state']
        else:
            state = 'added' if add_only else 'sent'
        return {'id': job['id'], 'url': job['url'], 'status': job['status'], 'state': state,
                'error': job['error'], 'time': job['time'], 'download': download}

    def _probe_output(self, job):
        folder = job['opts'].get('path') or self.defaults.get('path')
        name = job['opts'].get('output') or os.path.basename(unquote(urlparse(job['url']).path))
        if not folder or not name:
            return None
        target = os.path.join(folder, name)
        if LogWatcher._output_exists({'saveas': target, 'created': job['started']}):
            try:
                return target, os.path.getsize(target)
            except OSError:
                return target, None
        return None

    def _set(self, job, status, error=None):
        with self.lock:
            job['status'] = status
            job['error'] = error
            self._dirty = True
            if status == 'failed':
                job['ended'] = time.time()

    def _run_worker(self):
        com = None
        try:
            import comtypes
            comtypes.CoInitialize()
            com = comtypes
        except Exception:
            pass
        try:
            while True:
                job = self.queue.get()
                if job is None:
                    break
                job['started'] = time.time()
                self._set(job, 'running')
                kwargs = {}
                merged = dict(self.defaults)
                merged.update(job['opts'])
                for key, val in merged.items():
                    kwargs[FIELD_MAP[key]] = val
                try:
                    ok = self.downloader.download(job['url'], **kwargs)
                except BaseException as e:
                    self._set(job, 'failed', '%s: %s' % (e.__class__.__name__, e))
                else:
                    if ok is False:
                        self._set(job, 'failed', getattr(self.downloader, 'last_error', None) or 'IDM rejected the link')
                    else:
                        self._set(job, 'done')
                if self.verbose:
                    sys.stderr.write('[job %s] %s %s\n' % (job['id'], job['status'], job['url']))
        finally:
            if com is not None:
                try:
                    com.CoUninitialize()
                except Exception:
                    pass

    # ---- lifecycle --------------------------------------------------------
    def serve(self):
        class _Server(ThreadingHTTPServer):
            daemon_threads = True
            address_family = socket.AF_INET6 if ':' in self.host else socket.AF_INET

        if self.watcher is not None and not self.watcher._thread:
            # logs of downloads that were running when the agent stopped must be re-read from the start
            self.watcher.recent = max(self.watcher.recent, self._unfinished_span())
            if not self.watcher.start():
                self.watcher = None
        self.httpd = _Server((self.host, self.port), _make_handler(self))
        self.worker = threading.Thread(target=self._run_worker, name='pyidm-com', daemon=True)
        self.worker.start()
        self.sweeper = threading.Thread(target=self._sweep, name='pyidm-sweep', daemon=True)
        self.sweeper.start()
        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        self._stop_evt.set()
        self.save()
        if self.httpd is not None:
            try:
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None
        self.queue.put(None)
        if self.worker is not None:
            self.worker.join(timeout=5)
            self.worker = None


def _make_handler(srv):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'pyidm-agent'
        protocol_version = 'HTTP/1.1'

        def log_message(self, fmt, *args):
            if srv.verbose:
                sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

        def _json(self, code, obj):
            body = json.dumps(obj).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def _html(self, text):
            body = text.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy',
                             "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                             "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self):
            if srv.token:
                got = self.headers.get('X-Token') or ''
                auth = self.headers.get('Authorization') or ''
                if auth.lower().startswith('bearer '):
                    got = auth[7:].strip()
                return hmac.compare_digest(got.encode('utf-8'), srv.token.encode('utf-8'))
            # No token (loopback only): block DNS rebinding (Host) and cross-site pages (Origin)
            host_header = (self.headers.get('Host') or '').lower()
            origin = self.headers.get('Origin')
            if origin and urlparse(origin).netloc.lower() != host_header:
                return False
            return host_header.rsplit(':', 1)[0].strip('[]') in LOOPBACK

        def do_GET(self):
            path = urlparse(self.path).path.rstrip('/') or '/'
            if path in ('/', '/ui') and srv.webui:
                return self._html(INDEX_HTML)
            if path == '/health':
                try:
                    from . import __version__ as ver
                    ver = getattr(ver, 'version', None)
                except Exception:
                    ver = None
                return self._json(200, {'status': 'ok', 'version': ver, 'pending': srv.queue.qsize(),
                                        'watcher': bool(srv.watcher and srv.watcher.available())})
            if not self._authorized():
                return self._json(401, {'error': 'unauthorized'})
            if path == '/downloads':
                items = srv.watcher.snapshot() if srv.watcher else []
                for item in items:
                    item['downloaded'] = item.get('downloaded')
                return self._json(200, {'watcher': bool(srv.watcher), 'downloads': [
                    {'url': i['url'], 'state': i['state'], 'speed': i['speed'], 'downloaded': i['downloaded'],
                     'saveas': i['saveas'], 'log': i['log'], 'updated': i['updated']} for i in items]})
            if path == '/jobs':
                with srv.lock:
                    items = [srv.job_view(j) for j in srv.jobs.values()]
                srv.expire()
                return self._json(200, {'jobs': items[::-1]})
            if path.startswith('/jobs/'):
                with srv.lock:
                    job = srv.jobs.get(path[6:])
                    view = srv.job_view(job) if job else None
                if view is None:
                    return self._json(404, {'error': 'job not found'})
                return self._json(200, view)
            return self._json(404, {'error': 'not found'})

        def do_DELETE(self):
            path = urlparse(self.path).path.rstrip('/')
            if not path.startswith('/jobs/'):
                return self._json(404, {'error': 'not found'})
            if not self._authorized():
                return self._json(401, {'error': 'unauthorized'})
            with srv.lock:
                job = srv.jobs.pop(path[6:], None)
            if job is None:
                return self._json(404, {'error': 'job not found'})
            srv.save()
            return self._json(200, {'removed': job['id']})

        def do_POST(self):
            path = urlparse(self.path).path.rstrip('/')
            if path not in ('/send', '/add', '/jobs/clear'):
                return self._json(404, {'error': 'not found'})
            if not self._authorized():
                return self._json(401, {'error': 'unauthorized'})
            if (self.headers.get('Content-Type') or '').split(';')[0].strip().lower() != 'application/json':
                return self._json(415, {'error': 'Content-Type must be application/json'})
            if path == '/jobs/clear':
                with srv.lock:
                    done = [j for j, job in srv.jobs.items() if job['ended']]
                    for j in done:
                        srv.jobs.pop(j, None)
                srv.save()
                return self._json(200, {'cleared': len(done)})
            try:
                length = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                return self._json(400, {'error': 'bad Content-Length'})
            if length <= 0:
                return self._json(411, {'error': 'Content-Length required'})
            if length > MAX_BODY:
                return self._json(413, {'error': 'body too large'})
            try:
                data = json.loads(self.rfile.read(length).decode('utf-8'))
                urls, opts = _parse_payload(data, force_add=(path == '/add'))
            except (ValueError, UnicodeDecodeError) as e:
                return self._json(400, {'error': str(e)})
            ids = srv.submit(urls, opts)
            return self._json(202, {'queued': len(ids), 'jobs': ids})

    return Handler


# ---- client ---------------------------------------------------------------
def _request(method, agent, path, payload=None, token=None, timeout=10):
    if '://' not in agent:
        agent = 'http://' + agent
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(agent.rstrip('/') + path, data=data, method=method, headers=headers)
    if token:
        req.add_header('X-Token', token)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode('utf-8')).get('error', e.reason)
        except Exception:
            msg = e.reason
        raise AgentError('Agent server replied HTTP %s: %s' % (e.code, msg), e.code)
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        raise AgentError('Cannot reach agent server %s: %s' % (agent, getattr(e, 'reason', e)))


def send(agent, urls, opts=None, token=None, endpoint='/send', timeout=10):
    """POST links to an agent server. `opts` keys: see FIELD_MAP. Returns decoded JSON."""
    payload = {k: v for k, v in (opts or {}).items() if k in FIELD_MAP and v is not None and v != ''}
    payload['urls'] = list(urls)
    return _request('POST', agent, endpoint, payload, token, timeout)


def get(agent, path, token=None, timeout=10):
    return _request('GET', agent, path, None, token, timeout)


def poll_jobs(agent, ids, token=None, timeout=3600, interval=2.0, grace=10.0):
    """Generator: yields a job view every time its state or downloaded bytes change, and once more when the
    job is final (complete, removed, failed, interrupted, lost; error/cancelled after `grace` s unchanged).
    Ends when every job is final or `timeout` seconds passed (0 = no limit). A job the agent no longer
    knows (expired / removed) is reported once as state 'removed' with status 'gone'."""
    tracked = bool(get(agent, '/health', token).get('watcher'))
    deadline = time.time() + timeout if timeout else None
    pending, seen = list(ids), {}
    while pending:
        for jid in list(pending):
            try:
                view = get(agent, '/jobs/' + jid, token)
            except AgentError as e:
                if e.code != 404:
                    raise
                pending.remove(jid)
                yield {'id': jid, 'url': None, 'status': 'gone', 'state': 'removed', 'download': None,
                       'error': 'job not found on the agent (expired or removed)', 'time': None}
                continue
            sig = (view['state'], (view.get('download') or {}).get('downloaded'))
            prev = seen.get(jid)
            changed = prev is None or prev[0] != sig
            if changed:
                seen[jid] = (sig, time.time() if prev is None or prev[0][0] != sig[0] else prev[1])
            done = (not tracked and view['state'] in ('sent', 'added')) or \
                is_final(view['state'], time.time() - seen[jid][1], grace)
            if changed or done:
                yield view
            if done:
                pending.remove(jid)
        if pending:
            if deadline and time.time() > deadline:
                return
            time.sleep(interval)


def wait_jobs(agent, ids, token=None, timeout=3600, interval=2.0, grace=10.0, on_change=None):
    """Block until every job is final. Returns (views_by_id, tracked).
    tracked is False when the agent has no IDM log watcher (completion cannot be known)."""
    tracked = bool(get(agent, '/health', token).get('watcher'))
    final, last = {}, {}
    for view in poll_jobs(agent, ids, token, timeout, interval, grace):
        final[view['id']] = view
        sig = (view['state'], (view.get('download') or {}).get('downloaded'))
        if last.get(view['id']) != sig:
            last[view['id']] = sig
            if on_change:
                on_change(view)
    return final, tracked


class AgentClient(object):
    """Small client for an agent server (any OS, standard library only).

        c = AgentClient("192.168.1.10:8899", token="SECRET")
        ids = c.send(["http://test.com/a.iso"], referrer="http://test.com")
        for view in c.poll(ids):                # live progress
            print(view["state"], view["download"])
    """

    def __init__(self, agent, token=None, timeout=10):
        self.agent = agent
        self.token = token
        self.timeout = timeout

    def health(self):
        return get(self.agent, '/health', self.token, self.timeout)

    def send(self, urls, **opts):
        """Send link(s) (str or list). Options: see FIELD_MAP. Returns the list of job ids."""
        if isinstance(urls, str):
            urls = [urls]
        return send(self.agent, urls, opts, self.token, '/send', self.timeout).get('jobs', [])

    def add(self, urls, **opts):
        """Like send() but only adds to IDM's queue (does not start)."""
        if isinstance(urls, str):
            urls = [urls]
        return send(self.agent, urls, opts, self.token, '/add', self.timeout).get('jobs', [])

    def job(self, job_id):
        """Current view of one job: {'id', 'url', 'status', 'state', 'error', 'download': {...} | None}."""
        return get(self.agent, '/jobs/' + job_id, self.token, self.timeout)

    def state(self, job_id):
        return self.job(job_id)['state']

    def jobs(self):
        return get(self.agent, '/jobs', self.token, self.timeout)['jobs']

    def downloads(self):
        """Every download the agent sees in IDM's log files (also ones not sent through the agent)."""
        return get(self.agent, '/downloads', self.token, self.timeout)['downloads']

    def remove(self, job_id):
        """Remove a job from the agent's list (IDM is not touched)."""
        return _request('DELETE', self.agent, '/jobs/' + job_id, None, self.token, self.timeout)

    def clear(self):
        """Remove all finished jobs from the agent's list. Returns how many."""
        return _request('POST', self.agent, '/jobs/clear', {}, self.token, self.timeout).get('cleared', 0)

    def poll(self, job_ids, interval=2.0, timeout=3600, grace=10.0):
        """Generator of job views on every change until all jobs are final. See poll_jobs()."""
        return poll_jobs(self.agent, job_ids, self.token, timeout, interval, grace)

    def wait(self, job_ids, timeout=3600, interval=2.0, on_change=None):
        """Block until all jobs are final. Returns {job_id: view}."""
        return wait_jobs(self.agent, job_ids, self.token, timeout, interval, on_change=on_change)[0]
