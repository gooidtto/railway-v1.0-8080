#!/usr/bin/env python3
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


def main():
    runtime = load('runtime.json')
    manifest = load('xray-manifest.json')
    r = runtime['railway']
    d = runtime['domains']
    p = runtime['listeners']
    uuid = manifest['uuid']
    sid = manifest['short_id']
    public_key = manifest['public_key']
    enc = manifest.get('encryption', '')
    common = {'encryption': enc}
    nodes = []

    # Railway Public Domain: Railway terminates HTTPS; the Gateway forwards XHTTP locally.
    if r['public_domain']:
        nodes.append(vless(uuid, r['public_domain'], 443,
            {**common, 'security': 'tls', 'type': 'xhttp', 'fp': manifest['fingerprint'],
             'sni': r['public_domain'], 'alpn': 'h2,http/1.1', 'path': manifest['xhttp_path'], 'mode': manifest['xhttp_mode']},
            'railway-xhttp-tls'))

    # TCP Proxy carries end-to-end REALITY. Gateway routes by ClientHello SNI.
    if r['tcp_proxy_domain'] and r['tcp_proxy_port']:
        for kind, names in manifest['reality'].items():
            if not names:
                continue
            for sni in names:
                if kind == 'xhttp':
                    network = 'xhttp'
                    extra = {'path': manifest['xhttp_path'], 'mode': manifest['xhttp_mode']}
                elif kind == 'vision':
                    network = 'raw'
                    extra = {}
                else:
                    network = 'grpc'
                    extra = {'serviceName': manifest['grpc_service_name'], 'alpn': 'h2'}
                params = {**common, 'security': 'reality', 'type': network,
                          'fp': manifest['fingerprint'], 'sni': sni, 'pbk': public_key, 'sid': sid, **extra}
                label = 'railway-%s-reality-%s' % (kind, sni)
                nodes.append(vless(uuid, r['tcp_proxy_domain'], r['tcp_proxy_port'], params, label))

    # Optional user-owned custom TCP domain. Railway still requires the generated TCP proxy port.
    custom_tcp = d.get('custom_domain', '')
    if custom_tcp and r['tcp_proxy_port'] and manifest['reality']['grpc']:
        sni = manifest['reality']['grpc'][0]
        nodes.append(vless(uuid, custom_tcp, r['tcp_proxy_port'],
            {**common, 'security': 'reality', 'type': 'grpc', 'fp': manifest['fingerprint'],
             'sni': sni, 'pbk': public_key, 'sid': sid, 'serviceName': manifest['grpc_service_name'], 'alpn': 'h2'},
            'custom-grpc-reality'))

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
    print('[subscription-generator] nodes=%d' % len(nodes))
    for item in urls:
        print('[subscription-generator] %s' % item)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
