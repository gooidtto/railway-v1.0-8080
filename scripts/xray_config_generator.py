#!/usr/bin/env python3
import json
import os
import re
import secrets
import subprocess
from pathlib import Path

DATA_DIR = Path(os.getenv('DATA_DIR', '/data'))
CONFIG = Path(os.getenv('XRAY_CONFIG', '/etc/xray/config.json'))
RUNTIME_FILE = DATA_DIR / 'runtime.json'


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def persistent(name, producer):
    path = DATA_DIR / name
    if path.is_file():
        value = path.read_text(encoding='utf-8').strip()
        if value:
            return value
    value = producer().strip()
    if not value:
        raise SystemExit('ERROR: failed to generate %s' % name)
    path.write_text(value + '\n', encoding='utf-8')
    os.chmod(path, 0o600)
    return value


def xray(args):
    return subprocess.check_output(['xray', *args], text=True, stderr=subprocess.STDOUT)


def make_uuid():
    return xray(['uuid'])


def make_reality():
    """Parse legacy and current Xray x25519 output formats."""
    out = xray(['x25519'])
    values = {}
    for line in out.splitlines():
        if ':' not in line:
            continue
        key, value = [x.strip() for x in line.split(':', 1)]
        values[key.lower().replace(' ', '')] = value
    private = values.get('privatekey', '')
    public = values.get('publickey', '') or values.get('password(publickey)', '') or values.get('password', '')
    if not private or not public:
        raise SystemExit('ERROR: unable to parse xray x25519 output; expected Private key/Public key or PrivateKey/Password')
    return private, public


def make_vless_keys():
    out = xray(['vlessenc'])
    dec = enc = ''
    active = False
    for line in out.splitlines():
        if 'ML-KEM-768' in line and 'Post-Quantum' in line:
            active = True
            continue
        if not active:
            continue
        if '"decryption"' in line:
            dec = line.split('"decryption"', 1)[1].split(':', 1)[1].strip().strip(',').strip('"')
        elif '"encryption"' in line:
            enc = line.split('"encryption"', 1)[1].split(':', 1)[1].strip().strip(',').strip('"')
        if dec and enc:
            break
    return dec, enc


def short_id():
    value = os.getenv('SHORT_ID', '').strip().lower()
    if value:
        if not re.fullmatch(r'[0-9a-f]{2,16}', value) or len(value) % 2:
            raise SystemExit('ERROR: SHORT_ID must contain 2-16 hexadecimal characters with even length')
        return value
    return secrets.token_hex(8)


def candidate_list(name, fallback):
    raw = os.getenv(name, '').strip()
    path = Path(raw) if raw else Path('/opt/xray/config/reality-sni-candidates.txt')
    values = []
    if path.is_file():
        values = [x.strip() for x in path.read_text(encoding='utf-8').splitlines() if x.strip() and not x.lstrip().startswith('#')]
    if not values:
        values = fallback
    return list(dict.fromkeys(values))


def reality_settings(target, server_names, private, sid):
    return {'show': False, 'target': target, 'xver': 0, 'serverNames': server_names, 'privateKey': private, 'shortIds': [sid]}


def inbound(port, network, security, uuid, decryption, reality=None, xhttp=None, grpc=None, flow=None):
    stream = {'network': network, 'security': security}
    if reality:
        stream['realitySettings'] = reality
    if xhttp:
        stream['xhttpSettings'] = xhttp
    if grpc:
        stream['grpcSettings'] = grpc
    settings = {'clients': [{'id': uuid}]}
    if decryption:
        settings['decryption'] = decryption
    if flow:
        settings['clients'][0]['flow'] = flow
    return {'listen': '127.0.0.1', 'port': port, 'protocol': 'vless', 'settings': settings, 'streamSettings': stream}


def partition_candidates(all_candidates):
    """Partition the candidate list into three disjoint REALITY SNI pools.

    Explicit protocol-specific env files remain supported. When they are not
    supplied, candidates are assigned sequentially and never overlap.
    """
    defaults = {
        'xhttp': all_candidates[0:2],
        'vision': all_candidates[2:4],
        'grpc': all_candidates[4:6],
    }
    names = {}
    for kind, env_name in (
        ('xhttp', 'XHTTP_REALITY_SNI_FILE'),
        ('vision', 'VISION_REALITY_SNI_FILE'),
        ('grpc', 'GRPC_REALITY_SNI_FILE'),
    ):
        names[kind] = candidate_list(env_name, defaults[kind])

    seen = {}
    for kind, values in names.items():
        cleaned = []
        for value in values:
            if value in seen and seen[value] != kind:
                raise SystemExit('ERROR: REALITY SNI overlap: %s is assigned to both %s and %s' % (value, seen[value], kind))
            if value not in seen:
                seen[value] = kind
            if value not in cleaned:
                cleaned.append(value)
        names[kind] = cleaned

    missing = [kind for kind in ('xhttp', 'vision', 'grpc') if not names[kind]]
    if missing:
        raise SystemExit('ERROR: missing REALITY SNI pool(s): %s' % ', '.join(missing))
    return names


