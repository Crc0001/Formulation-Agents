"""Strict data contracts for reaction research and single-pass generation."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from pydantic import Field, HttpUrl, StringConstraints, model_validator

from virtual_reactor_api.contracts import (
    ReactionEquationSpec,
    ReactionSimulationConfig,
    StrictModel,
)
from virtual_reactor_api.scientific.contracts import (
    IdentifiabilityVerdict,
    ParameterBasis,
    ScientificToolReceipt,
    ScientificToolStatus,
)
from virtual_reactor_api.research_synthesis import ResearchSynthesis


NonBlankText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, strict=True),
]
ReactionDescription = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, strict=True),
]
ReactionImageDataUrl = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        strict=True,
        pattern=r"^data:image/(png|jpeg|webp|gif);base64,[A-Za-z0-9+/]+={0,2}$",
    ),
]


class ReactionImageInput(StrictModel):
    """One user-uploaded image passed to the multimodal generator."""

    filename: NonBlankText
    mediaType: Literal["image/png", "image/jpeg", "image/webp", "image/gif"]
    dataUrl: ReactionImageDataUrl


class ReactionGenerationRequest(StrictModel):
    """Natural-language request accepted from a non-AI-native user."""

    description: ReactionDescription
    conversationId: NonBlankText | None = None
    drawnReactionSmiles: NonBlankText | None = None
    images: list[ReactionImageInput] = Field(default_factory=list)

    def prompt_description(self) -> str:
        """Append user-authored chemical structure without changing the original text."""

        sections = [self.description]
        if self.drawnReactionSmiles is not None:
            sections.append(
                "[用户绘制的反应式（Reaction SMILES，化学身份与反应方向优先）]\n"
                + self.drawnReactionSmiles
            )
        if self.images:
            filenames = "、".join(image.filename for image in self.images)
            sections.append(
                "[用户上传的反应相关图片]\n"
                f"文件：{filenames}。请直接分析随请求提供的图片内容；图片识别结果不得覆盖用户绘制的反应式。"
            )
        return "\n\n".join(sections)


class ResearchGateDecision(StrictModel):
    """Auditable decision controlling whether the generator may search."""

    difficulty: Literal["basic", "moderate", "advanced"]
    searchDecision: Literal["skip", "targeted", "required"]
    reasonCodes: Annotated[list[NonBlankText], Field(min_length=1)]
    reason: NonBlankText
    evidenceTargets: list[NonBlankText]
    scholarBudget: Annotated[int, Field(strict=True, ge=0)]
    webBudget: Annotated[int, Field(strict=True, ge=0)]

    @model_validator(mode="after")
    def validate_search_budget(self) -> "ResearchGateDecision":
        if self.searchDecision == "skip":
            if self.scholarBudget != 0 or self.webBudget != 0:
                raise ValueError("skip decision requires zero search budgets")
            if self.evidenceTargets:
                raise ValueError("skip decision cannot declare evidence targets")
        elif self.scholarBudget + self.webBudget == 0:
            raise ValueError("search decision requires a positive search budget")
        return self


class EvidenceItem(StrictModel):
    """A source excerpt tied to exact fields in the candidate configuration."""

    sourceId: NonBlankText
    title: NonBlankText
    url: HttpUrl
    locator: NonBlankText
    excerpt: NonBlankText
    evidenceLevel: Literal["primary", "secondary", "database", "unknown"]
    supportedPaths: Annotated[list[NonBlankText], Field(min_length=1)]

    @model_validator(mode="after")
    def reject_non_evidence_sources(self) -> "EvidenceItem":
        host = (urlparse(str(self.url)).hostname or "").casefold()
        path = urlparse(str(self.url)).path.casefold()
        if (
            host.endswith("wikipedia.org")
            or host.endswith(".invalid")
            or "internal" in path
            or "tool-receipts.local" in host
        ):
            raise ValueError("百科、占位或内部工具 URL 不能作为文献证据")
        return self


class CandidateModelComparison(StrictModel):
    modelId: NonBlankText
    selected: bool
    reason: NonBlankText
    toolCallIds: list[NonBlankText]


class ParameterSourceDeclaration(StrictModel):
    parameterId: NonBlankText
    fieldPath: NonBlankText
    basis: ParameterBasis
    sourceIds: list[NonBlankText]
    toolCallIds: list[NonBlankText]
    uncertainty: NonBlankText


class ScientificRationale(StrictModel):
    selectedModelId: NonBlankText
    candidateComparisons: Annotated[
        list[CandidateModelComparison], Field(min_length=1)
    ]
    parameterSources: list[ParameterSourceDeclaration]
    citedToolCallIds: list[NonBlankText]
    citedSourceIds: list[NonBlankText]
    unresolvedQuestions: list[NonBlankText]

    @model_validator(mode="after")
    def validate_selected_model(self) -> "ScientificRationale":
        selected = [item.modelId for item in self.candidateComparisons if item.selected]
        if selected != [self.selectedModelId]:
            raise ValueError("exactly one comparison must select selectedModelId")
        return self


class ScientificFinding(StrictModel):
    status: ScientificToolStatus
    subjectId: NonBlankText
    summary: NonBlankText
    toolCallId: NonBlankText


class CandidateModelAssessment(StrictModel):
    modelId: NonBlankText
    selected: bool
    reason: NonBlankText
    metrics: dict[str, Any]
    toolCallIds: list[NonBlankText]


class IdentifiabilitySummary(StrictModel):
    status: ScientificToolStatus
    verdict: IdentifiabilityVerdict
    details: NonBlankText
    unresolvedParameterIds: list[NonBlankText]
    toolCallId: NonBlankText | None


class ParameterSourceSummary(ParameterSourceDeclaration):
    supported: bool


class ScientificAnalysisReport(StrictModel):
    reportVersion: Literal["1.0.0"] = "1.0.0"
    workspaceId: NonBlankText
    selectedModelId: NonBlankText
    identitySummary: list[ScientificFinding]
    unitSummary: list[ScientificFinding]
    balanceSummary: list[ScientificFinding]
    candidateModels: list[CandidateModelAssessment]
    identifiability: IdentifiabilitySummary
    parameterSources: list[ParameterSourceSummary]
    numericalQuality: list[ScientificFinding]
    toolReceipts: list[ScientificToolReceipt]
    warnings: list[NonBlankText]
    applicability: list[NonBlankText]


class AssistantParagraphBlock(StrictModel):
    kind: Literal["paragraph"]
    text: NonBlankText


class AssistantReactionEquationBlock(StrictModel):
    kind: Literal["reaction_equation"]
    equation: ReactionEquationSpec

    @model_validator(mode="after")
    def equation_is_explanatory(self) -> "AssistantReactionEquationBlock":
        if self.equation.role != "explanatory":
            raise ValueError("assistant reaction equation role must be explanatory")
        return self


AssistantContentBlock = Annotated[
    AssistantParagraphBlock | AssistantReactionEquationBlock,
    Field(discriminator="kind"),
]


class AlternativeSimulationConfig(StrictModel):
    """One independently executable configuration for a non-selected literature scenario."""

    candidateId: NonBlankText
    config: ReactionSimulationConfig


class CandidateReactionConfig(StrictModel):
    """A validated simulation configuration plus its scientific audit trail."""

    assistantMessage: NonBlankText
    assistantContent: list[AssistantContentBlock] = Field(default_factory=list)
    config: ReactionSimulationConfig
    evidence: list[EvidenceItem]
    assumptions: list[NonBlankText]
    unansweredQuestions: list[NonBlankText]
    scientificRationale: ScientificRationale | None = None
    researchSynthesis: ResearchSynthesis | None = None
    alternativeConfigs: list[AlternativeSimulationConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_evidence_or_explicit_teaching_assumptions(
        self,
    ) -> "CandidateReactionConfig":
        if not self.evidence and not self.assumptions:
            raise ValueError(
                "candidate without external evidence requires explicit teaching assumptions"
            )
        alternative_ids = [item.candidateId for item in self.alternativeConfigs]
        if len(alternative_ids) != len(set(alternative_ids)):
            raise ValueError("alternative configuration candidateId values must be unique")
        if self.researchSynthesis is None and alternative_ids:
            raise ValueError("alternative configurations require researchSynthesis")
        if self.researchSynthesis is not None:
            candidates = {item.candidateId: item for item in self.researchSynthesis.candidates}
            for candidate_id in alternative_ids:
                if candidate_id == self.researchSynthesis.selectedCandidateId:
                    raise ValueError("selected candidate must use the primary config")
                route = candidates.get(candidate_id)
                if route is None:
                    raise ValueError("alternative configuration must reference a literature candidate")
                if route.simulationReadiness != "configured":
                    raise ValueError("alternative configuration route must be marked configured")
            configured_ids = {
                item.candidateId
                for item in self.researchSynthesis.candidates
                if item.simulationReadiness == "configured"
            }
            supplied_ids = set(alternative_ids)
            if self.researchSynthesis.selectedCandidateId is not None:
                supplied_ids.add(self.researchSynthesis.selectedCandidateId)
            if configured_ids != supplied_ids:
                raise ValueError(
                    "every configured literature route must have exactly one primary or alternative configuration"
                )
        return self


class EligibilityIssue(StrictModel):
    """One deterministic eligibility finding with a machine-locatable path."""

    code: NonBlankText
    fieldPath: NonBlankText
    scope: Literal["simulation", "real_world_operation"]
    severity: Literal["warning", "block"]
    message: NonBlankText


class CandidatePreflightReport(StrictModel):
    """Structured deterministic checks performed before model review."""

    ruleVersion: Literal["1.5.0"] = "1.5.0"
    executable: bool
    singleReactionScopePassed: bool
    materialBalancePassed: bool
    thermalModelStatus: Literal["not_configured", "valid", "invalid"]
    issues: list[EligibilityIssue]


class ClarificationRequest(StrictModel):
    """One blocking question phrased in ordinary experimental language."""

    question: NonBlankText
    reason: NonBlankText


class GeneratorDecision(StrictModel):
    """Structured final response emitted by the Deep Agents graph."""

    kind: Literal["candidate", "clarification"]
    candidate: CandidateReactionConfig | None = None
    clarification: ClarificationRequest | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> "GeneratorDecision":
        if self.kind == "candidate":
            if self.candidate is None or self.clarification is not None:
                raise ValueError(
                    "candidate decision requires only the candidate payload"
                )
        elif self.clarification is None or self.candidate is not None:
            raise ValueError(
                "clarification decision requires only the clarification payload"
            )
        return self


class AgentGenerationResult(StrictModel):
    """One generated candidate or one blocking clarification question."""

    status: Literal["generated", "needs_clarification"]
    candidate: CandidateReactionConfig | None
    diagnostics: CandidatePreflightReport | None
    researchGate: ResearchGateDecision | None = None
    runId: NonBlankText | None = None
    clarificationQuestion: NonBlankText | None
    scientificAnalysis: ScientificAnalysisReport | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "AgentGenerationResult":
        if self.status == "generated":
            if self.candidate is None:
                raise ValueError("generated result requires a candidate")
            if self.clarificationQuestion is not None:
                raise ValueError("generated result cannot contain a clarification")
        else:
            if self.clarificationQuestion is None:
                raise ValueError(
                    "needs_clarification result requires clarificationQuestion"
                )
            if self.candidate is not None or self.diagnostics is not None:
                raise ValueError("needs_clarification cannot contain a candidate")
        return self


GeneratorOutput = CandidateReactionConfig | ClarificationRequest
