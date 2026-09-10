"""Detachable HMAC identity for material-certificate bytes.

The certificate JSON schema stays exact-keys v1. A sibling ``.sig.json``
file binds those bytes to a named key. Unknown keys and bad MACs fail
closed. This is identity, not issuer accreditation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path


ALGORITHM = "hmac-sha256-v1"
TEST_KEY_ID = "gat-test-cert-key-v1"
TEST_KEY_SECRET = b"gat-test-cert-key-v1-not-for-production"


@dataclass(frozen=True)
class CertificateSignature:
    key_id: str
    algorithm: str
    digest: str
    mac: str

    def to_dict(self) -> dict[str, str]:
        return {
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "digest": self.digest,
            "mac": self.mac,
        }


def known_keys() -> dict[str, bytes]:
    return {TEST_KEY_ID: TEST_KEY_SECRET}


def sign_certificate_bytes(
    source_bytes: bytes,
    *,
    key_id: str = TEST_KEY_ID,
    keys: dict[str, bytes] | None = None,
) -> CertificateSignature:
    secret = (keys or known_keys()).get(key_id)
    if secret is None:
        raise ValueError(f"unknown certificate key {key_id!r}")
    digest = hashlib.sha256(source_bytes).hexdigest()
    mac = hmac.new(secret, source_bytes, hashlib.sha256).hexdigest()
    return CertificateSignature(key_id, ALGORITHM, digest, mac)


def verify_certificate_bytes(
    source_bytes: bytes,
    signature: CertificateSignature | dict[str, str],
    *,
    keys: dict[str, bytes] | None = None,
) -> bool:
    if isinstance(signature, dict):
        signature = CertificateSignature(
            signature["key_id"],
            signature["algorithm"],
            signature["digest"],
            signature["mac"],
        )
    if signature.algorithm != ALGORITHM:
        return False
    secret = (keys or known_keys()).get(signature.key_id)
    if secret is None:
        return False
    digest = hashlib.sha256(source_bytes).hexdigest()
    if not hmac.compare_digest(digest, signature.digest):
        return False
    expected = hmac.new(secret, source_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.mac)


def write_signature(path: str | Path, signature: CertificateSignature) -> None:
    Path(path).write_text(
        json.dumps(signature.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_signature(path: str | Path) -> CertificateSignature:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return CertificateSignature(
        payload["key_id"],
        payload["algorithm"],
        payload["digest"],
        payload["mac"],
    )
