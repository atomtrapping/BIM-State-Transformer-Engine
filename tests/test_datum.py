"""Vertical datums and the geodetic anchor: the refusals, and the metric's bound.

The bound on the validity-radius metric is verified here against an
independent Vincenty inverse written in this file rather than asserted in the
module, because the module's first choice of radius was wrong in exactly the
direction that would have accepted an out-of-range separation, and it was the
measurement that caught it.
"""
import math
import unittest

from gat.errors import DatumError
from gat.geometry.datum import (
    ADMISSIBLE_ANCHOR_EVIDENCE, ANCHOR_LOSS, EARTH_REFERENCED,
    GEODETIC_ANCHOR_CONTRACT, WGS84_POLAR_RADIUS_OF_CURVATURE_M, AnchorEvidence,
    GeodeticAnchor, GeoidSeparation, VerticalDatum, VerticalDatumKind,
    anchor_standing, height_between, separation_arc_m)

EGM = VerticalDatum("ORTHOMETRIC", "EGM2008")
WGS = VerticalDatum("ELLIPSOIDAL", "WGS84")
FFL = VerticalDatum("LOCAL_ENGINEERING", "FFL 0.000 Block A")
LAT, LON = 51.5007, -0.1246


def anchor(**overrides):
    fields = dict(
        frame_id="model", latitude_deg=LAT, longitude_deg=LON, height_m=12.4,
        vertical_datum=EGM, horizontal_crs="EPSG:4326",
        evidence="SURVEY_CONTROL", horizontal_sigma_m=0.02, vertical_sigma_m=0.03)
    fields.update(overrides)
    return GeodeticAnchor(**fields)


def separation(**overrides):
    fields = dict(
        model="EGM2008", separation_m=45.9, at_latitude_deg=LAT, at_longitude_deg=LON,
        valid_radius_m=2000.0, evidence="SURVEY_CONTROL")
    fields.update(overrides)
    return GeoidSeparation(**fields)


# ── An independent geodesic, for the bound only ──

_A = 6378137.0
_F = 1 / 298.257223563
_B = _A * (1 - _F)


def vincenty_m(lat1, lon1, lat2, lon2):
    """Vincenty inverse on WGS84. None where it does not converge."""
    u1 = math.atan((1 - _F) * math.tan(math.radians(lat1)))
    u2 = math.atan((1 - _F) * math.tan(math.radians(lat2)))
    su1, cu1, su2, cu2 = math.sin(u1), math.cos(u1), math.sin(u2), math.cos(u2)
    length = math.radians(lon2 - lon1)
    lam = length
    for _ in range(200):
        sl, cl = math.sin(lam), math.cos(lam)
        sin_sigma = math.hypot(cu2 * sl, cu1 * su2 - su1 * cu2 * cl)
        if sin_sigma == 0:
            return 0.0
        cos_sigma = su1 * su2 + cu1 * cu2 * cl
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alpha = cu1 * cu2 * sl / sin_sigma
        cos2_alpha = 1 - sin_alpha * sin_alpha
        cos_2sm = cos_sigma - 2 * su1 * su2 / cos2_alpha if cos2_alpha != 0 else 0.0
        c = _F / 16 * cos2_alpha * (4 + _F * (4 - 3 * cos2_alpha))
        previous = lam
        lam = length + (1 - c) * _F * sin_alpha * (
            sigma + c * sin_sigma * (cos_2sm + c * cos_sigma * (-1 + 2 * cos_2sm ** 2)))
        if abs(lam - previous) < 1e-13:
            break
    else:
        return None
    u_sq = cos2_alpha * (_A * _A - _B * _B) / (_B * _B)
    big_a = 1 + u_sq / 16384 * (4096 + u_sq * (-768 + u_sq * (320 - 175 * u_sq)))
    big_b = u_sq / 1024 * (256 + u_sq * (-128 + u_sq * (74 - 47 * u_sq)))
    d_sigma = big_b * sin_sigma * (
        cos_2sm + big_b / 4 * (
            cos_sigma * (-1 + 2 * cos_2sm ** 2)
            - big_b / 6 * cos_2sm * (-3 + 4 * sin_sigma ** 2) * (-3 + 4 * cos_2sm ** 2)))
    return _B * big_a * (sigma - d_sigma)


class VerticalDatumTests(unittest.TestCase):
    def test_there_is_no_member_for_an_unknown_datum(self):
        self.assertEqual(
            {kind.value for kind in VerticalDatumKind},
            {"ELLIPSOIDAL", "ORTHOMETRIC", "LOCAL_ENGINEERING"})
        with self.assertRaises(DatumError) as error:
            VerticalDatum("UNDECLARED", "whatever")
        self.assertIn("the absence of one, not a member", str(error.exception))

    def test_a_reference_surface_is_required_on_every_kind(self):
        for kind in VerticalDatumKind:
            with self.assertRaises(DatumError):
                VerticalDatum(kind, "  ")

    def test_only_two_kinds_place_a_height_on_the_earth(self):
        self.assertEqual(
            EARTH_REFERENCED,
            (VerticalDatumKind.ELLIPSOIDAL, VerticalDatumKind.ORTHOMETRIC))
        self.assertTrue(EGM.earth_referenced)
        self.assertFalse(FFL.earth_referenced)


