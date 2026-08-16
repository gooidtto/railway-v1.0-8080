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
        raise SystemExit('ERROR: unable to parse xray x25519 output')
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
        values = [x.strip().lower() for x in path.read_text(encoding='utf-8').splitlines() if x.strip() and not x.lstrip().startswith('#')]
    return list(dict.fromkeys(values or fallback))


def validate_pools(names):
    seen = {}
    clean = {}
    for kind in ('xhttp', 'vision', 'grpc'):
        values = []
        for value in names.get(kind, []):
            value = value.strip().lower()
            if not value:
                continue
            if value in seen and seen[value] != kind:
                return None, 'REALITY SNI overlap: %s is assigned to both %s and %s' % (value, seen[value], kind)
            seen[value] = kind
            if value not in values:
                values.append(value)
        clean[kind] = values
    missing = [k for k in ('xhttp', 'vision', 'grpc') if not clean[k]]
    if missing:
        return None, 'missing REALITY SNI pool(s): %s' % ', '.join(missing)
    return clean, ''


def partition_candidates(all_candidates):
    canonical = {'xhttp': all_candidates[0:2], 'vision': all_candidates[2:4], 'grpc': all_candidates[4:6]}
    if any(not canonical[k] for k in canonical):
        raise SystemExit('ERROR: canonical REALITY SNI file must provide at least 6 unique entries (2 per protocol)')
    names = ('XHTTP_REALITY_SNI_FILE', 'VISION_REALITY_SNI_FILE', 'GRPC_REALITY_SNI_FILE')
    if any(os.getenv(n, '').strip() for n in names):
        overrides = {'xhttp': candidate_list(names[0], []), 'vision': candidate_list(names[1], []), 'grpc': candidate_list(names[2], [])}
        valid, error = validate_pools(overrides)
        if valid:
            print('[xray-config-generator] using explicit protocol SNI overrides', flush=True)
            return valid
        print('[xray-config-generator] WARNING: ignoring invalid/stale SNI environment override: %s' % error, flush=True)
    valid, error = validate_pools(canonical)
    if not valid:
        raise SystemExit('ERROR: %s' % error)
    return valid


def reality_settings(target, server_name, private, sid):
    return {'show': False, 'target': target, 'xver': 0, 'serverNames': [server_name], 'privateKey': private, 'shortIds': [sid]}


def xhttp_settings(path, mode):
    return {
        'path': path,
        'mode': mode,
        'extra': {
            'xPaddingBytes': '100-1000',
            'scStreamUpServerSecs': '20-80',
            'scMaxEachPostBytes': 1000000,
        },
    }


