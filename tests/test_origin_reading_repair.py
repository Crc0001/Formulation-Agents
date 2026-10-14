import threading
import time
from concurrent.futures import ThreadPoolExecutor
from virtual_reactor_api.source_images import _serialized_pdf
from virtual_reactor_api.capsule_research import validate_report
from virtual_reactor_api.capsule_models import ResearchReport

def test_pdf_operations_share_one_lock():
    active=0
    peak=0
    @_serialized_pdf
    def operation(i):
        nonlocal active,peak
        active+=1
        peak=max(peak,active)
        time.sleep(.005)
        active-=1
        return i
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(operation,range(12)))==list(range(12))
    assert peak==1

def test_failed_source_validation_preserves_citation_without_promoting_ocr():
    r=ResearchReport.model_validate(dict(summary='test',findings=[],gaps=[],formulations=[dict(title='example',product='drug',dosage_form='tablet',locator='page 2',applicability='OCR pending',source_role='patent_example',source_ids=['ocr'],components=[dict(name='drug',compartment='fill',amount_mg=10)])]))
    evidence=[dict(id='ocr',basis='image_estimate',access='imported',text='10mg',title='OCR',source_url='https://example.org',locator='page 2',fields={})]
    checked,issues=validate_report(r,evidence)
    assert checked.formulations[0].source_ids==['ocr']
    assert checked.formulations[0].source_role=='unknown'
    assert any('未绑定有效原文' in x for x in issues)
    assert r.formulations[0].source_role=='patent_example'