class AnchorEvidenceTests(unittest.TestCase):
    def test_an_anchor_may_not_be_derived_from_the_model_it_places(self):
        with self.assertRaises(DatumError) as error:
            anchor(evidence="MODEL_DERIVED")
        self.assertIn("circular", str(error.exception))
        self.assertIn("registration is already forbidden", str(error.exception))

    def test_an_anchor_may_not_be_inferred_from_context(self):
        with self.assertRaises(DatumError) as error:
            anchor(evidence="INFERRED_FROM_CONTEXT")
        self.assertIn("a guess with a sigma is still a guess", str(error.exception))

    def test_an_operator_declaration_is_admissible_and_carried_as_theirs(self):
        self.assertIn(AnchorEvidence.OPERATOR_DECLARATION, ADMISSIBLE_ANCHOR_EVIDENCE)
        self.assertEqual(
            anchor(evidence="OPERATOR_DECLARATION").evidence,
            AnchorEvidence.OPERATOR_DECLARATION)

    def test_the_same_refusal_covers_a_geoid_separation(self):
        with self.assertRaises(DatumError):
            separation(evidence="MODEL_DERIVED")


class AnchorUncertaintyTests(unittest.TestCase):
    def test_an_anchor_stating_no_uncertainty_is_refused_here_not_dropped_later(self):
        for field in ("horizontal_sigma_m", "vertical_sigma_m"):
            for value in (0.0, -1.0, float("nan"), float("inf")):
                with self.assertRaises(DatumError, msg=f"{field}={value}"):
                    anchor(**{field: value})

    def test_an_anchor_without_a_declared_datum_is_refused(self):
        with self.assertRaises(DatumError) as error:
            anchor(vertical_datum="EGM2008")
        self.assertIn("the trap this contract was written before", str(error.exception))

    def test_a_position_outside_the_earth_is_refused(self):
        with self.assertRaises(DatumError):
            anchor(latitude_deg=91.0)
        with self.assertRaises(DatumError):
            anchor(longitude_deg=-181.0)


class AnchorStandingTests(unittest.TestCase):
    def test_no_anchor_answers_no_to_both_joins_and_says_why(self):
        standing = anchor_standing(None)
        self.assertFalse(standing["anchored"])
        self.assertFalse(standing["horizontal_join"])
        self.assertFalse(standing["vertical_join"])
        self.assertIn("visual adjacency presented as evidence", standing["because"])

    def test_a_local_datum_joins_horizontally_and_not_vertically(self):
        local = anchor(vertical_datum=FFL, height_m=0.0)
        self.assertFalse(local.vertical_join_available)
        standing = anchor_standing(local)
        self.assertTrue(standing["horizontal_join"])
        self.assertFalse(standing["vertical_join"])
        self.assertIn("the plan position joins and the heights do not", standing["because"])

    def test_an_earth_referenced_datum_joins_both_ways(self):
        standing = anchor_standing(anchor())
        self.assertTrue(standing["horizontal_join"])
        self.assertTrue(standing["vertical_join"])
        self.assertEqual(standing["contract"], GEODETIC_ANCHOR_CONTRACT)

    def test_the_digest_is_of_the_statement_and_moves_with_it(self):
        self.assertEqual(anchor().digest(), anchor().digest())
        self.assertNotEqual(anchor().digest(), anchor(height_m=12.5).digest())
        self.assertNotEqual(anchor().digest(), anchor(vertical_datum=WGS).digest())


