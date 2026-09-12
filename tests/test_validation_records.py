"""Everything in `validation/` must be something the engine actually produced.

The directory used to hold hand-written claims wearing the costume of test
fixtures: world digests that no path form reproduced, `source` fields naming
files that did not exist, a geometry authority of SWEPT_SOLID on a model with
no body representation at all. Nine of eleven records were referenced by no
code, so nothing ever noticed.

These tests re-run the producers in `validation/records.py` and compare
byte-for-byte against the shipped files. A record can no longer be edited by
hand, and a change in a disposition or a digest cannot land quietly.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from validation.records import CORPUS_DEPENDENT, build_all, dumps


REPO = Path(__file__).resolve().parent.parent
VALIDATION = REPO / "validation"
CORPUS = os.environ.get("GAT_IFC_VALIDATION_ROOT")

#: Records produced by something other than validation/records.py. Each one
#: is load-bearing and read by code elsewhere in the tree.
EXTERNALLY_PRODUCED = {
    # the engineering oracle, transcribed from the AISC design-example volume
    "aisc360-22-f1-1b-v1.json",
    # the commit-pinned public model manifest, consumed by fetch_ifc_corpus.py
    "ifc-corpus-v1.json",
    # an explicitly environment-specific scale reference; it names the host it
    # was measured on and is a reference, not a threshold
    "incremental-scale-reference-v1.json",
}


class ShippedRecordsTests(unittest.TestCase):
    # Building the records parses a 19 MB corpus model, so do it once for the
    # class rather than once per test method.
    records: dict[str, dict]

    @classmethod
    def setUpClass(cls) -> None:
        cls.records = build_all(CORPUS)

    def test_every_generated_record_matches_the_engine(self) -> None:
        for name, record in sorted(self.records.items()):
            with self.subTest(record=name):
                path = VALIDATION / name
                self.assertTrue(path.exists(), f"{name} is missing; regenerate it")
                self.assertEqual(
                    path.read_text(encoding="utf-8"),
                    dumps(record),
                    f"{name} has drifted from what the engine produces. Run "
                    "python validation/regenerate.py and read the diff: a "
                    "changed digest means a changed decision.",
                )

    def test_no_record_is_unaccounted_for(self) -> None:
        """Every JSON in validation/ is either generated here or declared."""
        on_disk = {p.name for p in VALIDATION.glob("*.json")}
        # Corpus-gated records are shipped even on a host that cannot rebuild
        # them, so they are accounted for whether or not this run built them.
        accounted = set(self.records) | EXTERNALLY_PRODUCED | CORPUS_DEPENDENT
        orphans = sorted(on_disk - accounted)
        self.assertEqual(
            orphans,
            [],
            "these records are produced by nothing and verified by nothing: "
            f"{orphans}. Generate them in validation/records.py or remove them.",
        )

    def test_corpus_records_are_present_when_the_corpus_is(self) -> None:
        if not CORPUS:
            self.skipTest("public IFC corpus not fetched")
        for name in sorted(CORPUS_DEPENDENT):
            self.assertIn(name, self.records)


class RecordHonestyTests(unittest.TestCase):
    """Properties the records must have to be evidence rather than assertion."""

    def setUp(self) -> None:
        self.shipped = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in VALIDATION.glob("*.json")
        }

    def test_every_outcome_log_source_exists(self) -> None:
        for row in self.shipped["outcome-log-v1.json"]["rows"]:
            with self.subTest(case=row["case_id"]):
                self.assertTrue(
                    (REPO / row["source"]).exists(),
                    f"{row['case_id']} cites {row['source']}, which does not exist",
                )

    def test_no_record_advertises_placeholder_digests(self) -> None:
        for name, record in sorted(self.shipped.items()):
            note = str(record.get("note", "")).lower()
            with self.subTest(record=name):
                for phrase in ("placeholder", "will not verify", "illustrative"):
                    self.assertNotIn(
                        phrase,
                        note,
                        f"{name} admits its own numbers are not real",
                    )

    def test_the_beam_record_does_not_claim_geometry_it_lacks(self) -> None:
        """The shipped beam model has no body; the record must say so."""
        support = self.shipped["beam-b1-disposition-v1.json"]["support"]
        self.assertEqual(support["beam_geometry_status"], "BLOCKED")
        self.assertEqual(support["geometry_authority"], "INSUFFICIENT")
        self.assertEqual(
            support["section_modulus_source"], "GAT_Structural declared property set"
        )

    def test_the_field_packet_signature_verifies(self) -> None:
        from gat.engineering.certificate_signature import verify_certificate_bytes

        packet = self.shipped["field-packet-beam-b1-v1.json"]
        source = REPO / packet["source_path"]
        self.assertTrue(packet["signature_verified"])
        self.assertTrue(
            verify_certificate_bytes(source.read_bytes(), packet["signature"]),
            "the shipped HMAC does not verify against the certificate bytes",
        )

    def test_tampered_certificate_bytes_fail_the_packet_signature(self) -> None:
        from gat.engineering.certificate_signature import verify_certificate_bytes

        packet = self.shipped["field-packet-beam-b1-v1.json"]
        source = (REPO / packet["source_path"]).read_bytes()
        self.assertFalse(
            verify_certificate_bytes(source + b" ", packet["signature"]),
            "the packet signature accepted altered certificate bytes",
        )


if __name__ == "__main__":
    unittest.main()
