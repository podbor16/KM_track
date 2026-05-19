"""
Добавляет GitHub Actions секреты для деплоя на VPS.
Требует GITHUB_TOKEN с правами repo (Settings → Developer settings → Personal access tokens).
"""
import base64
import json
import os
import sys
import urllib.request
from base64 import b64encode
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

REPO = "podbor16/KM_track"
TOKEN = os.environ.get("GITHUB_TOKEN", "")

SECRETS = {
    "VPS_HOST": VPS_HOST,
    "VPS_USER": "root",
    "VPS_PASSWORD": VPS_PASSWORD,
}

if not TOKEN:
    print("Нужен GITHUB_TOKEN:")
    print("  $env:GITHUB_TOKEN = 'ghp_...'")
    print("  conda run -n base python deploy/add_github_secrets.py")
    sys.exit(1)

# Получаем public key репозитория для шифрования секретов
def api(method, path, data=None):
    url = f"https://api.github.com{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

# nacl для шифрования (требуется PyNaCl)
try:
    from nacl import encoding, public
    def encrypt(pub_key_b64: str, secret_value: str) -> str:
        pk = public.PublicKey(pub_key_b64.encode(), encoding.Base64Encoder)
        box = public.SealedBox(pk)
        return b64encode(box.encrypt(secret_value.encode())).decode()
    HAS_NACL = True
except ImportError:
    HAS_NACL = False

if not HAS_NACL:
    print("Установите PyNaCl: conda run -n base pip install PyNaCl")
    sys.exit(1)

key_data = api("GET", f"/repos/{REPO}/actions/secrets/public-key")
key_id = key_data["key_id"]
pub_key = key_data["key"]

for name, value in SECRETS.items():
    encrypted = encrypt(pub_key, value)
    api("PUT", f"/repos/{REPO}/actions/secrets/{name}", {
        "encrypted_value": encrypted,
        "key_id": key_id,
    })
    print(f"✓ {name}")

print("\nСекреты добавлены. Проверь: https://github.com/podbor16/KM_track/settings/secrets/actions")