def inbound(port, network, security, uuid, decryption, reality=None, xhttp=None, grpc=None, flow=None):
    stream = {'network': network, 'security': security}
    if reality:
        stream['realitySettings'] = reality
    if xhttp:
        stream['xhttpSettings'] = xhttp
    if grpc:
        stream['grpcSettings'] = grpc
    settings = {'clients': [{'id': uuid}], 'decryption': decryption or 'none'}
    if flow:
        settings['clients'][0]['flow'] = flow
    return {'listen': '127.0.0.1', 'port': port, 'protocol': 'vless', 'settings': settings, 'streamSettings': stream}


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

    enable_encryption = os.getenv('ENABLE_VLESS_ENCRYPTION', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    dec_file = DATA_DIR / 'vless_decryption.txt'
    enc_file = DATA_DIR / 'vless_encryption.txt'
    if enable_encryption:
        if dec_file.is_file() and enc_file.is_file() and dec_file.read_text().strip() and enc_file.read_text().strip():
            decryption = dec_file.read_text().strip()
            encryption = enc_file.read_text().strip()
        else:
            try:
                decryption, encryption = make_vless_keys()
            except (subprocess.CalledProcessError, FileNotFoundError):
                raise SystemExit('ERROR: ENABLE_VLESS_ENCRYPTION is enabled but xray vlessenc failed')
            if not decryption or not encryption:
                raise SystemExit('ERROR: ENABLE_VLESS_ENCRYPTION is enabled but ML-KEM keys could not be generated')
            dec_file.write_text(decryption + '\n', encoding='utf-8')
            enc_file.write_text(encryption + '\n', encoding='utf-8')
            os.chmod(dec_file, 0o600)
            os.chmod(enc_file, 0o600)
    else:
        decryption = 'none'
        encryption = ''
        dec_file.write_text('none\n', encoding='utf-8')
        enc_file.write_text('\n', encoding='utf-8')
        os.chmod(dec_file, 0o600)
        os.chmod(enc_file, 0o600)

    sid = persistent('short_id.txt', short_id)
    fingerprint = os.getenv('REALITY_FINGERPRINT', 'chrome').strip()
    xhttp_path = os.getenv('XHTTP_PATH', '/xhttp').strip() or '/xhttp'
    xhttp_mode = os.getenv('XHTTP_MODE', 'auto').strip() or 'auto'
    grpc_service = os.getenv('GRPC_SERVICE_NAME', 'grpc').strip() or 'grpc'

    all_candidates = candidate_list('REALITY_SNI_CANDIDATES_FILE', [
        'www.cloudflare.com', 'www.bing.com', 'www.canva.com',
        'www.notion.so', 'store.epicgames.com', 'www.gog.com'
    ])
    pools = partition_candidates(all_candidates)
    selected = {kind: pools[kind][0] for kind in ('xhttp', 'vision', 'grpc')}
    target_overrides = {
        'xhttp': os.getenv('XHTTP_REALITY_TARGET', '').strip(),
        'vision': os.getenv('VISION_REALITY_TARGET', '').strip(),
        'grpc': os.getenv('GRPC_REALITY_TARGET', '').strip(),
    }
    for kind in selected:
        if target_overrides[kind]:
            selected[kind] = target_overrides[kind].split(':', 1)[0].lower()

    ports = runtime['listeners']
    inbounds = [
        inbound(ports['xhttp_reality'], 'xhttp', 'reality', uuid, decryption,
                reality=reality_settings(selected['xhttp'] + ':443', selected['xhttp'], private, sid),
                xhttp=xhttp_settings(xhttp_path, xhttp_mode)),
        inbound(ports['xhttp_tls'], 'xhttp', 'none', uuid, decryption,
                xhttp=xhttp_settings(xhttp_path, xhttp_mode)),
        inbound(ports['vision_reality'], 'raw', 'reality', uuid, decryption,
                reality=reality_settings(selected['vision'] + ':443', selected['vision'], private, sid),
                flow='xtls-rprx-vision'),
        inbound(ports['grpc_reality'], 'grpc', 'reality', uuid, decryption,
                reality=reality_settings(selected['grpc'] + ':443', selected['grpc'], private, sid),
                grpc={'serviceName': grpc_service}),
    ]

    loglevel = os.getenv('XRAY_LOGLEVEL', 'info').strip() or 'info'
    config = {'log': {'loglevel': loglevel}, 'inbounds': inbounds,
              'outbounds': [{'protocol': 'freedom', 'tag': 'direct'}]}
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    os.chmod(tmp, 0o600)
    os.replace(tmp, CONFIG)

    manifest = {
        'schema': 3, 'uuid': uuid, 'public_key': public, 'short_id': sid,
        'encryption': encryption, 'decryption': decryption,
        'vless_encryption_enabled': enable_encryption,
        'reality': {'xhttp': [selected['xhttp']], 'vision': [selected['vision']], 'grpc': [selected['grpc']]},
        'reality_targets': {kind: selected[kind] + ':443' for kind in selected},
        'ports': ports, 'xhttp_path': xhttp_path, 'xhttp_mode': xhttp_mode,
        'grpc_service_name': grpc_service, 'fingerprint': fingerprint,
    }
    mf = DATA_DIR / 'xray-manifest.json'
    mf.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    os.chmod(mf, 0o600)

    print('[xray-config-generator] VLESS encryption=%s' % ('enabled' if enable_encryption else 'disabled (compatibility mode)'), flush=True)
    print('[xray-config-generator] XHTTP mode=%s padding=100-1000 keepalive=20-80s' % xhttp_mode, flush=True)
    print('[xray-config-generator] REALITY profiles: xhttp=%s vision=%s grpc=%s' % (selected['xhttp'], selected['vision'], selected['grpc']), flush=True)
    print('[xray-config-generator] listeners: xhttp_reality=127.0.0.1:%s xhttp_tls=127.0.0.1:%s vision_reality=127.0.0.1:%s grpc_reality=127.0.0.1:%s' % (
        ports['xhttp_reality'], ports['xhttp_tls'], ports['vision_reality'], ports['grpc_reality']), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
