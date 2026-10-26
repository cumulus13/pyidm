#!/usr/bin/env python3
#coding:utf-8

# File        : idm/idm.py
# Author      : Hadi Cahyadi <cumulus13@gmail.com>
# Created     : 04/22/19
# Description : command line to download with Internet Download Manager (IDM) on Windows OS
# Repo        : https://github.com/cumulus13/pyidm
# License     : MIT

import os
from envdot import load_env  # type: ignore
load_env()

LOG_LEVEL = os.getenv("PYIDM_LOG_LEVEL", 'CRITICAL')

import logging
logging.getLogger('ctypes').setLevel(getattr(logging, LOG_LEVEL))

import sys
import traceback
import argparse
from pathlib import Path
from make_colors import make_colors  # type: ignore
import signal

import time

try:
    from .server import AgentServer, AgentError, send as agent_send, wait_jobs as agent_wait, DEFAULT_HOST, DEFAULT_PORT, default_jobs_file
    from .watcher import LogWatcher, is_final
except ImportError:
    from server import AgentServer, AgentError, send as agent_send, wait_jobs as agent_wait, DEFAULT_HOST, DEFAULT_PORT, default_jobs_file
    from watcher import LogWatcher, is_final

if str(os.getenv('DEBUG', "0")).lower() in ("1", "true", "ok", "yes", "on"):
    try:
        from pydebugger.debug import debug
    except:
        def debug(*args, **kwargs):
            return     
else:
    def debug(*args, **kwargs):
        return 

class IDMNotFound(Exception):
    pass

class OSNotSupport(Exception):
    pass

# COM (local IDM) exists on Windows only. Everywhere else this module still imports fine and
# the CLI works as an agent client:  idm -A http://HOST:8899 URL
IS_WINDOWS = sys.platform == 'win32'
COM_ERROR = None
cc = comtypes = automation = windll = wintypes = create_unicode_buffer = None
if IS_WINDOWS:
    try:
        import comtypes.client as cc
        import comtypes
        from comtypes import automation, windll
        from ctypes import wintypes, create_unicode_buffer
    except ImportError as _e:
        COM_ERROR = "COM support is not installed ({}). Run: pip install comtypes pywin32".format(_e)
else:
    COM_ERROR = ("Local IDM (COM) is only available on Windows (this is '{}'). "
                 "Send links to an agent server instead: idm -A http://HOST:8899 URL".format(sys.platform))


