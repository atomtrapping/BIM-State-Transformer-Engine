"""Certificate bytes can be believed or refused by a named key."""

from __future__ import annotations

from pathlib import Path
import unittest

import gat.demo
from gat.engineering.certificate_signature import (
    TEST_KEY_ID,
    sign_certificate_bytes,
    verify_certificate_bytes,
)
from gat.engineering.material_certificate import read_material_certificate


class CertificateSignatureTests(unittest.TestCase):
    def test_known_key_accepts_matching_mac(self) -> None:
        path = Path(gat.demo.__file__).parent / "material_certificate.json"
        body = path.read_bytes()
        signature = sign_certificate_bytes(body)
        self.assertEqual(signature.key_id, TEST_KEY_ID)
        self.assertTrue(verify_certificate_bytes(body, signature))
        self.assertFalse(verify_certificate_bytes(body + b" ", signature))
        self.assertFalse(
            verify_certificate_bytes(body, signature, keys={"other": b"nope"})
        )
        certificate = read_material_certificate(path)
        self.assertEqual(certificate.source_digest, signature.digest)


if __name__ == "__main__":
    unittest.main()
