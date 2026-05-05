"""
Генерация JWT-токенов для приватного embed DataLens.
Алгоритм PS256 — RSA-PSS + SHA256, PKCS#1 private key.
"""

import base64
import json
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(
        json.dumps(data, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()


def _load_private_key(key_secret: str):
    raw = key_secret.strip().strip('"').strip("'")
    if "-----BEGIN" in raw:
        return serialization.load_pem_private_key(raw.encode(), password=None)
    b64 = "".join(raw.split())
    pem = f"-----BEGIN RSA PRIVATE KEY-----\n{b64}\n-----END RSA PRIVATE KEY-----\n"
    return serialization.load_pem_private_key(pem.encode(), password=None)


def make_embed_token(embed_id: str, key_secret: str, ttl: int = 3600) -> str:
    """
    Подписанный PS256 JWT для DataLens private embed.

    iframe src = https://datalens.ru/embeds/dash#dl_embed_token=<token>
    """
    now = int(time.time())
    header = _b64({"alg": "PS256", "typ": "JWT"})
    payload = _b64({
        "embedId": embed_id,
        "dlEmbedService": "YC_DATALENS_EMBEDDING_SERVICE_MARK",
        "iat": now,
        "exp": now + ttl,
    })
    signing = f"{header}.{payload}"
    private_key = _load_private_key(key_secret)
    sig_bytes = private_key.sign(
        signing.encode(),
        asym_padding.PSS(
            mgf=asym_padding.MGF1(hashes.SHA256()),
            salt_length=32,
        ),
        hashes.SHA256(),
    )
    sig = base64.urlsafe_b64encode(sig_bytes).rstrip(b"=").decode()
    return f"{signing}.{sig}"
