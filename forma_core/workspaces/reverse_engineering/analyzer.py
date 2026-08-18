"""Bounded local inspection for inline raster image artifacts."""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from io import BytesIO

from PIL import Image, ImageChops, UnidentifiedImageError

from forma_core.workspaces.design_briefs import DesignBrief
from forma_core.workspaces.reverse_engineering.models import (
    AnalyzedArtifact,
    ReverseEngineeringArtifactReference,
    ReverseEngineeringConfidence,
    ReverseEngineeringEvidence,
    ReverseEngineeringEvidenceSource,
    ReverseEngineeringFinding,
    ReverseEngineeringFindingKind,
    ReverseEngineeringReportDraft,
)


SUPPORTED_IMAGE_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_ARTIFACT_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
_DATA_URI = re.compile(r"^data:(?P<media_type>[^;,]+);base64,(?P<data>.+)$", re.DOTALL)
_FORMAT_MEDIA_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


class ReverseEngineeringError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.context = context or {}


def _decode_image(reference: ReverseEngineeringArtifactReference) -> tuple[bytes, Image.Image, str]:
    claimed_media_type = reference.media_type.split(";", 1)[0].strip().lower()
    if claimed_media_type not in SUPPORTED_IMAGE_MEDIA_TYPES:
        raise ReverseEngineeringError(
            "unsupported_reverse_engineering_artifact",
            f"Artifact media type '{claimed_media_type}' is not supported.",
            context={"supported_media_types": sorted(SUPPORTED_IMAGE_MEDIA_TYPES)},
        )
    match = _DATA_URI.fullmatch(reference.uri)
    if match is None:
        raise ReverseEngineeringError(
            "artifact_content_unavailable",
            "The baseline Reverse-Engineering worker requires an inline base64 image data URI.",
            context={"artifact_id": reference.artifact_id},
        )
    data_media_type = match.group("media_type").strip().lower()
    if data_media_type != claimed_media_type:
        raise ReverseEngineeringError(
            "artifact_media_type_mismatch",
            "Artifact media type does not match its inline data URI.",
            context={"claimed_media_type": claimed_media_type, "data_media_type": data_media_type},
        )
    encoded = match.group("data")
    if len(encoded) > (MAX_ARTIFACT_BYTES * 4 // 3) + 8:
        raise ReverseEngineeringError(
            "reverse_engineering_artifact_too_large",
            "Artifact exceeds the maximum supported inline image size.",
            context={"max_bytes": MAX_ARTIFACT_BYTES},
        )
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ReverseEngineeringError(
            "invalid_reverse_engineering_artifact",
            "Artifact data URI does not contain valid base64 image data.",
        ) from exc
    if not content or len(content) > MAX_ARTIFACT_BYTES:
        raise ReverseEngineeringError(
            "reverse_engineering_artifact_too_large",
            "Artifact is empty or exceeds the maximum supported inline image size.",
            context={"max_bytes": MAX_ARTIFACT_BYTES},
        )
    try:
        with Image.open(BytesIO(content)) as opened:
            actual_media_type = _FORMAT_MEDIA_TYPES.get(str(opened.format or "").upper())
            if actual_media_type is None or actual_media_type != claimed_media_type:
                raise ReverseEngineeringError(
                    "artifact_media_type_mismatch",
                    "Decoded image format does not match the declared artifact media type.",
                    context={
                        "claimed_media_type": claimed_media_type,
                        "decoded_media_type": actual_media_type,
                    },
                )
            width, height = opened.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise ReverseEngineeringError(
                    "reverse_engineering_artifact_too_large",
                    "Decoded image dimensions exceed the supported inspection limit.",
                    context={"max_pixels": MAX_IMAGE_PIXELS, "width": width, "height": height},
                )
            opened.load()
            image = opened.convert("RGB")
    except ReverseEngineeringError:
        raise
    except Image.DecompressionBombError as exc:
        raise ReverseEngineeringError(
            "reverse_engineering_artifact_too_large",
            "Decoded image dimensions exceed the supported inspection limit.",
            context={"max_pixels": MAX_IMAGE_PIXELS},
        ) from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ReverseEngineeringError(
            "invalid_reverse_engineering_artifact",
            "Artifact bytes could not be decoded as a supported image.",
        ) from exc
    return content, image, claimed_media_type


def inspect_inline_image(
    reference: ReverseEngineeringArtifactReference,
    design_brief: DesignBrief,
) -> ReverseEngineeringReportDraft:
    content, image, media_type = _decode_image(reference)
    width, height = image.size
    grayscale = image.convert("L")
    minimum, maximum = grayscale.getextrema()
    tonal_span = maximum - minimum
    background = Image.new("RGB", image.size, image.getpixel((0, 0)))
    foreground_box = ImageChops.difference(image, background).getbbox()
    ambiguous = foreground_box is None or tonal_span < 12

    evidence = [
        ReverseEngineeringEvidence(
            evidence_id="artifact-format",
            source=ReverseEngineeringEvidenceSource.ARTIFACT,
            observation=f"Decoded {media_type} image is {width} by {height} pixels.",
            method="Verified image decoder metadata.",
        ),
        ReverseEngineeringEvidence(
            evidence_id="artifact-tonal-range",
            source=ReverseEngineeringEvidenceSource.ARTIFACT,
            observation=f"Grayscale tonal range spans {tonal_span} levels ({minimum} to {maximum}).",
            method="Computed extrema after grayscale conversion.",
        ),
        ReverseEngineeringEvidence(
            evidence_id="brief-intent",
            source=ReverseEngineeringEvidenceSource.DESIGN_BRIEF,
            observation=f"Frozen DesignBrief intent: {design_brief.intent}",
            method="Read exact persisted DesignBrief context.",
        ),
    ]

    orientation = "square" if width == height else ("landscape" if width > height else "portrait")
    findings = [
        ReverseEngineeringFinding(
            finding_id="property-image-envelope",
            kind=ReverseEngineeringFindingKind.PROPERTY,
            inference=f"The supplied artifact is a {orientation} raster image with a {width}:{height} pixel envelope.",
            evidence_ids=["artifact-format"],
            confidence=ReverseEngineeringConfidence.HIGH,
            uncertainties=["Pixel dimensions do not establish real-world physical dimensions or scale."],
        )
    ]
    if ambiguous:
        findings.append(ReverseEngineeringFinding(
            finding_id="structure-foreground",
            kind=ReverseEngineeringFindingKind.STRUCTURE,
            inference="No distinct foreground structure can be resolved from the supplied raster evidence.",
            evidence_ids=["artifact-tonal-range"],
            confidence=ReverseEngineeringConfidence.LOW,
            uncertainties=[
                "Low contrast or a uniform background prevents reliable part, boundary, and connection inference."
            ],
        ))
    else:
        left, top, right, bottom = foreground_box
        box_area = (right - left) * (bottom - top)
        coverage = round(box_area / (width * height) * 100, 1)
        evidence.append(ReverseEngineeringEvidence(
            evidence_id="artifact-foreground-bounds",
            source=ReverseEngineeringEvidenceSource.ARTIFACT,
            observation=(
                f"Foreground difference from the top-left background sample spans "
                f"({left}, {top}) to ({right}, {bottom}), covering a {coverage}% bounding box."
            ),
            method="Compared RGB pixels with the top-left background color.",
        ))
        findings.append(ReverseEngineeringFinding(
            finding_id="structure-foreground",
            kind=ReverseEngineeringFindingKind.STRUCTURE,
            inference="The artifact contains a visually distinct foreground region that may represent design structure.",
            evidence_ids=["artifact-tonal-range", "artifact-foreground-bounds"],
            confidence=ReverseEngineeringConfidence.MEDIUM,
            uncertainties=[
                "Pixel segmentation alone cannot identify components, connectivity, occlusion, or physical scale."
            ],
        ))
    findings.append(ReverseEngineeringFinding(
        finding_id="function-brief-alignment",
        kind=ReverseEngineeringFindingKind.FUNCTION,
        inference=f"The artifact may relate to the DesignBrief intent: {design_brief.intent}",
        evidence_ids=["brief-intent", "artifact-format"],
        confidence=ReverseEngineeringConfidence.LOW,
        uncertainties=[
            "The frozen brief supplies context, but this baseline pixel analysis cannot verify depicted function."
        ],
    ))

    overall_uncertainties = [
        "The baseline analyzer uses image metadata and pixel-level segmentation, not semantic object recognition.",
        "No hidden geometry, electrical connectivity, materials, or physical scale can be established from this image alone.",
    ]
    if ambiguous:
        overall_uncertainties.insert(0, "The image is visually ambiguous because it has no reliable foreground separation.")
    return ReverseEngineeringReportDraft(
        artifact=AnalyzedArtifact(
            artifact_id=reference.artifact_id,
            kind=reference.kind,
            media_type=media_type,
            content_sha256=hashlib.sha256(content).hexdigest(),
            width_px=width,
            height_px=height,
        ),
        evidence=evidence,
        findings=findings,
        ambiguous=ambiguous,
        overall_uncertainties=overall_uncertainties,
    )


__all__ = [
    "MAX_ARTIFACT_BYTES",
    "MAX_IMAGE_PIXELS",
    "SUPPORTED_IMAGE_MEDIA_TYPES",
    "ReverseEngineeringError",
    "inspect_inline_image",
]
