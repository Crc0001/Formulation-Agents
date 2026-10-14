"""Structured literature synthesis independent from simulation configuration."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, HttpUrl, model_validator


class EvidenceLocator(BaseModel):
    kind: Literal["example", "paragraph", "page", "table", "claim", "section", "figure"]
    label: str
    page: str | None = None
    paragraph: str | None = None
    quotedText: str | None = None


class SourceRecord(BaseModel):
    sourceId: str
    sourceType: Literal["primary_paper", "patent_document", "patent_example", "secondary_review", "database", "user_process_record", "analogy"]
    title: str
    url: HttpUrl | None = None
    locator: str
    publicationId: str | None = None
    preciseLocators: list[EvidenceLocator] = Field(default_factory=list)
    supportedFacts: list[str]
    unsupportedClaims: list[str]
    accessLevel: Literal["full_text", "example_text", "abstract", "snippet", "user_provided"]

    @model_validator(mode="after")
    def patent_example_requires_example_text_and_locator(self) -> "SourceRecord":
        if self.sourceType != "patent_example":
            return self
        if self.accessLevel != "example_text":
            raise ValueError("patent_example requires example_text access")
        if not any(item.kind == "example" for item in self.preciseLocators):
            raise ValueError("patent_example requires an example locator")
        return self


class ConditionFieldEvidence(BaseModel):
    field: Literal["solvent", "temperature", "time", "catalyst", "equivalents", "yield", "purity", "workup"]
    value: str
    sourceId: str
    locator: EvidenceLocator


class YieldArithmeticCheck(BaseModel):
    limitingMoles: float = Field(gt=0)
    productMolarMass: float = Field(gt=0)
    isolatedMass: float = Field(ge=0)
    reportedYieldPercent: float = Field(ge=0, le=100)
    computedYieldPercent: float = Field(ge=0, le=100)
    absoluteDifferencePercentagePoints: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def verify_arithmetic(self) -> "YieldArithmeticCheck":
        computed = self.isolatedMass / (
            self.limitingMoles * self.productMolarMass
        ) * 100
        difference = abs(computed - self.reportedYieldPercent)
        if abs(self.computedYieldPercent - computed) > 0.15:
            raise ValueError("computedYieldPercent does not match mass balance")
        if abs(self.absoluteDifferencePercentagePoints - difference) > 0.15:
            raise ValueError("yield difference does not match computed yield")
        return self


class LiteratureOutcomeAssessment(BaseModel):
    reportedYield: str | None = None
    reportedPurity: str | None = None
    reportedConversionPercent: float | None = Field(default=None, ge=0, le=100)
    reportedSelectivityPercent: float | None = Field(default=None, ge=0, le=100)
    reportedIsolatedYieldPercent: float | None = Field(default=None, ge=0, le=100)
    yieldBasis: Literal["isolated", "assay", "conversion", "unclear", "not_reported"] = "not_reported"
    arithmeticConsistency: Literal["consistent", "conflict", "not_checkable"] = "not_checkable"
    arithmeticCheck: YieldArithmeticCheck | None = None
    note: str

    @model_validator(mode="after")
    def consistent_claim_requires_check(self) -> "LiteratureOutcomeAssessment":
        if self.arithmeticConsistency == "consistent" and self.arithmeticCheck is None:
            raise ValueError("consistent arithmetic requires arithmeticCheck")
        if (
            self.arithmeticCheck is not None
            and self.reportedIsolatedYieldPercent is not None
            and abs(
                self.arithmeticCheck.reportedYieldPercent
                - self.reportedIsolatedYieldPercent
            ) > 0.15
        ):
            raise ValueError("isolated yield does not match arithmetic check")
        return self


class PurificationAssessment(BaseModel):
    operations: list[str] = Field(default_factory=list)
    separationBasis: list[str] = Field(default_factory=list)
    impurityRisks: list[str] = Field(default_factory=list)
    evidenceStatus: Literal["direct", "partial", "mechanistic_hypothesis", "unknown"]
    note: str


class CandidateCondition(BaseModel):
    candidateId: str
    name: str | None = None
    scenarioType: Literal["distinct_route", "condition_variant"] = "condition_variant"
    sourceIds: list[str] = Field(min_length=1)
    solvent: str | None = None
    temperature: str | None = None
    time: str | None = None
    catalyst: str | None = None
    equivalents: str | None = None
    yieldValue: str | None = None
    purity: str | None = None
    workup: list[str] = Field(default_factory=list)
    fieldEvidence: list[ConditionFieldEvidence] = Field(default_factory=list)
    outcomeAssessment: LiteratureOutcomeAssessment | None = None
    purificationAssessment: PurificationAssessment | None = None
    simulationReadiness: Literal[
        "configured", "eligible_for_configuration", "insufficient_evidence"
    ] = "insufficient_evidence"
    simulationLimitations: list[str] = Field(default_factory=list)
    comparisonNote: str | None = None


class EvidenceConflict(BaseModel):
    field: str
    sourceIds: list[str] = Field(min_length=2)
    values: list[str] = Field(min_length=2)
    resolution: str | None = None


class EvidenceGap(BaseModel):
    topic: str
    consequence: str
    recommendedSearch: str


class ResearchSynthesis(BaseModel):
    sources: list[SourceRecord]
    candidates: list[CandidateCondition]
    conflicts: list[EvidenceConflict]
    gaps: list[EvidenceGap]
    selectedCandidateId: str | None = None
    selectionStatus: Literal["selected", "needs_user_choice", "not_comparable"] = "not_comparable"
    comparisonBasis: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def selected_candidate_must_exist_and_be_configured(self) -> "ResearchSynthesis":
        if self.selectedCandidateId is None:
            if self.selectionStatus == "selected":
                raise ValueError("selected status requires selectedCandidateId")
            return self
        selected = next(
            (
                item
                for item in self.candidates
                if item.candidateId == self.selectedCandidateId
            ),
            None,
        )
        if selected is None:
            raise ValueError("selectedCandidateId must reference a candidate")
        if (
            "selectionStatus" in self.model_fields_set
            and self.selectionStatus != "selected"
        ):
            raise ValueError("selectedCandidateId requires selected status")
        if (
            "simulationReadiness" in selected.model_fields_set
            and selected.simulationReadiness != "configured"
        ):
            raise ValueError("selected candidate must be configured for simulation")
        return self
