

# idm

Downloader with Internet Download Manager (Windows)

## Installing

Install and update using [pip](https://pip.pypa.io/en/stable/quickstart/):

$ pip install idm

idm supports Python 2 and newer, Python 3 and newer, and PyPy.

## Example

What does it look like? Here is an example of a simple pyidm program:

```python
from idm import IDMan

downloader = IDMan()
url = "http://test.com/test.exe"

downloader.download(url, r"c:\DOWNLOADS", "test_output.exe")
```

And "Internet Download Manager (IDM)" will open then immediately download the URL

or run on terminal/cmd

```bash
> python idm.py "http://test.com/test.exe" -p C:\DOWNLOADS -o test_output.exe -c -ua "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36" -r "http://test.com/test.exe" -U admin -P admin123 -D "Authorization=Bearer KN9WW7k5gKgCnQLpnmWWM7LytAuSUwb9\nCookie=accountToken=KN9WW7k5gKgCnQLpnmWWM7LytAuSUwb9" -C "accountToken=KN9WW7k5gKgCnQLpnmWWM7LytAuSUwb9;"

```

Example use with headers as postData, cookies and other parameters:

```python
from idm import IDMan

downloader = IDMan()
url = "http://test.com/test.exe"

headers = { 
    'Authorization': "Bearer KN9WW7k5gKgCnQLpnmWWM7LytAuSUwb9",
    'Cookie': 'accountToken=KN9WW7k5gKgCnQLpnmWWM7LytAuSUwb9',
}
cookies = {
    'accountToken': 'KN9WW7k5gKgCnQLpnmWWM7LytAuSUwb9'
}

username = "admin"
password = "admin123"
confirm = True
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36"

downloader.download(url, r"c:\DOWNLOADS", "test_output.exe", "http://test.com/test.exe", cookie, headers, username, password, confirm, user_agent)
```

## Command line usage
you can use `idm` or `pyidm`
```bash
usage: idm/pyidm [-h] [-p PATH] [-o OUTPUT] [-c] [-r REFERRER] [-C COOKIE] [-D POST_DATA] [-U USERNAME] [-P PASSWORD]
              [-ua USER_AGENT] [--config CONFIG]
              [URLS ...]

Command line downloader with/Via Internet Download Manager(IDM), type 'c' for get url from clipboard

positional arguments:
  URLS                  url to download, or "c" to get url from clipboard

options:
  -h, --help            show this help message and exit
  -p PATH, --path PATH  Path to save
  -o OUTPUT, --output OUTPUT
                        Save with different name
  -c, --confirm         Confirm before download
  -r REFERRER, --referrer REFERRER
                        Url referrer
  -C COOKIE, --cookie COOKIE
                        Cookie string or dict
  -D POST_DATA, --post-data POST_DATA
                        Post Data string or dict
  -U USERNAME, --username USERNAME
                        Username if require
  -P PASSWORD, --password PASSWORD
                        Password if require
  -ua USER_AGENT, --user-agent USER_AGENT
                        Send with custom User-Agent string
  --config CONFIG       set config, format section:option:value, for list valid section/option type "doc"
```
## Support

- Python 2.7+, Python 3.x
- Windows (only), for Linux you can't use pywget (pip install pywget)

## Tips
`always provide ‘referrer’, some sites must have referrer in header`

## Links

- License: [GPL](https://github.com/cumulus13/pyidm/blob/master/LICENSE.rst)
- Code: [https://github.com/cumulus13/pyidm](https://github.com/cumulus13/pyidm)
- Issue tracker: [https://github.com/cumulus13/pyidm/issues](https://github.com/cumulus13/pyidm/issues)

## Author
[Hadi Cahyadi](mailto:cumulus13@gmail.com)

[![Buy Me a Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/cumulus13)

[![Donate via Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/cumulus13)
 [Support me on Patreon](https://www.patreon.com/cumulus13)