class IDMan(object):
    PID = os.getpid()
    last_error = None
    CONFIGFILE = str(Path(__file__).parent / 'idm.ini')
    CONFIG = load_env(CONFIGFILE)
    
    def __init__(self):
        super(IDMan, self)
        self.tlb = None
        if IS_WINDOWS:
            self.tlb = r'c:\Program Files\Internet Download Manager\idmantypeinfo.tlb'
            if not os.path.isfile(self.tlb):
                self.tlb = r'c:\Program Files (x86)\Internet Download Manager\idmantypeinfo.tlb'
            if not os.path.isfile(self.tlb):
                self.tlb = None

    def _require_com(self):
        """Raise unless local IDM (COM) can be used. Agent client mode never needs this."""
        if COM_ERROR:
            raise OSNotSupport(make_colors(COM_ERROR, 'lw', 'r'))
        if not self.tlb:
            raise IDMNotFound(make_colors("It seem IDM (Internet Download Manager) not installed, please install first !", 'lw', 'r'))

    def get_from_clipboard(self):
        try:
            import clipboard
        except ImportError:
            print("Module 'clipboard' not Installer yet, please install first [pip install clipboard]")
            q = input("Please re-input url download [q=quit/x=exit]: ")
            if not q:
                sys.exit("You not input URL Download !")
            elif  q and q.lower() in ('q', 'exit', 'quit', 'q'):
                sys.exit("quit ...")
            else:
                return q
        return clipboard.paste()

    def download(self, link, path_to_save=None, output=None, referrer=None, cookie=None, postData=None, user=None, password=None, confirm=False, user_agent=None, add_only=False, clip=False):
        
        self._require_com()
        lflag = 5
        
        if clip or link == 'c':
            link = self.get_from_clipboard()
        if confirm:
            lflag = 0
        elif add_only:
            lflag = 2
        else:
            lflag = 1
        try:
            cc.GetModule(['{ECF21EAB-3AA8-4355-82BE-F777990001DD}', 1, 0])
        except:
            cc.GetModule(self.tlb)

        try:
            import comtypes.gen.IDManLib as idman
        except ImportError:
            raise IDMNotFound(make_colors("Please install 'Internet Download Manager' first !", 'lw', 'r'))
        idman1 = cc.CreateObject(idman.CIDMLinkTransmitter, None, None, idman.ICIDMLinkTransmitter2)  # type: ignore
        if path_to_save:
            path_to_save = os.path.realpath(path_to_save)
        #if isinstance(postData, dict):
            #postData = '\n'.join([f'{key}: {value}' for key, value in postData.items()])
        if isinstance(cookie, dict):
            cookie = '; '.join([f'{key}={value}' for key, value in cookie.items()])
        
        if isinstance(postData, dict):
            postData = '\n'.join([f'{key}={value}' for key, value in postData.items()])
        
        reserved1 = automation.VARIANT()
        if user_agent:
            reserved1.vt = automation.VT_BSTR
            reserved1.value = user_agent
        else:
            reserved1.vt = automation.VT_EMPTY
        
        # Prepare reserved2 (not used)
        reserved2 = automation.VARIANT()
        reserved2.vt = automation.VT_EMPTY
        
        #idman1.SendLinkToIDM(link, referrer, cookie, postData, user, password, path_to_save, output, lflag)
        self.last_error = None
        try:
            idman1.SendLinkToIDM2(link, referrer, cookie, postData, user, password, path_to_save, output, lflag, reserved1, reserved2)
        except Exception as e:
            self.last_error = str(e)
            print("Error: {}".format(make_colors(str(e), 'lw', 'r')))
            return False
        else:
            if not self.CONFIG.get_config('DEBUG_VERBOSE') == False: print("\n", make_colors("Link sent to IDM successfully.", 'b', 'y'))
            return True

    def _cfg(self, name, default=None):
        try:
            val = self.CONFIG.get_config(name)
        except Exception:
            return default
        if val is None or val is False or val == '':
            return default
        return val

    def _flag(self, name):
        """True only for an explicit truthy config value (empty/unset = False)."""
        try:
            val = self.CONFIG.get_config(name)
        except Exception:
            return False
        return bool(val) and str(val).strip().lower() not in ('0', 'false', 'no', 'off')

    def expand_urls(self, urls):
        """'c' -> clipboard content, existing file -> one link per line, otherwise as is."""
        out = []
        for item in urls:
            if item == 'c':
                text = self.get_from_clipboard()
                lines = str(text or '').splitlines()
            elif os.path.isfile(item):
                with open(item, 'r', encoding='utf-8', errors='ignore') as fh:
                    lines = fh.read().splitlines()
            else:
                lines = [item]
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    out.append(line)
        return out

    def serve(self, host=None, port=None, token=None, verbose=False, webui=True, watcher=True, log_dir=None, jobs_file=None, persist=True):
        try:
            self._require_com()
        except (OSNotSupport, IDMNotFound) as e:
            sys.exit(str(e))
        host = host or self._cfg('SERVER_HOST') or DEFAULT_HOST
        try:
            port = int(port or self._cfg('SERVER_PORT') or DEFAULT_PORT)
        except ValueError:
            sys.exit(make_colors("INVALID port !", 'lw', 'r'))
        token = token or os.getenv('PYIDM_TOKEN') or self._cfg('SERVER_TOKEN')
        defaults = {
            'path': self._cfg('DOWNLOAD_PATH'),
            'confirm': True if self._cfg('DOWNLOAD_CONFIRM') else None,
            'user_agent': self._cfg('DATA_USER_AGENT'),
        }
        log_watcher = None
        if watcher and not self._flag('WATCHER_DISABLE'):
            try:
                interval = float(self._cfg('WATCHER_INTERVAL') or 0.5)
            except (TypeError, ValueError):
                interval = 0.5
            log_watcher = LogWatcher(log_dir=log_dir or self._cfg('WATCHER_LOG_DIR'), interval=interval)
            if not log_watcher.available():       # started by AgentServer.serve() after the saved jobs are restored
                print(make_colors("IDM log directory not found ({}): download completion tracking is off".format(
                    log_watcher.log_dir or 'unknown'), 'ly'))
                log_watcher = None
        webui = webui and not self._flag('SERVER_NO_WEBUI')
        try:
            try:
                job_ttl = int(self._cfg('SERVER_JOB_TTL', 3600))
            except (TypeError, ValueError):
                job_ttl = 3600
            jobs_path = None
            if persist and not self._flag('SERVER_NO_PERSIST'):
                jobs_path = jobs_file or self._cfg('SERVER_JOBS_FILE') or default_jobs_file()
            srv = AgentServer(self, host, port, token, defaults=defaults, verbose=verbose, watcher=log_watcher,
                              webui=webui, job_ttl=job_ttl, jobs_file=jobs_path)
        except ValueError as e:
            sys.exit(make_colors(str(e), 'lw', 'r'))
        print(make_colors("pyidm agent server listening on http://%s:%s (%s) - Ctrl+C to stop" % (
            host, port, "token required" if token else "no token, loopback only"), 'b', 'y'))
        print(make_colors("web ui: %s | completion tracking: %s | jobs file: %s%s" % (
            "/" if webui else "off", "on" if log_watcher else "off", jobs_path or "off (memory only)",
            " (%d job(s) restored)" % srv.restored if jobs_path else ""), 'lc'))
        try:
            srv.serve()
        finally:
            if log_watcher:
                log_watcher.stop()

    def send_to_agent(self, agent, urls, token=None, **opts):
        try:
            res = agent_send(agent, urls, opts, token)
        except AgentError as e:
            print(make_colors(str(e), 'lw', 'r'))
            return None
        print(make_colors("Sent {} link(s) to agent {}".format(res.get('queued', len(urls)), agent), 'b', 'y'))
        return res

    @staticmethod
    def _show_state(url, state, downloaded=None):
        print(make_colors("[{}] {}{}".format(state, url, " ({} bytes)".format(downloaded) if downloaded else ""), 'lc'))

    def wait_agent(self, agent, job_ids, token=None, timeout=3600):
        """Wait until the agent reports every job final. Returns a process exit code."""
        def show(view):
            self._show_state(view['url'], view['state'], (view.get('download') or {}).get('downloaded'))
        try:
            final, tracked = agent_wait(agent, job_ids, token, timeout, on_change=show)
        except AgentError as e:
            print(make_colors(str(e), 'lw', 'r'))
            return 2
        if not tracked:
            print(make_colors("Agent has no IDM log watcher: links were sent, completion cannot be tracked.", 'ly'))
            return 0
        return 0 if all(v['state'] == 'complete' for v in final.values()) else 2

    def wait_local(self, watcher, urls, since, timeout=3600):
        codes = []
        for url in urls:
            st = watcher.wait_final(url, since, timeout,
                                    on_change=lambda s: self._show_state(s['url'], s['state'], s['downloaded']))
            codes.append(bool(st and st['state'] == 'complete'))
        return 0 if all(codes) else 2

    def docs(self):
        print(make_colors("uppercase words is VALUE NAME", 'lc'))
        print("\n")
        print(make_colors('download:path:DIR_NAME', 'ly'))
        print(make_colors('download:config:1 or 0', 'lg'))

    def bring_to_top(self):
        if not IS_WINDOWS or windll is None:
            return
        user32 = windll.user32

        # Callback for EnumWindows
        EnumWindowsProc = comtypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM
        )

        find_title = "internet download manager"
        found = []

        def foreach_window(hwnd, lParam):
            # Filter only visible window
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    # print(f"HWND: {hwnd} | Title: {buf.value}")
                    if find_title in buf.value.lower():
                        found.append([hwnd, buf.value])
            return True

        # Enumerate all window
        user32.EnumWindows(EnumWindowsProc(foreach_window), 0)

        # print(f"found: {found}")
        if found:
            user32.ShowWindow(found[0][0], 5)   # SW_SHOW
            user32.SetForegroundWindow(found[0][0])
            user32.BringWindowToTop(found[0][0])

        
    def usage(self):
        try:
            from rchf import CustomRichHelpFormatter  # type: ignore
        except:
            CustomRichHelpFormatter = argparse.RawTextHelpFormatter

        description = make_colors("Command line downloader with/Via Internet Download Manager(IDM)", 'lg')
        parse = argparse.ArgumentParser(formatter_class=CustomRichHelpFormatter, description = description, prog="idm")
        parse.add_argument('URLS', action='store', help='url to download, or "c" to get url from clipboard or a text file containing one link per line' , nargs = '*')
        parse.add_argument('-p', '--path', action='store', help='Path to save (default: current dir; on agent server: its configured path)')
        parse.add_argument('-o', '--output', help='Save with different name', action='store')
        parse.add_argument('-c', '--confirm', help='Confirm before download', action='store_true')
        parse.add_argument('-a', '--add', help='Add link to IDM without start downloading', action='store_true')
        parse.add_argument('-r', '--referrer', help='Url referrer', action='store')
        parse.add_argument('-C', '--cookie', help='Cookie string or dict', action='store', type = str)
        parse.add_argument('-D', '--post-data', help='Post Data string or dict', action='store', type = str)
        parse.add_argument('-U', '--username', help='Username if require', action='store', type = str)
        parse.add_argument('-P', '--password', help='Password if require', action='store', type = str)
        parse.add_argument('-ua', '--user-agent', help='Send with custom User-Agent string', action='store')
        parse.add_argument('-s', '--server', help='Run agent server: receive links over HTTP and forward them to IDM (COM)', action='store_true')
        parse.add_argument('--host', help='Agent server bind host (default: 127.0.0.1)', action='store')
        parse.add_argument('--port', help='Agent server port (default: 8899)', action='store', type=int)
        parse.add_argument('--token', help='Agent server token (or env PYIDM_TOKEN), required if host is not loopback', action='store')
        parse.add_argument('-A', '--agent', help='Send links to an agent server instead of local IDM, e.g. http://192.168.1.10:8899', action='store')
        parse.add_argument('--agent-token', help='Token for the agent server (or env PYIDM_TOKEN)', action='store')
        parse.add_argument('--local', help='Ignore configured agent url, send to local IDM', action='store_true')
        parse.add_argument('-w', '--wait', help='Wait until the download is complete (needs the IDM log watcher), exit code 2 on error/cancel/timeout', action='store_true')
        parse.add_argument('--timeout', help='Max seconds to wait with --wait (default: 3600, 0 = forever)', action='store', type=int, default=3600)
        parse.add_argument('--no-webui', help='Agent server: disable the web interface', action='store_true')
        parse.add_argument('--no-watcher', help='Agent server: disable IDM log watching (download state tracking)', action='store_true')
        parse.add_argument('--jobs-file', help='Agent server: where jobs are saved (default: %%APPDATA%%\\pyidm\\jobs.json, ~/.pyidm/jobs.json elsewhere)', action='store')
        parse.add_argument('--no-persist', help='Agent server: keep jobs in memory only (lost on restart)', action='store_true')
        parse.add_argument('--log-dir', help='IDM log directory (default: %%APPDATA%%\\IDM\\DwnlData\\<USERNAME>)', action='store')
        parse.add_argument('-v', '--verbose', help='Verbose agent server log', action='store_true')
        parse.add_argument('--config',  help = 'set config, format section:option:value, for list valid section/option type "doc"', action = 'store')
        # parse.add_argument('--clip', help='Get URL from clipboard for one link', action='store_true')

        if len(sys.argv) ==1:
            parse.print_help()
            if COM_ERROR:
                print(make_colors("\nNote: " + COM_ERROR, 'ly'))
            self.bring_to_top()
        else:
            try:
                if sys.argv[1] == '--config' and sys.argv[2] == 'doc':
                    self.docs()
                    os.kill(self.PID, signal.SIGTERM)
                elif sys.argv[1] == '--config' and len(sys.argv) > 2:
                    debug(check_1 = sys.argv[2].split(":", 2))
                    if len(sys.argv[2].split(":", 2)) == 3:
                        section, option, value = sys.argv[2].split(":", 2)
                        self.CONFIG.write_config(section, option, value)
                        os.kill(self.PID, signal.SIGTERM)
                    else:
                        print(make_colors("INVALID config parameter/argument !", 'lw', 'r'))
                        os.kill(self.PID, signal.SIGTERM)
            except IndexError:
                pass
            except:
                print(traceback.format_exc())
            args = parse.parse_args()
            if args.config == 'doc':
                self.docs()
            elif args.server:
                self.serve(args.host, args.port, args.token, args.verbose, not args.no_webui, not args.no_watcher, args.log_dir, args.jobs_file, not args.no_persist)
            else:
                urls = self.expand_urls(args.URLS)
                agent = None if args.local else (args.agent or self._cfg('AGENT_URL'))
                if agent:
                    token = args.agent_token or os.getenv('PYIDM_TOKEN') or self._cfg('AGENT_TOKEN')
                    res = self.send_to_agent(agent, urls, token, path=args.path, output=args.output,
                                             referrer=args.referrer, cookie=args.cookie, post_data=args.post_data,
                                             username=args.username, password=args.password,
                                             confirm=True if args.confirm else None,
                                             user_agent=args.user_agent, add_only=True if args.add else None)
                    if not res:
                        sys.exit(1)
                    if args.wait and not args.add:
                        sys.exit(self.wait_agent(agent, res.get('jobs', []), token, args.timeout))
                else:
                    try:
                        self._require_com()
                    except (OSNotSupport, IDMNotFound) as e:
                        print(str(e))
                        sys.exit(1)
                    watcher = None
                    if args.wait and not args.add:
                        watcher = LogWatcher(log_dir=args.log_dir or self._cfg('WATCHER_LOG_DIR'))
                        if not watcher.start():
                            print(make_colors("IDM log directory not found ({}): cannot wait for completion".format(
                                watcher.log_dir or 'unknown'), 'ly'))
                            watcher = None
                    started = time.time()
                    download_path = args.path or os.getcwd()
                    confirm = args.confirm or self.CONFIG.get_config('DOWNLOAD_CONFIRM')
                    user_agent = args.user_agent or self.CONFIG.get_config('DATA_USER_AGENT')
                    for url in urls:
                        self.download(url, download_path, args.output, args.referrer, args.cookie, args.post_data, args.username, args.password, confirm, user_agent, args.add)
                    if watcher:
                        code = self.wait_local(watcher, urls, started, args.timeout)
                        watcher.stop()
                        sys.exit(code)


if __name__ == '__main__':
    c = IDMan()
    c.usage()
