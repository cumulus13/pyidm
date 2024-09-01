
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

downloader.download(url, r"c:\DOWNLOADS", output=None, referrer=None, cookie=None, postData=None, user=None, password=None, confirm=False, lflag=None, clip=False)
```

And it will open "Internet Download Manager (IDM)"

or run on terminal

```bash
$ python idm.py "http://test.com/test.exe" -p C:\DOWNLOADS -o test_output.exe
```

Example use with headers as postData and cookies:

```python
from idm import IDMan

downloader = IDMan()
url = "http://test.com/test.exe"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3', 
    'Authorization': "Bearer KN9WW7k5gKgCnQLpnmWWM7LytAuSUwb9",
    'Cookie': 'accountToken=KN9WW7k5gKgCnQLpnmWWM7LytAuSUwb9',
}
cookies = {
    'accountToken': 'KN9WW7k5gKgCnQLpnmWWM7LytAuSUwb9'
}

downloader.download(url, r"c:\DOWNLOADS", output=None, referrer=None, cookie=cookie, postData=headers, user=None, password=None, confirm=False, lflag=None, clip=False)
```

## Support

- Python 2.7+, Python 3.x
- Windows (only), for Linux you can't use pywget (pip install pywget)

## Links

- License: [GPL](https://github.com/cumulus13/pyidm/blob/master/LICENSE.rst)
- Code: [https://github.com/cumulus13/pyidm](https://github.com/cumulus13/pyidm)
- Issue tracker: [https://github.com/cumulus13/pyidm/issues](https://github.com/cumulus13/pyidm/issues)

## Author
[Hadi Cahyadi](mailto:cumulus13@gmail.com)