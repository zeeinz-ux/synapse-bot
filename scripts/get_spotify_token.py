"""
Spotify User OAuth2 Token Generator — one-time setup for SPOTIFY_USER_REFRESH_TOKEN.

How it works:
    1. Prints an authorization URL — open it in your browser.
    2. Log in as the user who OWNS the target playlists and authorize.
    3. Browser will redirect to an error page — that's OK.
    4. Copy the FULL URL from the browser address bar.
    5. Paste it here — script exchanges the code for a refresh token.

No server-side setup needed.
"""

import base64
import json
import sys
import urllib.parse
import urllib.request
import webbrowser

SCOPES = "playlist-read-private playlist-read-collaborative"
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"


def main():
    client_id = input("Spotify Client ID: ").strip()
    client_secret = input("Spotify Client Secret: ").strip()
    if not client_id or not client_secret:
        print("Client ID and Secret are required.")
        sys.exit(1)

    redirect_uri = input(
        "Redirect URI (Enter untuk Railway): "
    ).strip() or "https://my-discord-bot-my-discord-bot.up.railway.app/spotify-callback"

    print()
    print("=" * 60)
    print("Step 1: Open this URL in your browser and authorize:")
    print("=" * 60)
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "show_dialog": "true",
    })
    authorize_url = f"{AUTH_URL}?{params}"
    print(authorize_url)
    print()
    webbrowser.open(authorize_url)

    print("Step 2: After authorizing, your browser will redirect")
    print(f"  to: {redirect_uri}")
    print("  The page might show an error — that's NORMAL.")
    print()
    print("Step 3: Copy the FULL URL from your browser's address bar")
    print("  (it looks like: ...spotify-callback?code=AQ...)")
    print("  and paste it below:")
    print()
    callback_url = input("Paste the full redirect URL here: ").strip()

    if not callback_url:
        print("No URL provided.")
        sys.exit(1)

    parsed = urllib.parse.urlparse(callback_url)
    params = urllib.parse.parse_qs(parsed.query)
    code = params.get("code", [None])[0]
    if not code:
        print("No authorization code found in URL.")
        print(f"URL parsed: {parsed.query[:100]}...")
        sys.exit(1)

    print(f"Authorization code received! Exchanging for tokens...")

    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Authorization", f"Basic {auth}")

    try:
        with urllib.request.urlopen(req) as resp:
            token_data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Token exchange failed: HTTP {e.code} {body}")
        sys.exit(1)

    refresh_token = token_data.get("refresh_token")
    access_token = token_data.get("access_token", "")

    if not refresh_token:
        print("No refresh_token in response — Spotify didn't return one.")
        print(f"Response: {json.dumps(token_data, indent=2)}")
        sys.exit(1)

    print()
    print("=" * 60)
    print("SUCCESS — Add this to your .env / Railway secrets:")
    print("=" * 60)
    print()
    print(f"SPOTIFY_USER_REFRESH_TOKEN={refresh_token}")
    print()
    print("This User OAuth2 token will bypass Sandbox 403")
    print("on /v1/playlists/{id}/tracks endpoints.")
    print()


if __name__ == "__main__":
    main()
