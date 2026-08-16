import base64
import json
import os
import secrets
from pathlib import Path
from urllib.parse import quote

DATA_DIR = Path(os.getenv('DATA_DIR', '/data'))


def load(name):
    return json.loads((DATA_DIR / name).read_text(encoding='utf-8'))


def write(name, text, mode=0o600):
    path = DATA_DIR / name
    path.write_text(text, encoding='utf-8')
    os.chmod(path, mode)


def q(value):
    return quote(str(value), safe='')


def vless(uuid, host, port, params, label):
    query = '&'.join('%s=%s' % (k, q(v)) for k, v in params.items() if v is not None and v != '')
    return 'vless://%s@%s:%s/?%s#%s' % (uuid, host, port, query, q(label))


def first_sni(manifest, kind):
    names = manifest.get('reality', {}).get(kind, [])
    return names[0] if names else ''


def main():
    runtime = load('runtime.json')
    manifest = load('xray-manifest.json')
    r = runtime['railway']
    uuid = manifest['uuid']
    sid = manifest['short_id']
    public_key = manifest['public_key']
    enc = manifest.get('encryption', '')
    common = {'encryption': enc}
    nodes = []

    # Node 1: Railway Public Domain -> Gateway HTTP -> XHTTP/TLS inbound.
    if r['public_domain']:
        nodes.append(vless(
            uuid,
            r['public_domain'],
            443,
            {**common, 'security': 'tls', 'type': 'xhttp',
             'fp': manifest['fingerprint'], 'sni': r['public_domain'],
             'alpn': 'h2,http/1.1', 'path': manifest['xhttp_path'],
             'mode': manifest['xhttp_mode']},
            'railway-xhttp-tls'))

    # Nodes 2-4: one TCP Proxy carries all three end-to-end REALITY transports.
    # Each protocol gets exactly one subscription node; the SNI pool is an
    # internal failover/candidate pool, not a multiplier for node count.
    if r['tcp_proxy_domain'] and r['tcp_proxy_port']:
        profiles = (
            ('xhttp', 'xhttp', {'path': manifest['xhttp_path'], 'mode': manifest['xhttp_mode']}),
            ('vision', 'raw', {'flow': 'xtls-rprx-vision'}),
            ('grpc', 'grpc', {'serviceName': manifest['grpc_service_name'], 'alpn': 'h2'}),
        )
        for kind, network, extra in profiles:
            sni = first_sni(manifest, kind)
            if not sni:
                continue
            params = {
                **common,
                'security': 'reality',
                'type': network,
                'fp': manifest['fingerprint'],
                'sni': sni,
                'pbk': public_key,
                'sid': sid,
                **extra,
            }
            nodes.append(vless(
                uuid,
                r['tcp_proxy_domain'],
                r['tcp_proxy_port'],
                params,
                'railway-%s-reality' % kind))

    text = '\n'.join(nodes) + ('\n' if nodes else '')
    encoded = base64.b64encode(text.encode()).decode() + '\n'
    write('vless.txt', text)
    write('subscription.txt', encoded)

    token_file = DATA_DIR / 'subscription_token.txt'
    if token_file.is_file() and token_file.read_text().strip():
        token = token_file.read_text().strip()
    else:
        token = secrets.token_urlsafe(32)
        write('subscription_token.txt', token + '\n')

    urls = []
    if r['public_domain']:
        urls.append('PRIMARY=https://%s/sub/%s' % (r['public_domain'], token))
    if r['tcp_proxy_domain'] and r['tcp_proxy_port']:
        urls.append('TCP=http://%s:%s/sub/%s' % (r['tcp_proxy_domain'], r['tcp_proxy_port'], token))
    write('subscription_endpoints.txt', '\n'.join(urls) + ('\n' if urls else ''))

    expected = 4 if r['public_domain'] and r['tcp_proxy_domain'] and r['tcp_proxy_port'] else 1
    if len(nodes) != expected:
        raise SystemExit('[subscription-generator] ERROR: expected %d nodes, generated %d' % (expected, len(nodes)))

    print('[subscription-generator] nodes=%d (1 TLS + 3 REALITY)' % len(nodes))
    for item in urls:
        print('[subscription-generator] %s' % item)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
