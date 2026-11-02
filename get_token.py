"""One-time: get a Yahoo refresh token. Run on your own computer:  python get_token.py

It opens a Yahoo login page. After you click "Agree", the browser goes to
https://localhost:8080/?code=XXXX  - the page won't load, that's expected.
Copy the code from the address bar and paste it here.
"""
import getpass
import urllib.parse
import webbrowser

from fetch import REDIRECT_URI, token_request

cid = input("Yahoo Client ID: ").strip()
sec = getpass.getpass("Yahoo Client Secret (hidden): ").strip()
url = "https://api.login.yahoo.com/oauth2/request_auth?" + urllib.parse.urlencode(
    {"client_id": cid, "redirect_uri": REDIRECT_URI, "response_type": "code"})
print("\nOpening:", url)
webbrowser.open(url)
raw = input("\nPaste the code (or the whole localhost URL): ").strip()
code = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query).get("code", [raw])[0]
tok = token_request(cid, sec, {"grant_type": "authorization_code", "code": code,
                               "redirect_uri": REDIRECT_URI})
print("\nYour refresh token (save it as the GitHub secret YAHOO_REFRESH_TOKEN):\n")
print(tok["refresh_token"])
