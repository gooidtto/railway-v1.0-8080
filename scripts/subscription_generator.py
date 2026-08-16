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
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def q(value):
    return quote(str(value), safe='')


def vless(uuid, host, port, params, label):
    query = '&'.join('%s=%s' % (k, q(v)) for k, v in params.items() if v is not None and v != '')
    return 'vless://%s@%s:%s?%s#%s' % (uuid, host, port, query, q(label))


def first_sni(manifest, kind):
    names = manifest.get('reality', {}).get(kind, [])
    return names[0] if names else ''


def validate_nodes(nodes):
    if not nodes:
        raise SystemExit('[subscription-generator] ERROR: no nodes generated')
    for index, node in enumerate(nodes, 1):
        if not node.startswith('vless://') or '?' not in node or '@' not in node:
            raise SystemExit('[subscription-generator] ERROR: invalid VLESS URI at index %d' % index)
    return True


def main():
    runtime = load('runtime.json')
    manifest = load('xray-manifest.json')
    r = runtime['railway']
    uuid = manifest['uuid']
    sid = manifest['short_id']
    public_key = manifest['public_key']

    encryption = manifest.get('encryption', '') if manifest.get('vless_encryption_enabled', False) else ''
    common = {'encryption': encryption} if encryption else {}
    nodes = []

    # Railway Generate Domain is an HTTP/HTTPS edge. Railway terminates the
    # public TLS session before forwarding the request to Target Port 8080.
    # Therefore this node MUST use XHTTP over HTTP at the service side; it
    # must not advertise end-to-end VLESS TLS through the Railway domain.
    # The edge still provides HTTPS to the client, while the Gateway receives
    # the decrypted HTTP request and forwards /xhttp to the local Xray inbound.
    if r['public_domain']:
        nodes.append(vless(
            uuid, r['public_domain'], 443,
            {**common, 'security': 'none', 'type': 'xhttp',
             'fp': manifest['fingerprint'], 'sni': r['public_domain'],
             'alpn': 'h2,http/1.1', 'path': manifest['xhttp_path'],
             'mode': manifest['xhttp_mode']},
            'railway-xhttp-https-edge'))

    # Railway TCP Proxy preserves raw TCP and is therefore the only public
    # endpoint used for end-to-end REALITY profiles.
    if r['tcp_proxy_domain'] and r['tcp_proxy_port']:
        profiles = (
            ('xhttp', 'xhttp', {'path': manifest['xhttp_path'], 'mode': manifest['xhttp_mode']}),
            ('vision', 'tcp', {'flow': 'xtls-rprx-vision'}),
            ('grpc', 'grpc', {'serviceName': manifest['grpc_service_name'], 'alpn': 'h2'}),
        )
        for kind, network, extra in profiles:
            sni = first_sni(manifest, kind)
            if not sni:
                raise SystemExit('[subscription-generator] ERROR: missing SNI for %s' % kind)
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
            nodes.append(vless(uuid, r['tcp_proxy_domain'], r['tcp_proxy_port'], params,
                               'railway-%s-reality' % kind))

    validate_nodes(nodes)
    text = '\n'.join(nodes) + '\n'
    encoded = base64.b64encode(text.encode('utf-8')).decode('ascii') + '\n'
    write('vless.txt', text)
    write('subscription.txt', encoded)

    try:
        decoded = base64.b64decode(encoded.strip(), validate=True).decode('utf-8')
    except Exception as exc:
        raise SystemExit('[subscription-generator] ERROR: Base64 self-check failed: %s' % exc)
    decoded_nodes = [line.strip() for line in decoded.splitlines() if line.strip()]
    if decoded_nodes != nodes:
        raise SystemExit('[subscription-generator] ERROR: Base64 round-trip changed node content')

    token_file = DATA_DIR / 'subscription_token.txt'
    if token_file.is_file() and token_file.read_text().strip():
        token = token_file.read_text().strip()
    else:
        token = secrets.token_urlsafe(32)
        write('subscription_token.txt', token + '\n')

    subscription_url = ''
    if r['public_domain']:
        subscription_url = 'https://%s/sub/%s' % (r['public_domain'], token)
        write('subscription_endpoints.txt', 'PRIMARY=%s\n' % subscription_url)
        write('subscription_url.txt', subscription_url + '\n')
    else:
        write('subscription_endpoints.txt', '')
        write('subscription_url.txt', '')

    if r['tcp_proxy_domain'] and r['tcp_proxy_port']:
        write('tcp_proxy_endpoint.txt', 'TCP=%s:%s\n' % (r['tcp_proxy_domain'], r['tcp_proxy_port']))
    else:
        write('tcp_proxy_endpoint.txt', '')

    expected = 4 if r['public_domain'] and r['tcp_proxy_domain'] and r['tcp_proxy_port'] else 1
    if len(nodes) != expected:
        raise SystemExit('[subscription-generator] ERROR: expected %d nodes, generated %d' % (expected, len(nodes)))

    print('[subscription-generator] nodes=%d (1 HTTPS-edge XHTTP + 3 REALITY)' % len(nodes), flush=True)
    print('[subscription-generator] vless-encryption=%s' % ('enabled' if encryption else 'disabled'), flush=True)
    print('[subscription-generator] public-domain transport=HTTPS-edge -> XHTTP security=none', flush=True)
    print('[subscription-generator] vless-bytes=%d subscription-bytes=%d' % (len(text.encode()), len(encoded.encode())), flush=True)
    print('[subscription-generator] base64-roundtrip=OK', flush=True)
    if subscription_url:
        print('[subscription-generator] PRIMARY=%s' % subscription_url, flush=True)
    if r['tcp_proxy_domain'] and r['tcp_proxy_port']:
        print('[subscription-generator] TCP transport=%s:%s' % (r['tcp_proxy_domain'], r['tcp_proxy_port']), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
