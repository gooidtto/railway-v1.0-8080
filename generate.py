import base64
import os
import urllib.parse

PUBLIC_DOMAIN = os.environ.get("PUBLIC_DOMAIN", "railway-v10-8080-production.up.railway.app")
UUID = os.environ.get("UUID", "9d230ff4-026a-4702-be3f-479f5bdeb3d8")
REALITY_PUBLIC_KEY = os.environ.get("REALITY_PUBLIC_KEY", "")
REALITY_SHORT_ID = os.environ.get("REALITY_SHORT_ID", "")
XHTTP_PATH = os.environ.get("XHTTP_PATH", "/xhttp")

# Keep only SNI values that the user has actually confirmed as working.
SNI_LIST = [
    "www.cloudflare.com",
    "www.bing.com",
    "www.canva.com",
    "www.notion.so",
    "store.epicgames.com",
    "www.gog.com",
    "www.gamespot.com",
]


def q(params):
    return urllib.parse.urlencode(params, safe="/,:")


def vless_xhttp_https():
    # TLS is terminated by Railway's public HTTPS edge. The backend hop to
    # health_proxy/Xray is plain HTTP. Keep the public client URI minimal and
    # do not inject fragment, REALITY, or MUX-specific parameters.
    params = {
        "encryption": "none",
        "security": "tls",
        "sni": PUBLIC_DOMAIN,
        "type": "xhttp",
        "host": PUBLIC_DOMAIN,
        "path": XHTTP_PATH,
        "mode": "auto",
        "alpn": "h2,http/1.1",
        "fp": "chrome",
        "allowInsecure": "0",
    }
    return (
        f"vless://{UUID}@{PUBLIC_DOMAIN}:443?{q(params)}"
        f"#railway-https-xhttp-{PUBLIC_DOMAIN}"
    )


def vless_xhttp_reality(sni):
    params = {
        "encryption": "none",
        "security": "reality",
        "sni": sni,
        "fp": "chrome",
        "pbk": REALITY_PUBLIC_KEY,
        "sid": REALITY_SHORT_ID,
        "type": "xhttp",
        "host": sni,
        "path": XHTTP_PATH,
        "mode": "auto",
        "alpn": "h2,http/1.1",
    }
    return (
        f"vless://{UUID}@{os.environ.get('TCP_PROXY_HOST', 'shortline.proxy.rlwy.net')}"
        f":{os.environ.get('TCP_PROXY_PORT', '37762')}?{q(params)}"
        f"#railway-xhttp-reality-{sni}"
    )


def main():
    nodes = [vless_xhttp_https()]
    nodes.extend(vless_xhttp_reality(sni) for sni in SNI_LIST)
    payload = "\n".join(nodes)
    encoded = base64.b64encode(payload.encode()).decode()
    out = "/data/subscription.txt"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(encoded)
    print(f"HTTPS XHTTP node generated: {PUBLIC_DOMAIN}:443")
    print(f"REALITY SNI nodes generated: {len(SNI_LIST)}")
    for sni in SNI_LIST:
        print(f"REALITY SNI: {sni}")
    return payload


if __name__ == "__main__":
    main()
