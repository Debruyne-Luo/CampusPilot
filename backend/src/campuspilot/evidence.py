"""Shared provenance contracts; authority is independent of human verification."""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=120)]
Text = Annotated[str, Field(min_length=1, pattern=r"\S")]


class Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class SyntheticEvidence(Contract):
    evidence_id: Identifier
    source_id: Identifier
    source_reference: Text
    version: Text = "fixture-v1"
    locator: Text
    applicability: Text = "synthetic demo only; not university information"
    verification_status: Literal["synthetic"] = "synthetic"
    synthetic: Literal[True] = True


class SourceEvidence(Contract):
    evidence_id: Identifier
    source_id: Identifier
    source_reference: Text
    source_url: HttpUrl
    publisher: Text
    source_authority: Literal["official_university", "official_department", "official_college"]
    version: Text
    locator: Text
    applicability: Text
    source_published_at: date | None = None
    source_updated_at: date | None = None
    retrieved_at: date
    verification_status: Literal["needs_review", "verified"] = "needs_review"
    verified_at: date | None = None
    reviewer: Text | None = None
    access_method: Literal["direct", "search_index", "user_provided_file"]
    source_file_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None
    limitations: tuple[Text, ...] = ()
    synthetic: Literal[False] = False

    @model_validator(mode="after")
    def review_metadata(self) -> Self:
        if self.source_url.username or self.source_url.password:
            raise ValueError("Source URLs cannot contain credentials")
        if self.verification_status == "verified":
            if self.verified_at is None or self.reviewer is None:
                raise ValueError("Verified evidence requires a reviewer and verification date")
        elif self.verified_at is not None or self.reviewer is not None:
            raise ValueError("Unreviewed evidence cannot carry a completed review")
        return self


Evidence = Annotated[SyntheticEvidence | SourceEvidence, Field(discriminator="synthetic")]


class FieldEvidence(Contract):
    field_path: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")]
    evidence_ids: tuple[Identifier, ...]
    note: Text

    @model_validator(mode="after")
    def unique_references(self) -> Self:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Duplicate evidence reference")
        return self


class Payload(Contract):
    synthetic: bool
    evidence: tuple[Evidence, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def same_origin(self) -> Self:
        if any(item.synthetic != self.synthetic for item in self.evidence):
            raise ValueError("Synthetic and source evidence cannot be mixed")
        if len({item.evidence_id for item in self.evidence}) != len(self.evidence):
            raise ValueError("Duplicate payload evidence")
        return self


class SyntheticPayload(Payload):
    synthetic: Literal[True] = True
    evidence: tuple[SyntheticEvidence, ...] = Field(min_length=1)
