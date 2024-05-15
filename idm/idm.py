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
if not 'linux' in sys.platform:
    import comtypes.client as cc
else:
    import comtypes
import argparse
if sys.version_info.major == 2:
    input = raw_input
from configset import configset
from make_colors import make_colors
import signal
from pydebugger.debug import debug

class IDMan(object):
    PID = os.getpid()
    CONFIG = configset()
    
    def __init__(self):
        super(IDMan, self)
        self.tlb = r'c:\Program Files\Internet Download Manager\idmantypeinfo.tlb'
        if not self.tlb:
            self.tlb = r'c:\Program Files\Internet Download Manager (x86)\idmantypeinfo.tlb'
        if not self.tlb:
            print("It seem IDM not installer, please install first !")
            sys.exit("It seem IDM not installer, please install first !")

    def get_from_clipboard(self):
        try:
            import clipboard
        except ImportError:
            print("Module Clipboard not Installer yet, please install first")
            q = input("Please re-input url download to:")
            if not q:
                sys.exit("You not input URL Download !")
            else:
                return q
        return clipboard.paste()

    def download(self, link, path_to_save=None, output=None, referrer=None, cookie=None, postData=None, user=None, password=None, confirm = False, lflag = None, clip=False):
        
        if clip:
            link = self.get_from_clipboard()
        if confirm:
            lflag = 0
        else:
            lflag = 5
        try:
            cc.GetModule(['{ECF21EAB-3AA8-4355-82BE-F777990001DD}', 1, 0])
        except:
            cc.GetModule(self.tlb)

        import comtypes.gen.IDManLib as idman 
        idman1 = cc.CreateObject(idman.CIDMLinkTransmitter, None, None, idman.ICIDMLinkTransmitter2)
        if path_to_save:
            os.path.realpath(path_to_save)
        if isinstance(postData, dict):
            postData = '\n'.join([f'{key}: {value}' for key, value in postData.items()])
        if isinstance(cookie, dict):
            cookie = '; '.join([f'{key}={value}' for key, value in cookie.items()])
            
        idman1.SendLinkToIDM(link, referrer, cookie, postData, user, password, path_to_save, output, lflag)

    def docs(self):
        print(make_colors("uppercase words is VALUE NAME", 'lc'))
        print("\n")
        print(make_colors('download:path:DIR_NAME', 'ly'))
        print(make_colors('download:config:1 or 0', 'lg'))
        
    def usage(self):
        description = make_colors("Command line downloader with/Via Internet Download Manager(IDM), type 'c' for get url from clipboard", 'lg')
        parse = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter, description = description)
        parse.add_argument('URL', action='store', help='url to download, or "c" to get url from clipboard')
        parse.add_argument('-p', '--path', action='store', help='Path to save', default=os.getcwd())
        parse.add_argument('-o', '--output', help='Save with different name', action='store')
        parse.add_argument('-c', '--confirm', help='Confirm before download', action='store_true')
        parse.add_argument('-C', '--clip', help='Get URL from clipboard', action='store_true')
        parse.add_argument('--config',  help = 'set config, format section:option:value, for list valid section/option type "doc"', action = 'store')
        if len(sys.argv) ==1:
            parse.print_help()
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
                self.download(args.URL, download_path, args.output, confirm=confirm, clip=args.clip)


if __name__ == '__main__':
    c = IDMan()
    c.usage()
