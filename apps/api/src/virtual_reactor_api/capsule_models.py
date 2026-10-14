"""Capsule research v1; separate from reaction simulation contracts."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Section = Literal['reference', 'dissolution', 'formulation', 'process', 'comparison', 'excipients']

class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)

class ProjectInput(Model):
    name: str = Field(min_length=1)
    api: str = Field(min_length=1)
    market: str = Field(min_length=1)
    strength: str = Field(min_length=1)
    strength_basis: str = Field(min_length=1)
    dosage_form: str = '普通释放硬胶囊'

class Project(ProjectInput):
    schema_version: Literal['1.0'] = '1.0'
    id: str
    created_at: str

class EvidenceInput(Model):
    section: Section
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    basis: Literal['source', 'hypothesis', 'unknown', 'image_estimate', 'measurement', 'search_lead']
    source_url: str = ''
    locator: str = ''
    applicability: str = Field(min_length=1)
    product: str = ''
    strength: str = ''
    market: str = ''
    document_version: str = ''
    access: Literal['snippet', 'full_text', 'page_text', 'imported', 'user'] = 'user'
    fields: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode='after')
    def source_is_traceable(self):
        if self.basis in ('source', 'image_estimate') and (not self.source_url or not self.locator):
            raise ValueError('来源证据须填写原文链接和页码/表图/段落定位')
        if self.source_url and not self.source_url.startswith(('https://', 'http://')):
            raise ValueError('来源链接须使用http或https')
        return self

class Evidence(EvidenceInput):
    id: str
    project_id: str
    run_id: str | None = None
    created_at: str

class TaskInput(Model):
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)
    experiment: str = Field(min_length=1)
    endpoint: str = Field(min_length=1)

class Task(TaskInput):
    id: str
    status: Literal['open', 'in_progress', 'done'] = 'open'
    result: str = ''
    version: int = 1

class TaskUpdate(Model):
    status: Literal['open', 'in_progress', 'done']
    result: str = ''
    version: int

    @model_validator(mode='after')
    def completion(self):
        if self.status == 'done' and not self.result:
            raise ValueError('完成任务需记录结果及依据')
        return self

class Finding(Model):
    section: Section
    title: str
    text: str
    basis: Literal['source', 'hypothesis', 'unknown']
    source_ids: list[str] = Field(default_factory=list)
    applicability: str

class FormulaComponent(Model):
    source_amount: float | None = Field(default=None,ge=0,allow_inf_nan=False)
    source_unit: str = ''
    source_quantity_basis: str = ''
    batch_amount: float | None = Field(default=None,ge=0)
    batch_mass_unit: Literal['mg','g','kg'] | None = None
    name: str = Field(min_length=1)
    compartment: Literal['fill','shell','unknown']
    amount_mg: float | None = Field(default=None,ge=0)
    percent: float | None = Field(default=None,ge=0,le=100)
    grade: str = ''
    amount_basis: Literal['salt','active_moiety','excipient','unknown'] = 'unknown'
    locator: str = ''

class RetrievedFormula(Model):
    batch_units: int | None = Field(default=None,gt=0,strict=True)
    title: str
    product: str
    manufacturer: str = ''
    market: str = ''
    dosage_form: Literal['capsule','tablet','other','unknown']
    strength_mg: float | None = Field(default=None,gt=0)
    strength_basis: Literal['active_moiety','salt','unknown'] = 'unknown'
    source_role: Literal['official_label','manufacturer_document','patent_example','generic_product','secondary','unknown']
    source_ids: list[str]
    locator: str
    components: list[FormulaComponent]
    applicability: str

    @model_validator(mode='after')
    def per_unit_from_batch(self):
        if self.batch_units is not None:
            factors={'mg':1,'g':1000,'kg':1000000}
            for c in self.components:
                if c.batch_amount is None or c.batch_mass_unit is None: continue
                per=c.batch_amount*factors[c.batch_mass_unit]/self.batch_units
                c.amount_mg=per
                note=f'原文批量{self.batch_units}粒/片；{c.batch_amount:g} {c.batch_mass_unit} × {factors[c.batch_mass_unit]} ÷ {self.batch_units} = {per:g} mg/粒（片）'
                if note not in c.locator: c.locator=(c.locator+'；'+note).strip('；')
        return self

class ProcessStep(Model):
    order: int = Field(ge=1)
    operation: Literal['premix','milling','sieving','blending','lubrication','wet_granulation','dry_granulation','drying','filling','polishing','unknown']
    equipment: str = ''
    action_quote: str = Field(min_length=1)
    parameters: str = ''
    locator: str = ''

class RetrievedProcess(Model):
    title: str
    product: str
    scope: str
    source_role: Literal['patent_example','manufacturer_document','regulatory_document','user_process','secondary','unknown']
    source_ids: list[str]
    steps: list[ProcessStep]
    applicability: str

class DissolutionCurve(Model):
    title: str = Field(min_length=1)
    formula_title: str = Field(min_length=1, description='Exact title of a formulation in this report; never bind by URL alone')
    source_ids: list[str] = Field(min_length=1)
    locator: str = Field(min_length=1)
    table_excerpt: str = Field(min_length=1, description='Verbatim original table/text containing paired times and values; no image estimates')
    medium: str = Field(min_length=1)
    method: str = Field(min_length=1, description='Apparatus, volume, rpm, temperature; explicitly mark missing conditions')
    sample: str = Field(min_length=1, description='Product/example, batch and n; unknown explicitly')
    storage: str = Field(min_length=1, description='Initial or storage conditions and duration; unknown explicitly')
    applicability: str = Field(min_length=1)
    time_min: list[float] = Field(min_length=2)
    percent: list[float] = Field(min_length=2)

    @model_validator(mode='after')
    def ordered_points(self):
        if len(self.time_min)!=len(self.percent) or any(t<0 for t in self.time_min) or any(b<=a for a,b in zip(self.time_min,self.time_min[1:])) or any(y<0 for y in self.percent):
            raise ValueError('Curve requires aligned nonnegative points and strictly increasing times')
        return self

class ScreeningCandidate(Model):
    title: str
    disposition: Literal['test_first','reserve','exclude','insufficient']
    formulation: str
    excipient_selection: str
    api_particle_match: str
    process_match: str
    rationale: str
    source_ids: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    verification_experiment: str
    decision_rule: str

class SubstitutionCase(Model):
    title: str
    source_id: str
    locator: str
    source_quote: str
    change: str
    observed_result: str
    comparability: str
    limitation: str

class SubstitutionAssessment(Model):
    actual_change: str
    source_identity: str
    answer: str
    supported: str
    unresolved: str
    next_action: str
    cases: list[SubstitutionCase] = Field(default_factory=list)

class OriginRecommendation(Model):
    formula_title: str
    rationale: str
    process: str
    limitations: list[str] = Field(default_factory=list)

class CatalogFinding(Model):
    name: str
    manufacturer: str = ''
    grade: str = ''
    market: str = ''
    specification: str
    source_ids: list[str] = Field(default_factory=list)
    limitations: str

class DecisionRow(Model):
    metric: str
    values: list[str]
    source_ids: list[str] = Field(default_factory=list)
    note: str = ''

class DecisionComparison(Model):
    title: str
    recommendation: str
    candidates: list[str]
    rows: list[DecisionRow]
    reasons: list[str]
    limitations: list[str]
    next_steps: list[str]

class PatentAuditRow(Model):
    patent: str
    example: str
    evidence_ids: list[str]
    locator: str
    status: Literal['missing','quantity_unresolved','recorded']

from .agent_split import OrganizationReport
from .interaction_agent import InteractionReport
from .model_research import ResearchDesign
from .focused_screening import ScreeningProgress

class ResearchReport(Model):
    origin_extraction_done: list[str] = Field(default_factory=list)
    research_design: ResearchDesign | None = None
    screening_progress: ScreeningProgress | None = None
    excipient_organization: OrganizationReport | None = None
    interaction_research: InteractionReport | None = None
    patent_audit: list[PatentAuditRow] = Field(default_factory=list)
    decision_comparison: DecisionComparison | None = None
    origin_recommendation: OriginRecommendation | None = None
    catalog_findings: list[CatalogFinding] = Field(default_factory=list)
    substitution_assessment: SubstitutionAssessment | None = None
    screening_candidates: list[ScreeningCandidate] = Field(default_factory=list)
    summary: str
    findings: list[Finding]
    gaps: list[str]
    proposed_tasks: list[TaskInput] = Field(default_factory=list)
    dissolution_curves: list[DissolutionCurve] = Field(default_factory=list)
    formulations: list[RetrievedFormula] = Field(default_factory=list)
    processes: list[RetrievedProcess] = Field(default_factory=list)

class CalibrationReference(Model):
    id: str
    version: int
    title: str
    strength_mg: float
    strength_basis: str
    fill_mass_mg: float
    components: list[FormulaComponent]
    shell_components: list[str]
    statements: list[str]
    unknowns: list[str]
    user_corrections: list[dict] = Field(default_factory=list)
    sha256: str
    image_url: str
    source_note: str

class ComparisonRow(Model):
    name: str
    reference_mg: float | None
    retrieved_mg: float | None
    status: Literal['matched','different','amount_unknown','not_found','basis_mismatch','compartment_mismatch']
    reference_grade: str
    retrieved_grade: str
    grade_status: str
    note: str

class FormulaComparison(Model):
    title: str
    source_ids: list[str]
    scope: str
    eligible_for_amount_comparison: bool
    rows: list[ComparisonRow]
    extra_components: list[str]
    matched_names: int
    matched_amounts: int
    interpretation: str

class CalibrationEvaluation(Model):
    id: str
    run_id: str
    reference_version: int
    created_at: str
    blind_context: bool
    formulas: list[FormulaComparison]
    limitations: list[str]
    comparator_version: str = '1.0'

class CalibrationView(Model):
    reference: CalibrationReference
    evaluations: list[CalibrationEvaluation]
    process_plan: dict
    process_benchmark: dict = Field(default_factory=dict)

class RunInput(Model):
    message: str = Field(min_length=1)

class Run(Model):
    id: str
    project_id: str
    message: str
    status: Literal['queued', 'running', 'completed', 'partial', 'failed', 'cancelled', 'interrupted']
    created_at: str
    error: str = ''
    report: ResearchReport | None = None

class Event(Model):
    id: int
    run_id: str
    kind: str
    created_at: str
    payload: dict

class Snapshot(Model):
    project: Project
    evidence: list[Evidence]
    tasks: list[Task]
    runs: list[Run]

SourceChannel = Literal['regulatory', 'anmat', 'japan', 'manufacturer', 'patents', 'literature', 'technical', 'other']

class CoverageItem(Model):
    channel: SourceChannel
    title: str
    objective: str
    searches: list[dict]
    documents: list[dict]
    status: str

class CoverageView(Model):
    schema_version: str = '1.0'
    project_id: str
    items: list[CoverageItem]
    limitation: str = '渠道是检索意图分类；取得正文不等于官方性、适用性或定量处方已核实。没有“检索齐全”自动评分。'

class Contracts(Model):
    project_input: ProjectInput
    snapshot: Snapshot
    evidence_input: EvidenceInput
    task_input: TaskInput
    task_update: TaskUpdate
    run_input: RunInput
    event: Event
    calibration: CalibrationView
    coverage: CoverageView