class HeightTransformTests(unittest.TestCase):
    def test_the_same_datum_passes_a_height_through_unchanged(self):
        self.assertEqual(height_between(
            12.4, EGM, VerticalDatum("ORTHOMETRIC", "EGM2008"),
            at_latitude_deg=LAT, at_longitude_deg=LON), 12.4)

    def test_a_bare_subtraction_between_the_two_earth_data_is_refused(self):
        with self.assertRaises(DatumError) as error:
            height_between(12.4, EGM, WGS, at_latitude_deg=LAT, at_longitude_deg=LON)
        self.assertIn("offset-in-a-script", str(error.exception))

    def test_the_separation_must_be_from_the_orthometric_datum_s_own_model(self):
        with self.assertRaises(DatumError) as error:
            height_between(12.4, EGM, WGS, at_latitude_deg=LAT, at_longitude_deg=LON,
                           separation=separation(model="EGM96"))
        self.assertIn("a number about another surface", str(error.exception))

    def test_a_separation_used_beyond_its_declared_radius_is_refused(self):
        far = separation(valid_radius_m=100.0)
        with self.assertRaises(DatumError) as error:
            height_between(12.4, EGM, WGS, at_latitude_deg=LAT + 0.2, at_longitude_deg=LON,
                           separation=far)
        self.assertIn("N is a field", str(error.exception))

    def test_within_the_radius_it_converts_and_the_sign_follows_h_equals_capital_h_plus_n(self):
        near = separation(separation_m=45.9)
        ellipsoidal = height_between(
            12.4, EGM, WGS, at_latitude_deg=LAT, at_longitude_deg=LON, separation=near)
        self.assertAlmostEqual(ellipsoidal, 12.4 + 45.9, places=9)
        orthometric = height_between(
            ellipsoidal, WGS, EGM, at_latitude_deg=LAT, at_longitude_deg=LON, separation=near)
        self.assertAlmostEqual(orthometric, 12.4, places=9)

    def test_a_local_engineering_datum_converts_to_nothing(self):
        for other in (EGM, WGS):
            for source, target in ((FFL, other), (other, FFL)):
                with self.assertRaises(DatumError) as error:
                    height_between(1.0, source, target, at_latitude_deg=LAT,
                                   at_longitude_deg=LON, separation=separation())
                self.assertIn("not an arithmetic step", str(error.exception))

    def test_two_references_of_one_kind_need_their_own_declared_transform(self):
        with self.assertRaises(DatumError) as error:
            height_between(12.4, EGM, VerticalDatum("ORTHOMETRIC", "NAVD88"),
                           at_latitude_deg=LAT, at_longitude_deg=LON)
        self.assertIn("its own declared transform", str(error.exception))


class MetricBoundTests(unittest.TestCase):
    """The claim the module makes about its radius, measured rather than argued."""

    def test_the_radius_is_the_polar_radius_of_curvature_and_not_the_semi_major_axis(self):
        self.assertAlmostEqual(WGS84_POLAR_RADIUS_OF_CURVATURE_M, _A * _A / _B, places=6)
        self.assertGreater(WGS84_POLAR_RADIUS_OF_CURVATURE_M, _A)

    def test_the_arc_over_states_the_geodesic_everywhere_it_was_sampled(self):
        pairs = 0
        tightest = None
        for half_degree in range(-179, 180):
            latitude = half_degree / 2
            for d_lat in (0.0, 0.001, 0.01, 0.05, 0.2, 0.9):
                for d_lon in (0.0, 0.001, 0.01, 0.05, 0.2, 0.9):
                    if d_lat == 0.0 and d_lon == 0.0:
                        continue
                    other = latitude + d_lat
                    if not -90.0 <= other <= 90.0:
                        continue
                    geodesic = vincenty_m(latitude, 0.0, other, d_lon)
                    if geodesic is None or geodesic < 1e-6:
                        continue
                    ratio = separation_arc_m(latitude, 0.0, other, d_lon) / geodesic
                    pairs += 1
                    self.assertGreaterEqual(
                        ratio, 1.0,
                        f"under-states at lat={latitude} d_lat={d_lat} d_lon={d_lon}")
                    tightest = ratio if tightest is None else min(tightest, ratio)
        self.assertGreater(pairs, 10000)
        # Tight at the pole, where the prime vertical radius of curvature is a^2/b.
        self.assertLess(tightest, 1.0001)

    def test_the_semi_major_axis_would_under_state_which_is_why_it_is_not_used(self):
        # The case that refuted the first choice: east-west near the pole.
        geodesic = vincenty_m(-80.0, 0.0, -80.0, 0.2)
        on_a = 2 * _A * math.asin(math.sqrt(
            math.cos(math.radians(-80.0)) ** 2 * math.sin(math.radians(0.2) / 2) ** 2))
        self.assertLess(on_a, geodesic)
        self.assertGreaterEqual(separation_arc_m(-80.0, 0.0, -80.0, 0.2), geodesic)

    def test_a_point_is_zero_from_itself(self):
        self.assertEqual(separation_arc_m(LAT, LON, LAT, LON), 0.0)


class LossTests(unittest.TestCase):
    def test_what_the_contract_holds_is_written_where_a_reader_meets_it(self):
        text = " ".join(ANCHOR_LOSS)
        self.assertIn("An anchor is evidence, not geometry", text)
        self.assertIn("no member for an unknown datum", text)
        self.assertIn("may not come from the model", text)
        self.assertIn("no stated uncertainty is refused here", text)
        self.assertIn("offset-in-a-script", text)


if __name__ == "__main__":
    unittest.main()
