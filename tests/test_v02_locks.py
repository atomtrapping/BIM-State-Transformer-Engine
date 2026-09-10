"""CI locks for the v0.2 live contracts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import unittest

import gat.demo
from gat.headless import handle_request
from gat.workflows.geometry_authority import authority_from_beam_status


ROOT = Path(__file__).resolve().parents[1]
CORPUS = os.environ.get("GAT_IFC_VALIDATION_ROOT")


class HeadlessBeamLockTests(unittest.TestCase):
    def test_beam_b1_headless_matches_published_lock(self) -> None:
        demo = Path(gat.demo.__file__).parent
        request = json.loads(
            (ROOT / "validation" / "headless-beam-b1-request-v1.json").read_text()
        )
        request["state"]["path"] = str(demo / "beam_model.ifc")
        request["payload"]["material_certificate_path"] = str(
            demo / "material_certificate.json"
        )
        response = handle_request(request)
        lock = json.loads(
            (ROOT / "validation" / "headless-beam-b1-lock-v1.json").read_text()
        )
        result = response["result"]
        self.assertEqual(result["disposition"], lock["disposition"])
        self.assertEqual(result["prior"]["verdict"], lock["prior_verdict"])
        self.assertEqual(result["revised"]["verdict"], lock["revised_verdict"])
        self.assertEqual(result["prior"]["world_digest"], lock["prior_world_digest"])
        self.assertEqual(
            result["revised"]["world_digest"], lock["revised_world_digest"]
        )
        self.assertEqual(result["beam"]["global_id"], lock["beam_global_id"])
        self.assertEqual(
            result["revised"]["computation"]["independent_oracle_id"],
            lock["independent_oracle_id"],
        )
        self.assertFalse(result["assurance"]["may_authorize"])
        self.assertFalse(result["assurance"]["certificate_signature_verified"])


class ClinicDispositionLockTests(unittest.TestCase):
    def test_published_clinic_decision_is_fail_closed(self) -> None:
        payload = json.loads(
            (ROOT / "validation" / "clinic-w460x60-disposition-v1.json").read_text()
        )
        self.assertEqual(payload["disposition"], "REQUEST_EVIDENCE")
        self.assertFalse(payload["may_authorize"])
        self.assertEqual(payload["beam"]["geometry_authority"], "SWEPT_SOLID")
        self.assertEqual(
            authority_from_beam_status(payload["beam"]["geometry_status"]).value,
            "SWEPT_SOLID",
        )
        self.assertEqual(
            payload["contrast"]["length_only_example"]["geometry_authority"],
            "LENGTH_ONLY",
        )
        self.assertFalse(payload["file_boundary"]["pipeline_ready"])

    @unittest.skipUnless(CORPUS, "public IFC corpus not fetched")
    def test_clinic_file_still_matches_published_subject(self) -> None:
        from gat.ifc_audit import audit_ifc_file

        payload = json.loads(
            (ROOT / "validation" / "clinic-w460x60-disposition-v1.json").read_text()
        )
        path = Path(CORPUS) / payload["model"]["destination"]
        report = audit_ifc_file(path)
        self.assertEqual(report.source_sha256, payload["model"]["sha256"])
        self.assertFalse(report.pipeline_ready)
        geometry = report.to_dict()["inventory"]["beam_geometry"]
        self.assertEqual(geometry["status_counts"]["COMPLETE"], 277)
        self.assertEqual(geometry["status_counts"]["LENGTH_ONLY"], 461)
        self.assertFalse(geometry["authorizes_structural_decisions"])
