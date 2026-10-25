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
import queue
import socket
import sys
import threading
import time
import uuid
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

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
    pass


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
                 defaults=None, history=200, verbose=False):
        if host not in LOOPBACK and not token:
            raise ValueError('Refusing to listen on %s without a token (use --token or PYIDM_TOKEN)' % host)
        self.downloader = downloader
        self.host = host
        self.port = int(port)
        self.token = token or None
        self.defaults = {k: v for k, v in (defaults or {}).items() if v not in (None, '')}
        self.history = history
        self.verbose = verbose
        self.queue = queue.Queue()
        self.jobs = collections.OrderedDict()
        self.lock = threading.Lock()
        self.httpd = None
        self.worker = None

    # ---- jobs -------------------------------------------------------------
    def submit(self, urls, opts):
        ids = []
        with self.lock:
            for url in urls:
                job = {'id': uuid.uuid4().hex[:12], 'url': url, 'opts': opts,
                       'status': 'queued', 'error': None, 'time': time.time()}
                self.jobs[job['id']] = job
                ids.append(job['id'])
                self.queue.put(job)
            while len(self.jobs) > self.history:
                self.jobs.popitem(last=False)
        return ids

    def job_view(self, job):
        return {'id': job['id'], 'url': job['url'], 'status': job['status'],
                'error': job['error'], 'time': job['time']}

    def _set(self, job, status, error=None):
        with self.lock:
            job['status'] = status
            job['error'] = error

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

        self.httpd = _Server((self.host, self.port), _make_handler(self))
        self.worker = threading.Thread(target=self._run_worker, name='pyidm-com', daemon=True)
        self.worker.start()
        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
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
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self):
            if srv.token:
                got = self.headers.get('X-Token') or ''
                auth = self.headers.get('Authorization') or ''
                if auth.lower().startswith('bearer '):
                    got = auth[7:].strip()
                return hmac.compare_digest(got.encode('utf-8'), srv.token.encode('utf-8'))
            # No token (loopback only): block browsers / DNS rebinding
            if self.headers.get('Origin'):
                return False
            host = (self.headers.get('Host') or '').rsplit(':', 1)[0].strip('[]').lower()
            return host in LOOPBACK

        def do_GET(self):
            path = urlparse(self.path).path.rstrip('/') or '/'
            if path == '/health':
                try:
                    from . import __version__ as ver
                except Exception:
                    ver = None
                return self._json(200, {'status': 'ok', 'version': ver, 'pending': srv.queue.qsize()})
            if not self._authorized():
                return self._json(401, {'error': 'unauthorized'})
            if path == '/jobs':
                with srv.lock:
                    items = [srv.job_view(j) for j in srv.jobs.values()]
                return self._json(200, {'jobs': items[::-1]})
            if path.startswith('/jobs/'):
                with srv.lock:
                    job = srv.jobs.get(path[6:])
                    view = srv.job_view(job) if job else None
                if view is None:
                    return self._json(404, {'error': 'job not found'})
                return self._json(200, view)
            return self._json(404, {'error': 'not found'})

        def do_POST(self):
            path = urlparse(self.path).path.rstrip('/')
            if path not in ('/send', '/add'):
                return self._json(404, {'error': 'not found'})
            if not self._authorized():
                return self._json(401, {'error': 'unauthorized'})
            if (self.headers.get('Content-Type') or '').split(';')[0].strip().lower() != 'application/json':
                return self._json(415, {'error': 'Content-Type must be application/json'})
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
def send(agent, urls, opts=None, token=None, endpoint='/send', timeout=10):
    """POST links to an agent server. `opts` keys: see FIELD_MAP. Returns decoded JSON."""
    if '://' not in agent:
        agent = 'http://' + agent
    payload = {k: v for k, v in (opts or {}).items() if k in FIELD_MAP and v is not None and v != ''}
    payload['urls'] = list(urls)
    req = urllib.request.Request(
        agent.rstrip('/') + endpoint,
        data=json.dumps(payload).encode('utf-8'),
        method='POST',
        headers={'Content-Type': 'application/json'},
    )
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
        raise AgentError('Agent server replied HTTP %s: %s' % (e.code, msg))
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        raise AgentError('Cannot reach agent server %s: %s' % (agent, getattr(e, 'reason', e)))
