#!/usr/bin/env python
#coding:utf-8
"""
  Author : Hadi Cahyadi <cumulus13@gmail.com>
  Purpose: command line to download with Internet Download Manager (IDM) on Windows OS
  Created: 04/22/19
  Support: 2.7+, 3+
"""

from __future__ import print_function
import sys
import os
import traceback
import argparse
if sys.version_info.major == 2: input = raw_input
try:
    from pathlib import Path
except:
    pass
from configset import configset
from make_colors import make_colors
import signal
if os.getenv('DEBUG') == '1':
    from pydebugger.debug import debug
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
    from ctypes import wintypes, byref, create_unicode_buffer

else:
    raise OSNotSupport(make_colors('This only for Windows OS !'))


class IDMan(object):
    PID = os.getpid()
    if sys.version_info.major == '2':
        CONFIGFILE = os.path.join(os.path.dirname(__file__), 'idm.ini')
    else:
        CONFIGFILE = str(Path(__file__).parent / 'idm.ini')
    CONFIG = configset(CONFIGFILE)
    
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
            q = input("Please re-input url download to:")
            if not q:
                sys.exit("You not input URL Download !")
            else:
                return q
        return clipboard.paste()

    #def download(self, link, path_to_save=None, output=None, referrer=None, cookie=None, postData=None, user=None, password=None, confirm = False, lflag = None, clip=False):
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
        idman1 = cc.CreateObject(idman.CIDMLinkTransmitter, None, None, idman.ICIDMLinkTransmitter2)
        if path_to_save:
            os.path.realpath(path_to_save)
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
        try:
            idman1.SendLinkToIDM2(link, referrer, cookie, postData, user, password, path_to_save, output, lflag, reserved1, reserved2)
        except Exception as e:
            print("Error: {}".format(make_colors(str(e), 'lw', 'r')))
        else:
            if not self.CONFIG.get_config('debug', 'verbose') == False: print("\n", make_colors("Link sent to IDM successfully.", 'b', 'y'))        

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
        description = make_colors("Command line downloader with/Via Internet Download Manager(IDM)", 'lg')
        parse = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter, description = description)
        parse.add_argument('URLS', action='store', help='url to download, or "c" to get url from clipboard or a text file containing one link per line' , nargs = '*')
        parse.add_argument('-p', '--path', action='store', help='Path to save', default=os.getcwd())
        parse.add_argument('-o', '--output', help='Save with different name', action='store')
        parse.add_argument('-c', '--confirm', help='Confirm before download', action='store_true')
        parse.add_argument('-a', '--add', help='Add link to IDM without start downloading', action='store_true')
        parse.add_argument('-r', '--referrer', help='Url referrer', action='store')
        parse.add_argument('-C', '--cookie', help='Cookie string or dict', action='store', type = str)
        parse.add_argument('-D', '--post-data', help='Post Data string or dict', action='store', type = str)
        parse.add_argument('-U', '--username', help='Username if require', action='store', type = str)
        parse.add_argument('-P', '--password', help='Password if require', action='store', type = str)
        parse.add_argument('-ua', '--user-agent', help='Send with custom User-Agent string', action='store')
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
            else:
                download_path = args.path or self.CONFIG.get_config('download', 'path')
                confirm = args.confirm or self.CONFIG.get_config('download', 'confirm')
                user_agent = args.user_agent or self.CONFIG.get_config('data', 'user_agent')
                for url in args.URLS:
                    self.download(url, download_path, args.output, args.referrer, args.cookie, args.post_data, args.username, args.password, confirm, user_agent, args.add)


if __name__ == '__main__':
    c = IDMan()
    c.usage()
