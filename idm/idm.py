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

try:
    from .server import AgentServer, AgentError, send as agent_send, DEFAULT_HOST, DEFAULT_PORT
except ImportError:
    from server import AgentServer, AgentError, send as agent_send, DEFAULT_HOST, DEFAULT_PORT

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

if not 'linux' in sys.platform:
    import comtypes.client as cc
    import comtypes
    from comtypes import automation, windll
    from ctypes import wintypes, create_unicode_buffer

else:
    raise OSNotSupport(make_colors('This only for Windows OS !'))


class IDMan(object):
    PID = os.getpid()
    last_error = None
    CONFIGFILE = str(Path(__file__).parent / 'idm.ini')
    CONFIG = load_env(CONFIGFILE)
    
    def __init__(self):
        super(IDMan, self)
        self.tlb = r'c:\Program Files\Internet Download Manager\idmantypeinfo.tlb'
        if not os.path.isfile(self.tlb):
            self.tlb = r'c:\Program Files (x86)\Internet Download Manager\idmantypeinfo.tlb'
        if not os.path.isfile(self.tlb):
            #print("It seem IDM not installed, please install first !")
            #sys.exit("It seem IDM not installed, please install first !")
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

    def serve(self, host=None, port=None, token=None, verbose=False):
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
        try:
            srv = AgentServer(self, host, port, token, defaults=defaults, verbose=verbose)
        except ValueError as e:
            sys.exit(make_colors(str(e), 'lw', 'r'))
        print(make_colors("pyidm agent server listening on http://%s:%s (%s) - Ctrl+C to stop" % (
            host, port, "token required" if token else "no token, loopback only"), 'b', 'y'))
        srv.serve()

    def send_to_agent(self, agent, urls, token=None, **opts):
        try:
            res = agent_send(agent, urls, opts, token)
        except AgentError as e:
            print(make_colors(str(e), 'lw', 'r'))
            return False
        print(make_colors("Sent {} link(s) to agent {}".format(res.get('queued', len(urls)), agent), 'b', 'y'))
        return True

    def docs(self):
        print(make_colors("uppercase words is VALUE NAME", 'lc'))
        print("\n")
        print(make_colors('download:path:DIR_NAME', 'ly'))
        print(make_colors('download:config:1 or 0', 'lg'))

    def bring_to_top(self):
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
        parse.add_argument('-v', '--verbose', help='Verbose agent server log', action='store_true')
        parse.add_argument('--config',  help = 'set config, format section:option:value, for list valid section/option type "doc"', action = 'store')
        # parse.add_argument('--clip', help='Get URL from clipboard for one link', action='store_true')

        if len(sys.argv) ==1:
            parse.print_help()
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
                self.serve(args.host, args.port, args.token, args.verbose)
            else:
                urls = self.expand_urls(args.URLS)
                agent = None if args.local else (args.agent or self._cfg('AGENT_URL'))
                if agent:
                    token = args.agent_token or os.getenv('PYIDM_TOKEN') or self._cfg('AGENT_TOKEN')
                    if not self.send_to_agent(agent, urls, token, path=args.path, output=args.output,
                                              referrer=args.referrer, cookie=args.cookie, post_data=args.post_data,
                                              username=args.username, password=args.password,
                                              confirm=True if args.confirm else None,
                                              user_agent=args.user_agent, add_only=True if args.add else None):
                        sys.exit(1)
                else:
                    download_path = args.path or os.getcwd()
                    confirm = args.confirm or self.CONFIG.get_config('DOWNLOAD_CONFIRM')
                    user_agent = args.user_agent or self.CONFIG.get_config('DATA_USER_AGENT')
                    for url in urls:
                        self.download(url, download_path, args.output, args.referrer, args.cookie, args.post_data, args.username, args.password, confirm, user_agent, args.add)


if __name__ == '__main__':
    c = IDMan()
    c.usage()
