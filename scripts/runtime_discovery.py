#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

DATA_DIR = Path(os.getenv('DATA_DIR', '/data'))
RUNTIME_FILE = DATA_DIR / 'runtime.json'


def clean(value):
    return (value or '').strip()


def host_only(value):
    value = clean(value)
    if not value:
        return ''
    if '://' in value:
        value = urlparse(value).netloc
    return value.split('/', 1)[0].split(':', 1)[0]


def env_first(*names):
    for name in names:
        value = clean(os.getenv(name))
        if value:
            return value
    return ''


def positive_int(value, default=0):
    try:
        value = int(value)
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


def discover():
    port = positive_int(os.getenv('PORT'), 8080)
    app_port = positive_int(os.getenv('RAILWAY_TCP_APPLICATION_PORT'), port)
    tcp_port = positive_int(os.getenv('RAILWAY_TCP_PROXY_PORT'))
    public_domain = host_only(env_first('RAILWAY_PUBLIC_DOMAIN', 'PUBLIC_DOMAIN'))
    tcp_domain = host_only(env_first('RAILWAY_TCP_PROXY_DOMAIN', 'SERVER_HOST', 'XRAY_TCP_PROXY_HOST'))
    custom_domain = host_only(os.getenv('CUSTOM_DOMAIN'))
    grpc_domain = host_only(os.getenv('GRPC_DOMAIN')) or custom_domain

    return {
        'schema': 1,
        'updated_at': int(time.time()),
        'railway': {
            'port': port,
            'application_port': app_port,
            'public_domain': public_domain,
            'tcp_proxy_domain': tcp_domain,
            'tcp_proxy_port': tcp_port,
            'private_domain': host_only(os.getenv('RAILWAY_PRIVATE_DOMAIN')),
            'project_id': clean(os.getenv('RAILWAY_PROJECT_ID')),
            'environment_id': clean(os.getenv('RAILWAY_ENVIRONMENT_ID')),
            'service_id': clean(os.getenv('RAILWAY_SERVICE_ID')),
            'replica_id': clean(os.getenv('RAILWAY_REPLICA_ID')),
            'replica_region': clean(os.getenv('RAILWAY_REPLICA_REGION')),
            'deployment_id': clean(os.getenv('RAILWAY_DEPLOYMENT_ID')),
        },
        'domains': {
            'custom_domain': custom_domain,
            'grpc_domain': grpc_domain,
        },
        'listeners': {
            'gateway': port,
            'xhttp_reality': positive_int(os.getenv('XRAY_XHTTP_REALITY_PORT'), 10087),
            'xhttp_tls': positive_int(os.getenv('XRAY_XHTTP_TLS_PORT'), 10086),
            'vision_reality': positive_int(os.getenv('XRAY_VISION_REALITY_PORT'), 10085),
            'grpc_reality': positive_int(os.getenv('XRAY_GRPC_REALITY_PORT'), 10088),
        },
    }


def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    runtime = discover()
    atomic_write(RUNTIME_FILE, runtime)
    r = runtime['railway']
    print('[runtime-discovery] PORT=%s application=%s public=%s tcp=%s:%s' % (
        r['port'], r['application_port'], r['public_domain'] or '-',
        r['tcp_proxy_domain'] or '-', r['tcp_proxy_port'] or '-'))
    print('[runtime-discovery] project=%s service=%s replica=%s region=%s' % (
        r['project_id'] or '-', r['service_id'] or '-', r['replica_id'] or '-', r['replica_region'] or '-'))
    print('[runtime-discovery] runtime=%s' % RUNTIME_FILE)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
