import base64, json, os, re
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs


def env(name, default=None, required=False):
    value = os.getenv(name, default)
    if required and not value:
        raise SystemExit(f"ERROR: missing {name}")
    return value


data_dir = Path(env("DATA_DIR", "/data"))
config_path = Path(env("CONFIG", "/etc/xray/config.json"))
xray_port = int(env("XRAY_PORT", "10087"))
xray_http_port = int(env("XRAY_HTTP_PORT", "10086"))
xray_listen = env("XRAY_LISTEN", "127.0.0.1")
gateway_port = int(env("GATEWAY_PORT", env("PORT", "8080")))
uuid = env("UUID", required=True)
private_key = env("PRIVATE_KEY", required=True)
public_key = env("PUBLIC_KEY", required=True)
vless_decryption = env("VLESS_DECRYPTION", required=True)
vless_encryption = env("VLESS_ENCRYPTION", required=True)


def normalize_target(value):
    value = (value or "").strip()
    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        value = parsed.netloc or parsed.path
    value = value.strip("[]").rstrip("/")
    if ":" not in value:
        value += ":443"
    host, port = value.rsplit(":", 1)
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host) or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise SystemExit("ERROR: invalid REALITY_TARGET")
    return f"{host}:{int(port)}"


target = normalize_target(env("REALITY_TARGET", "www.cloudflare.com:443"))
fingerprint = env("REALITY_FINGERPRINT", "chrome")
xhttp_path = env("XHTTP_PATH", "/xhttp")
xhttp_mode = env("XHTTP_MODE", "auto")
short_id = env("SHORT_ID", "50175c035ee132")

# Railway runtime values are authoritative. No deployment-specific hostname or
# external TCP port is stored in this portable branch.
public_domain = env("RAILWAY_PUBLIC_DOMAIN", "").strip() or env("PUBLIC_DOMAIN", "").strip()
if not public_domain:
    raise SystemExit("ERROR: RAILWAY_PUBLIC_DOMAIN is unavailable; generate a Railway Public Networking domain first")

server_host = env("RAILWAY_TCP_PROXY_DOMAIN", "").strip() or env("SERVER_HOST", "").strip() or env("XRAY_TCP_PROXY_HOST", "").strip()
server_port = env("RAILWAY_TCP_PROXY_PORT", "").strip() or env("SERVER_PORT", "").strip() or env("XRAY_TCP_PROXY_PORT", "").strip()
tcp_application_port = env("RAILWAY_TCP_APPLICATION_PORT", "").strip() or env("TCP_APPLICATION_PORT", "8080").strip()
if not server_host or not server_port:
    raise SystemExit("ERROR: Railway TCP Proxy domain/port are unavailable; create a TCP Proxy targeting application port 8080")
if not server_port.isdigit() or not 1 <= int(server_port) <= 65535:
    raise SystemExit("ERROR: invalid RAILWAY_TCP_PROXY_PORT")
if not tcp_application_port.isdigit() or int(tcp_application_port) != 8080:
    raise SystemExit(f"ERROR: RAILWAY_TCP_APPLICATION_PORT must be 8080, got {tcp_application_port}")

sni_file = Path(env("REALITY_SNI_CANDIDATES_FILE", "/opt/xray/config/reality-sni-candidates.txt"))
pool = []
for raw in sni_file.read_text(encoding="utf-8").splitlines():
    value = raw.strip()
    if value and not value.startswith("#") and value not in pool:
        pool.append(value)
expected = int(env("REALITY_SNI_LIMIT", "7"))
if len(pool) != expected:
    raise SystemExit(f"ERROR: expected exactly {expected} verified SNI values, got {len(pool)}")

