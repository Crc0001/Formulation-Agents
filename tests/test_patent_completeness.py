import json
from pathlib import Path
from types import SimpleNamespace as N
from virtual_reactor_api.patent_completeness import audit_patents,audit_gaps
from virtual_reactor_api.patent_reader import prioritized_patent_table_pages
from virtual_reactor_api.capsule_models import RetrievedFormula,ResearchReport
from virtual_reactor_api.capsule_research import validate_report

E=json.loads((Path(__file__).parent/'fixtures/patent-examples.json').read_text(encoding='utf-8'))
def formula(title,sid,amount=None):
 return RetrievedFormula(title=title,product='诺氟沙星胶囊',dosage_form='capsule',source_role='patent_example',source_ids=[sid],locator='原始实施例',components=[{'name':'诺氟沙星','compartment':'fill','amount_mg':amount}],applicability='测试来源核对，不是投料')

def test_detects_omitted_controls_in_actual_pdf_text():
 r=N(formulations=[formula('CN112336701A 实施例1胶囊',E[0]['id'],100),formula('CN112336701A 实施例2胶囊',E[0]['id'],100)],processes=[])
 rows=audit_patents(r,E)
 assert {x['example'] for x in rows}=={'实施例1','实施例2','实施例3','对照例1','对照例2'}
 assert {x['example'] for x in rows if x['status']=='missing'}=={'实施例3','对照例1','对照例2'}
 assert len(audit_gaps(rows))==3

def test_empty_extracted_table_is_unresolved_not_absent():
 report=ResearchReport(summary='待核',findings=[],gaps=[],formulations=[formula('CN110960501B 实施例1胶囊',E[1]['id'])])
 checked,issues=validate_report(report,E)
 first=next(x for x in checked.patent_audit if x.example=='实施例1')
 assert first.status=='quantity_unresolved'
 assert any('不能以程序未读全' in x for x in issues)

def test_same_example_number_in_other_patent_does_not_cover_omission():
 report=N(formulations=[formula('CN112336701A 实施例1胶囊',E[0]['id'],100),formula('CN110960501B 实施例2胶囊',E[1]['id'],98)],processes=[])
 assert next(x for x in audit_patents(report,E) if x['patent']=='CN112336701A' and x['example']=='实施例2')['status']=='missing'

def test_visual_source_amount_basis_and_total_are_preserved():
 f=formula('CN110960501B 实施例1胶囊',E[2]['id'],98)
 assert f.strength_mg is None
 assert f.components[0].amount_mg==98
 assert sum([98,19.6,7,14,1.4])==140
 assert '98 | 70%' in E[2]['text'] and '30～35微米' in E[2]['text']
 assert next(x for x in audit_patents(N(formulations=[f],processes=[]),E) if x['example']=='实施例1')['status']=='recorded'

def test_reading_priority_includes_actual_missing_formula_table():
 data=Path('data/documents/9a093365676495922eb7fd8687cc7f79a4d1e0167c1539223ab8646618d77891').read_bytes()
 pages=prioritized_patent_table_pages(data)
 assert 6 in pages[:3]
