"""Vertical datums and the geodetic anchor: where a model sits on the earth.

The frame module is mathematics — rigid transforms, a validated tree, no
earth anywhere in it, and its own docstring says it is "not a source of
calibrated evidence".  That boundary is right and this module does not cross
it.  A datum is not mathematics; it is a declaration about what a height is
measured from, and an anchor is evidence about where a frame's origin stands
on the planet.  They live beside the frame graph and name a frame by id.

WHY THIS EXISTS BEFORE ANY ANCHOR DOES

The workbench already refuses MAP and GLOBE, and refuses them for the right
reason: no IfcSite placement, IfcMapConversion or coordinate reference system
reaches the IR, so nothing can be placed without inventing a position, and an
invented position would be visual adjacency presented as evidence.  What was
missing is the other half — nothing an operator could *supply* would lift that
refusal, however well surveyed.  The refusal was permanent by omission rather
than by rule.  This module is the object that a properly evidenced anchor
would be, so the refusal becomes conditional and the condition is written down.

Declared before the first anchor, deliberately.  The trap it guards against is
the one that makes fusion silently wrong rather than loudly wrong: two heights,
each internally consistent, referencing different vertical data, differing by
tens of metres.  An ellipsoidal height and an orthometric height are not the
same quantity and their difference is the geoid undulation, which varies over
the earth by roughly -105 m to +85 m.  A model that records elevations and no
datum — which is what this engine does today, on every storey and every clear
height — is exactly the producer that springs it.

THREE KINDS, AND NO MEMBER FOR "UNKNOWN"

ELLIPSOIDAL is height above a reference ellipsoid, which is what a GNSS
receiver produces natively.  ORTHOMETRIC is height above a geoid model, which
is what a survey, a map and an engineer mean by "level".  LOCAL_ENGINEERING is
a project datum — finished floor level, a site benchmark, a storey zero — and
it is what an IFC almost always carries.

There is no UNDECLARED member.  An unknown datum is not a datum this module
will hold; it is the absence of an anchor, and the absence refuses rather than
defaults.  A member for it would let a height with no declared origin travel
through every later join looking like a height that had one.

A LOCAL_ENGINEERING anchor is not refused, because it is honest and common: a
building whose horizontal position is surveyed and whose heights are relative
to its own floor slab is a real and well-understood object.  What it does not
have is a vertical join with anything else, and `vertical_join_available` says
so rather than letting the height pass as an earth height.

THE TRANSFORM IS AN OBJECT WITH EVIDENCE, NOT A SUBTRACTION

Converting between ELLIPSOIDAL and ORTHOMETRIC requires the geoid undulation N
at the point in question: h = H + N.  N is a field, not a constant, and a
single value applied across a site is the characteristic silent error — the
"offset applied in a script" that this discipline exists to prevent.  So a
`GeoidSeparation` carries the model that produced it, the point where it was
evaluated, a declared validity radius, and its own evidence; and the transform
refuses when the model does not match the datum being converted, when the point
is outside the declared radius, or when the separation carries no evidence.

LOCAL_ENGINEERING converts to nothing.  A project datum has no declared
relation to the earth — that relation is precisely what a levelling run to a
benchmark establishes, and where one exists the operator supplies an
ORTHOMETRIC anchor instead.  Refusing is not a limitation here; inventing the
relation would be the failure.

THE ANCHOR MAY NOT COME FROM THE MODEL

`scan_likelihood` already refuses to let registration supply the pose used to
claim the model's dimensions are wrong, because a model-derived alignment fed
back as independent evidence about that same model is circular.  A geodetic
anchor inferred from the geometry it places is the same circle at a larger
radius, so MODEL_DERIVED and INFERRED_FROM_CONTEXT are inadmissible evidence
for an anchor and the refusal names the circularity.

AND IT MAY NOT COME WITHOUT UNCERTAINTY

An anchor with no stated uncertainty is refused.  This is not fastidiousness:
the consumer of this engine indexes geodetic positions into cells sized by the
*stated* horizontal uncertainty, and gives no key at all to a position that
states none.  An anchor without sigma would therefore be dropped silently one
system downstream.  Refusing it here makes the failure loud at the producer,
where it can be fixed, rather than quiet at the consumer.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import math

from ..errors import DatumError

GEODETIC_ANCHOR_CONTRACT = "gat-geodetic-anchor-v1"

#: The radius of the sphere the validity-radius check measures arcs on: the
#: WGS84 polar radius of curvature, a^2/b.
#:
#: It is chosen because it is the *largest* principal radius of curvature
#: anywhere on the ellipsoid, so the arc over-states the true geodesic
#: separation: a point marginally inside a declared radius may be refused, and a
#: point outside one is never accepted.  Fail-closed on the metric as well as on
#: the declaration.
#:
#: The semi-major axis is the intuitive choice and is wrong.  A sphere of radius
#: a *under*-states east-west separations at high latitude, where the prime
#: vertical radius of curvature exceeds a — measured, at 80 degrees south a
#: 0.2-degree east-west pair gives 3866 m for a 3879 m geodesic — and an
#: under-stated distance accepts a
#: separation that has travelled outside its declared validity.  The bound is
#: verified numerically against a Vincenty inverse in the tests rather than
#: argued for here, because that is how the first choice was caught.
#:
#: This is not geodesy and is not offered as any.  It answers one question: is
#: this point further from that one than somebody declared their number good for.
WGS84_POLAR_RADIUS_OF_CURVATURE_M = 6378137.0 ** 2 / (6378137.0 * (1 - 1 / 298.257223563))


class VerticalDatumKind(StrEnum):
    ELLIPSOIDAL = "ELLIPSOIDAL"
    ORTHOMETRIC = "ORTHOMETRIC"
    LOCAL_ENGINEERING = "LOCAL_ENGINEERING"


#: The kinds that place a height on the earth.  A local engineering datum does
#: not, which is a fact about it rather than a fault in it.
EARTH_REFERENCED = (VerticalDatumKind.ELLIPSOIDAL, VerticalDatumKind.ORTHOMETRIC)


class AnchorEvidence(StrEnum):
    SURVEY_CONTROL = "SURVEY_CONTROL"
    GNSS_OBSERVATION = "GNSS_OBSERVATION"
    OPERATOR_DECLARATION = "OPERATOR_DECLARATION"
    MODEL_DERIVED = "MODEL_DERIVED"
    INFERRED_FROM_CONTEXT = "INFERRED_FROM_CONTEXT"


#: Evidence an anchor may rest on.  An operator's declaration is admissible and
#: is carried as their assertion, not upgraded: it says a person stood behind a
#: number, which is what promotion at a boundary means and is different in kind
#: from a machine having produced it.
ADMISSIBLE_ANCHOR_EVIDENCE = (
    AnchorEvidence.SURVEY_CONTROL,
    AnchorEvidence.GNSS_OBSERVATION,
    AnchorEvidence.OPERATOR_DECLARATION,
)

INADMISSIBLE_REASON = {
    AnchorEvidence.MODEL_DERIVED: (
        "an anchor derived from the geometry it places is circular: the model "
        "would be supplying the evidence about where the model is, the same "
        "circle registration is already forbidden from closing"
    ),
    AnchorEvidence.INFERRED_FROM_CONTEXT: (
        "an anchor inferred from surrounding context is a guess about where a "
        "building stands, and a guess with a sigma is still a guess"
    ),
}


def _finite(value, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DatumError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise DatumError(f"{name} must be a finite number")
    return number


def _positive(value, name: str) -> float:
    number = _finite(value, name)
    if number <= 0:
        raise DatumError(f"{name} must be greater than zero; {number} states no uncertainty at all")
    return number


def _named(value, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatumError(f"{name} must be a nonempty declared name")
    return value.strip()


@dataclass(frozen=True)
class VerticalDatum:
    """What a height is measured from, declared and never inferred.

    ``reference`` is the thing the zero sits on and its meaning follows the
    kind: the ellipsoid for ELLIPSOIDAL, the geoid model for ORTHOMETRIC, and
    the physical or documentary zero for LOCAL_ENGINEERING.  It is required in
    every case, because "orthometric" without a geoid model names a family of
    surfaces that differ from each other by metres.
    """

    kind: VerticalDatumKind
    reference: str

    def __post_init__(self):
        try:
            kind = VerticalDatumKind(self.kind)
        except ValueError as exc:
            raise DatumError(
                f"{self.kind!r} is not a declared vertical datum kind; an unknown datum is "
                "the absence of one, not a member of the vocabulary"
            ) from exc
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "reference", _named(self.reference, "reference"))

    @property
    def earth_referenced(self) -> bool:
        return self.kind in EARTH_REFERENCED

    def as_record(self) -> dict:
        return {"kind": self.kind.value, "reference": self.reference}


@dataclass(frozen=True)
class GeoidSeparation:
    """N at a declared point, from a declared model, valid within a declared radius.

    The validity radius is supplied rather than derived.  This module holds no
    geoid model and cannot know the local gradient, so it will not invent a
    distance over which somebody else's number stays true; whoever produced N
    states how far it travels, and beyond that the transform refuses.
    """

    model: str
    separation_m: float
    at_latitude_deg: float
    at_longitude_deg: float
    valid_radius_m: float
    evidence: AnchorEvidence

    def __post_init__(self):
        object.__setattr__(self, "model", _named(self.model, "model"))
        object.__setattr__(self, "separation_m", _finite(self.separation_m, "separation_m"))
        object.__setattr__(self, "at_latitude_deg", _latitude(self.at_latitude_deg))
        object.__setattr__(self, "at_longitude_deg", _longitude(self.at_longitude_deg))
        object.__setattr__(self, "valid_radius_m", _positive(self.valid_radius_m, "valid_radius_m"))
        object.__setattr__(self, "evidence", _admissible(self.evidence, "a geoid separation"))


def _latitude(value) -> float:
    degrees = _finite(value, "latitude_deg")
    if not -90.0 <= degrees <= 90.0:
        raise DatumError(f"latitude {degrees} is outside [-90, 90]")
    return degrees


def _longitude(value) -> float:
    degrees = _finite(value, "longitude_deg")
    if not -180.0 <= degrees <= 180.0:
        raise DatumError(f"longitude {degrees} is outside [-180, 180]")
    return degrees


def _admissible(value, subject: str) -> AnchorEvidence:
    try:
        evidence = AnchorEvidence(value)
    except ValueError as exc:
        raise DatumError(f"{value!r} is not a declared evidence kind") from exc
    if evidence not in ADMISSIBLE_ANCHOR_EVIDENCE:
        raise DatumError(
            f"{evidence.value} is inadmissible evidence for {subject}: "
            f"{INADMISSIBLE_REASON[evidence]}"
        )
    return evidence


def separation_arc_m(
    from_latitude_deg: float,
    from_longitude_deg: float,
    to_latitude_deg: float,
    to_longitude_deg: float,
) -> float:
    """Great-circle arc on a sphere of the WGS84 semi-major axis, in metres.

    An over-statement of the geodesic separation on the ellipsoid, chosen so
    the validity check errs toward refusal.  See
    WGS84_POLAR_RADIUS_OF_CURVATURE_M for why it is that radius and not the
    semi-major axis.
    """
    phi1 = math.radians(_latitude(from_latitude_deg))
    phi2 = math.radians(_latitude(to_latitude_deg))
    d_phi = phi2 - phi1
    d_lambda = math.radians(_longitude(to_longitude_deg) - _longitude(from_longitude_deg))
    h = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * WGS84_POLAR_RADIUS_OF_CURVATURE_M * math.asin(math.sqrt(min(1.0, h)))


def height_between(
    height_m: float,
    source: VerticalDatum,
    target: VerticalDatum,
    *,
    at_latitude_deg: float,
    at_longitude_deg: float,
    separation: GeoidSeparation | None = None,
) -> float:
    """Carry a height from one declared datum to another, or refuse.

    Identical data pass through unchanged.  ELLIPSOIDAL and ORTHOMETRIC convert
    through h = H + N and only with a separation whose model matches the
    orthometric datum's reference and whose validity radius covers the point.
    LOCAL_ENGINEERING converts to nothing: a project datum has no declared
    relation to the earth, and inventing one is the error this refuses.
    """
    if not isinstance(source, VerticalDatum) or not isinstance(target, VerticalDatum):
        raise DatumError("both data must be declared VerticalDatum records")
    if source == target:
        return _finite(height_m, "height_m")
    if source.kind == target.kind:
        raise DatumError(
            f"both data are {source.kind.value} but reference different surfaces "
            f"({source.reference!r} and {target.reference!r}); the relation between two "
            "references of one kind is its own declared transform and none was supplied"
        )
    if VerticalDatumKind.LOCAL_ENGINEERING in (source.kind, target.kind):
        raise DatumError(
            f"{source.kind.value} to {target.kind.value} is not a transform this module will "
            "invent: a local engineering datum has no declared relation to the earth, and "
            "establishing one is a levelling run to a benchmark, not an arithmetic step"
        )
    if separation is None:
        raise DatumError(
            "converting between ellipsoidal and orthometric height needs the geoid "
            "separation at this point, declared with its model and validity; a bare "
            "subtraction here is the offset-in-a-script this contract exists to refuse"
        )
    orthometric = source if source.kind is VerticalDatumKind.ORTHOMETRIC else target
    if separation.model != orthometric.reference:
        raise DatumError(
            f"the separation is from {separation.model!r} and the orthometric datum is "
            f"{orthometric.reference!r}; a separation from another model is a number about "
            "another surface"
        )
    distance_m = separation_arc_m(
        separation.at_latitude_deg, separation.at_longitude_deg,
        at_latitude_deg, at_longitude_deg,
    )
    if distance_m > separation.valid_radius_m:
        raise DatumError(
            f"the separation was evaluated {distance_m:.0f} m away and is declared valid "
            f"within {separation.valid_radius_m:.0f} m; N is a field and this is the point "
            "where applying one value across a site stops being true"
        )
    value = _finite(height_m, "height_m")
    # h = H + N: orthometric to ellipsoidal adds the undulation, and back subtracts it.
    return value + separation.separation_m if source.kind is VerticalDatumKind.ORTHOMETRIC else value - separation.separation_m


@dataclass(frozen=True)
class GeodeticAnchor:
    """Where a named frame's origin stands on the earth, with evidence.

    The frame is named, never held: the frame graph stays mathematics and this
    stays evidence, and the two meet by identifier.  Both sigmas are required
    and positive — an anchor that states no uncertainty is refused here rather
    than dropped silently by whatever indexes it later.
    """

    frame_id: str
    latitude_deg: float
    longitude_deg: float
    height_m: float
    vertical_datum: VerticalDatum
    horizontal_crs: str
    evidence: AnchorEvidence
    horizontal_sigma_m: float
    vertical_sigma_m: float

    def __post_init__(self):
        object.__setattr__(self, "frame_id", _named(self.frame_id, "frame_id"))
        object.__setattr__(self, "latitude_deg", _latitude(self.latitude_deg))
        object.__setattr__(self, "longitude_deg", _longitude(self.longitude_deg))
        object.__setattr__(self, "height_m", _finite(self.height_m, "height_m"))
        if not isinstance(self.vertical_datum, VerticalDatum):
            raise DatumError(
                "vertical_datum must be a declared VerticalDatum; a height with no declared "
                "origin is the trap this contract was written before"
            )
        object.__setattr__(self, "horizontal_crs", _named(self.horizontal_crs, "horizontal_crs"))
        object.__setattr__(self, "evidence", _admissible(self.evidence, "a geodetic anchor"))
        object.__setattr__(
            self, "horizontal_sigma_m", _positive(self.horizontal_sigma_m, "horizontal_sigma_m"))
        object.__setattr__(
            self, "vertical_sigma_m", _positive(self.vertical_sigma_m, "vertical_sigma_m"))

    @property
    def vertical_join_available(self) -> bool:
        """Whether this anchor's height can meet another system's height at all."""
        return self.vertical_datum.earth_referenced

    def as_record(self) -> dict:
        return {
            "contract": GEODETIC_ANCHOR_CONTRACT,
            "frame_id": self.frame_id,
            "latitude_deg": self.latitude_deg,
            "longitude_deg": self.longitude_deg,
            "height_m": self.height_m,
            "vertical_datum": self.vertical_datum.as_record(),
            "horizontal_crs": self.horizontal_crs,
            "evidence": self.evidence.value,
            "horizontal_sigma_m": self.horizontal_sigma_m,
            "vertical_sigma_m": self.vertical_sigma_m,
            "vertical_join_available": self.vertical_join_available,
        }

    def digest(self) -> str:
        """Hash this declaration.  Identity of a statement, not of a place."""
        encoded = json.dumps(
            self.as_record(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def anchor_standing(anchor: GeodeticAnchor | None) -> dict:
    """What a consumer may and may not do with the anchoring as it stands.

    Written as a reading rather than a permission.  The horizontal and the
    vertical are answered separately because they fail separately: the common
    real case is a surveyed plan position over a floor-relative height, and
    reporting one verdict for both would either forbid a join that is sound or
    allow one that is not.
    """
    if anchor is None:
        return {
            "contract": GEODETIC_ANCHOR_CONTRACT,
            "anchored": False,
            "horizontal_join": False,
            "vertical_join": False,
            "because": (
                "No geodetic anchor is declared, so the model's frame is related to the "
                "earth by nothing. Placing it would be inventing a position, and an "
                "invented position is visual adjacency presented as evidence."
            ),
        }
    return {
        "contract": GEODETIC_ANCHOR_CONTRACT,
        "anchored": True,
        "horizontal_join": True,
        "vertical_join": anchor.vertical_join_available,
        "anchor_digest": anchor.digest(),
        "because": (
            f"Anchored on {anchor.evidence.value} in {anchor.horizontal_crs} to "
            f"±{anchor.horizontal_sigma_m} m horizontally. Heights are "
            f"{anchor.vertical_datum.kind.value} from {anchor.vertical_datum.reference!r} "
            f"to ±{anchor.vertical_sigma_m} m"
            + (
                ", which places them on the earth and lets them meet another system's heights."
                if anchor.vertical_join_available else
                ", which is a project zero with no declared relation to the earth: the plan "
                "position joins and the heights do not."
            )
        ),
    }


ANCHOR_LOSS = (
    "An anchor is evidence, not geometry. The frame graph stays mathematics and this stays a "
    "declaration about the world; they meet by frame identifier and nothing else.",
    "There is no member for an unknown datum. An undeclared height origin is the absence of an "
    "anchor, which refuses, rather than a value that travels through later joins looking declared.",
    "The anchor may not come from the model. MODEL_DERIVED and INFERRED_FROM_CONTEXT are refused, "
    "because a model supplying the evidence for where the model is closes the same circle that "
    "registration is already forbidden to close.",
    "An anchor with no stated uncertainty is refused here rather than dropped silently later. The "
    "consumer indexes positions into cells sized by the stated uncertainty and gives no key to a "
    "position that states none.",
    "The ellipsoidal-orthometric transform is an object with a model, a point, a validity radius "
    "and its own evidence. N is a field; one value applied across a site is the offset-in-a-script "
    "that makes fusion silently wrong instead of loudly wrong.",
    "A local engineering datum converts to nothing, and that is honest rather than limiting. The "
    "relation between a floor slab and the earth is established by a levelling run, and where one "
    "exists the operator supplies an orthometric anchor instead.",
    "Horizontal and vertical standing are answered separately, because a surveyed plan position "
    "over a floor-relative height is the common real case and one verdict for both would either "
    "forbid a sound join or allow an unsound one.",
)