reality_inbound = {
    "listen": xray_listen, "port": xray_port, "protocol": "vless",
    "settings": {"clients": [{"id": uuid}], "decryption": vless_decryption},
    "streamSettings": {
        "network": "xhttp", "security": "reality",
        "realitySettings": {
            "show": False, "target": target, "xver": 0,
            "serverNames": pool, "privateKey": private_key,
            "shortIds": [short_id],
        },
        "xhttpSettings": {"path": xhttp_path, "mode": xhttp_mode},
    },
}
https_inbound = {
    "listen": xray_listen, "port": xray_http_port, "protocol": "vless",
    "settings": {"clients": [{"id": uuid}], "decryption": vless_decryption},
    "streamSettings": {
        "network": "xhttp", "security": "none",
        "xhttpSettings": {"path": xhttp_path, "mode": xhttp_mode},
    },
}
config = {
    "log": {"loglevel": env("XRAY_LOGLEVEL", "info")},
    "inbounds": [reality_inbound, https_inbound],
    "outbounds": [{"protocol": "freedom", "tag": "direct"}],
}
config_path.parent.mkdir(parents=True, exist_ok=True)
tmp = str(config_path) + ".tmp"
Path(tmp).write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
os.chmod(tmp, 0o600)
os.replace(tmp, config_path)
data_dir.mkdir(parents=True, exist_ok=True)
os.chmod(data_dir, 0o700)

https_vless = (
    f"vless://{uuid}@{public_domain}:443/?encryption={quote(vless_encryption, safe='')}"
    f"&security=tls&type=xhttp&fp={quote(fingerprint, safe='')}"
    f"&sni={quote(public_domain, safe='')}&alpn=h2%2Chttp%2F1.1"
    f"&path={quote(xhttp_path, safe='')}&mode={quote(xhttp_mode, safe='')}"
    f"#railway-xhttp-https-{public_domain}"
)
reality_nodes = []
for sni in pool:
    reality_nodes.append(
        f"vless://{uuid}@{server_host}:{server_port}/?encryption={quote(vless_encryption, safe='')}"
        f"&security=reality&type=xhttp&fp={quote(fingerprint, safe='')}&sni={quote(sni, safe='')}"
        f"&pbk={quote(public_key, safe='')}&sid={quote(short_id, safe='')}"
        f"&path={quote(xhttp_path, safe='')}&mode={quote(xhttp_mode, safe='')}"
        f"#railway-xhttp-reality-{sni}"
    )

nodes = [https_vless] + reality_nodes
text = "\n".join(nodes) + "\n"
(data_dir / "vless.txt").write_text(text, encoding="utf-8")
encoded = base64.b64encode(text.encode()).decode() + "\n"
(data_dir / "subscription.txt").write_text(encoded, encoding="utf-8")
os.chmod(data_dir / "subscription.txt", 0o600)
(data_dir / "reality-sni-list.txt").write_text("\n".join(pool) + "\n", encoding="utf-8")

# Publish both subscription endpoints. Primary uses the public HTTPS domain;
# fallback uses the current Railway TCP Proxy domain and its current random port.
primary_url = f"https://{public_domain}/sub/{env('SUBSCRIPTION_TOKEN', required=True)}"
fallback_url = f"http://{server_host}:{server_port}/sub/{env('SUBSCRIPTION_TOKEN', required=True)}"
(data_dir / "subscription_primary_url.txt").write_text(primary_url + "\n", encoding="utf-8")
(data_dir / "subscription_fallback_url.txt").write_text(fallback_url + "\n", encoding="utf-8")
(data_dir / "subscription_endpoints.txt").write_text(
    f"PRIMARY={primary_url}\nFALLBACK={fallback_url}\n", encoding="utf-8"
)
for path in (data_dir / "subscription_primary_url.txt", data_dir / "subscription_fallback_url.txt", data_dir / "subscription_endpoints.txt"):
    os.chmod(path, 0o600)

# Validate the generated subscription before publishing it.
for node in nodes:
    p = urlparse(node)
    q = parse_qs(p.query, keep_blank_values=True)
    if p.scheme != "vless" or p.username != uuid or q.get("encryption", [""])[0] != vless_encryption or q.get("type", [""])[0] != "xhttp":
        raise SystemExit("ERROR: generated VLESS node failed structural validation")
if len(nodes) != expected + 1:
    raise SystemExit("ERROR: subscription node count mismatch")

print(f"Railway Public Domain: {public_domain}")
print(f"TCP Proxy: {server_host}:{server_port}")
print(f"TCP Application Port: {tcp_application_port}")
print(f"Primary subscription: {primary_url}")
print(f"Fallback subscription: {fallback_url}")
print(f"HTTPS XHTTP node generated: {public_domain}:443")
print(f"REALITY SNI nodes generated: {len(reality_nodes)}")
for sni in pool:
    print(f"REALITY SNI: {sni}")