def main():
    runtime = read_json(RUNTIME_FILE)
    if not runtime:
        raise SystemExit('ERROR: runtime.json is missing; run runtime_discovery.py first')
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    uuid = persistent('uuid.txt', make_uuid)
    private_file = DATA_DIR / 'reality_private_key.txt'
    public_file = DATA_DIR / 'reality_public_key.txt'
    if private_file.is_file() and public_file.is_file():
        private = private_file.read_text().strip()
        public = public_file.read_text().strip()
    else:
        private, public = make_reality()
        private_file.write_text(private + '\n')
        public_file.write_text(public + '\n')
        os.chmod(private_file, 0o600)
        os.chmod(public_file, 0o600)

    dec_file = DATA_DIR / 'vless_decryption.txt'
    enc_file = DATA_DIR / 'vless_encryption.txt'
    if dec_file.is_file() and enc_file.is_file():
        decryption = dec_file.read_text().strip()
        encryption = enc_file.read_text().strip()
    else:
        try:
            decryption, encryption = make_vless_keys()
        except (subprocess.CalledProcessError, FileNotFoundError):
            decryption, encryption = '', ''
        dec_file.write_text(decryption + '\n')
        enc_file.write_text(encryption + '\n')
        os.chmod(dec_file, 0o600)
        os.chmod(enc_file, 0o600)

    sid = persistent('short_id.txt', short_id)
    target = os.getenv('REALITY_TARGET', 'www.cloudflare.com:443').strip()
    fingerprint = os.getenv('REALITY_FINGERPRINT', 'chrome').strip()
    xhttp_path = os.getenv('XHTTP_PATH', '/xhttp').strip() or '/xhttp'
    xhttp_mode = os.getenv('XHTTP_MODE', 'auto').strip() or 'auto'
    grpc_service = os.getenv('GRPC_SERVICE_NAME', 'grpc').strip() or 'grpc'

    all_candidates = candidate_list('REALITY_SNI_CANDIDATES_FILE', ['www.cloudflare.com', 'www.bing.com', 'www.canva.com', 'www.notion.so', 'store.epicgames.com', 'www.gog.com'])
    pools = partition_candidates(all_candidates)
    xhttp_names = pools['xhttp']
    vision_names = pools['vision']
    grpc_names = pools['grpc']

    ports = runtime['listeners']
    inbounds = [
        inbound(ports['xhttp_reality'], 'xhttp', 'reality', uuid, decryption, reality=reality_settings(target, xhttp_names, private, sid), xhttp={'path': xhttp_path, 'mode': xhttp_mode}),
        inbound(ports['xhttp_tls'], 'xhttp', 'none', uuid, decryption, xhttp={'path': xhttp_path, 'mode': xhttp_mode}),
        inbound(ports['vision_reality'], 'raw', 'reality', uuid, decryption, reality=reality_settings(target, vision_names, private, sid), flow='xtls-rprx-vision'),
        inbound(ports['grpc_reality'], 'grpc', 'reality', uuid, decryption, reality=reality_settings(target, grpc_names, private, sid), grpc={'serviceName': grpc_service}),
    ]

    config = {'log': {'loglevel': os.getenv('XRAY_LOGLEVEL', 'warning')}, 'inbounds': inbounds, 'outbounds': [{'protocol': 'freedom', 'tag': 'direct'}]}
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    os.chmod(tmp, 0o600)
    os.replace(tmp, CONFIG)

    manifest = {
        'uuid': uuid,
        'public_key': public,
        'short_id': sid,
        'encryption': encryption,
        'decryption': decryption,
        'reality_target': target,
        'reality': {'xhttp': xhttp_names, 'vision': vision_names, 'grpc': grpc_names},
        'ports': ports,
        'xhttp_path': xhttp_path,
        'xhttp_mode': xhttp_mode,
        'grpc_service_name': grpc_service,
        'fingerprint': fingerprint,
    }
    manifest_file = DATA_DIR / 'xray-manifest.json'
    manifest_file.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    os.chmod(manifest_file, 0o600)
    print('[xray-config-generator] SNI pools: xhttp=%s vision=%s grpc=%s' % (','.join(xhttp_names), ','.join(vision_names), ','.join(grpc_names)))
    print('[xray-config-generator] generated inbounds: 10087 XHTTP/REALITY, 10086 XHTTP, 10085 Vision/REALITY, 10088 gRPC/REALITY')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
