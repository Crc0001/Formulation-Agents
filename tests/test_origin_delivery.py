import asyncio
from virtual_reactor_api.origin_delivery import merge_report, source_chunks, staged_origin_report, CompactExtraction, expand_extraction

def formula(name='例1',amount=10):
    return dict(title=name,product='test',dosage_form='tablet',source_role='patent_example',source_ids=['s1'],locator='例1',applicability='测试',components=[dict(name='API',compartment='fill',amount_mg=amount)])

def report(**values):
    return dict(summary='stage',findings=[],gaps=[],**values)

def evidence(text='实施例1 药物10mg'):
    return [dict(id='s1',text=text,basis='source',access='full_text',title='source',source_url='https://example.org',locator='例1')]

def test_incremental_checkpoint_does_not_erase_or_mutate():
    old=report(formulations=[formula()])
    merged=merge_report(old,report(formulations=[formula('例2')]))
    merged=merge_report(merged,report())
    assert [f.title for f in merged.formulations]==['例1','例2']
    assert len(old['formulations'])==1
    assert len(merge_report(merged,report(formulations=[formula()])).formulations)==2
    assert len(merge_report(merged,report(formulations=[formula(amount=20)])).formulations)==3

def test_chunks_preserve_all_text_and_stable_resume_ids():
    text='实施例1'+('x'*40000)
    chunks=source_chunks(evidence(text))
    assert all(len(c['text'])<=16000 for c in chunks)
    recovered=['']*len(text)
    for c in chunks:recovered[c['offset']:c['offset']+len(c['text'])]=list(c['text'])
    assert ''.join(recovered)==text
    assert [c['chunk_id'] for c in chunks]==[c['chunk_id'] for c in source_chunks(evidence(text))]
    assert source_chunks([{**evidence()[0],'basis':'image_estimate'}])==[]

def test_archived_ocr_extractable_but_not_promoted_to_verified_source():
    parent=evidence()[0]
    child={**parent,'id':'ocr','basis':'image_estimate','locator':'physical page 2',
           'fields':{'source_evidence_id':'s1','ocr_json':'{}'}}
    chunks=source_chunks([parent,child])
    ocr=next(c for c in chunks if c['id']=='ocr')
    assert ocr['basis']=='image_estimate' and ocr['source_evidence_id']=='s1'
    result=expand_extraction(CompactExtraction.model_validate({'formulas':[{'title':'example','locator':'page 2','source_role':'patent_example','components':[{'name':'API','amount':10,'unit':'mg'}]}]}),ocr,{})
    assert result.formulations[0].source_ids==['ocr']
    assert result.formulations[0].source_role=='unknown'
    assert 'OCR待核' in result.formulations[0].applicability

class Model:
    def __init__(self,responses):self.responses=iter(responses);self.calls=[]
    def with_structured_output(self,schema,**kw):self.calls.append(schema.__name__);return self
    async def ainvoke(self,messages):
        value=next(self.responses)
        if isinstance(value,BaseException):raise value
        return value

def test_decision_failure_preserves_extraction_and_resume_skips_done():
    saved=[]
    model=Model([dict(formulas=[dict(title='例1',locator='例1',single_unit=True,components=[dict(name='API',amount=10,unit='mg',compartment='fill')])]),TimeoutError()])
    result=asyncio.run(staged_origin_report(model,evidence(),{},None,saved.append,lambda *a:None,lambda r,e:(r,[])))
    assert len(result.formulations)==1 and result.origin_recommendation is None
    assert len(result.origin_extraction_done)==1 and len(saved)>=2
    model=Model([dict(summary='comparison complete',gaps=[])])
    resumed=asyncio.run(staged_origin_report(model,evidence(),{},result,saved.append,lambda *a:None,lambda r,e:(r,[])))
    assert resumed.summary=='comparison complete' and len(resumed.formulations)==1

def test_cancel_propagates_and_unprocessed_sources_remain_pending():
    model=Model([asyncio.CancelledError()])
    try:asyncio.run(staged_origin_report(model,evidence(),{},None,lambda r:None,lambda *a:None,lambda r,e:(r,[])))
    except asyncio.CancelledError:pass
    else:raise AssertionError('cancellation swallowed')
    model=Model([TimeoutError()])
    result=asyncio.run(staged_origin_report(model,evidence(),{},None,lambda r:None,lambda *a:None,lambda r,e:(r,[])))
    assert not result.origin_extraction_done and any('1段' in g for g in result.gaps)

def test_budget_does_not_drop_remaining_source_manifest():
    ev=evidence('实施例1'+('x'*7000))
    model=Model([dict(formulas=[dict(title='例1',locator='例1',single_unit=True,components=[dict(name='API',amount=10,unit='mg',compartment='fill')])]),dict(summary='partial')])
    result=asyncio.run(staged_origin_report(model,ev,{},None,lambda r:None,lambda *a:None,lambda r,e:(r,[]),max_chunks=1))
    assert len(result.origin_extraction_done)==1 and any('1段' in g for g in result.gaps)

def test_compact_quantities_keep_batch_parts_and_coating_separate():
    value=CompactExtraction.model_validate({'formulas':[
        {'title':'batch','locator':'p1','components':[{'name':'API','amount':100,'unit':'g','compartment':'fill'},{'name':'coat','amount':3,'unit':'parts','compartment':'shell'}]},
        {'title':'single','locator':'p2','single_unit':True,'components':[{'name':'API','amount':0.0005,'unit':'g','compartment':'fill'}]},
        {'title':'known batch','locator':'p3','batch_units':1000,'components':[{'name':'API','amount':0.5,'unit':'g','compartment':'fill'}]}]})
    result=expand_extraction(value,evidence()[0],{'api':'API'})
    assert result.formulations[0].components[0].amount_mg is None
    assert result.formulations[0].components[0].batch_amount==100
    assert result.formulations[0].components[1].percent is None
    assert result.formulations[0].components[1].compartment=='shell'
    assert result.formulations[1].components[0].amount_mg==0.5
    assert result.formulations[2].components[0].amount_mg==0.5

def test_nonverbatim_process_is_not_promoted_to_source_process():
    value=CompactExtraction.model_validate({'formulas':[{'title':'example','locator':'p1','components':[],'process_quote':'invented mixing 5min'}]})
    result=expand_extraction(value,evidence()[0],{'api':'API'})
    assert not result.processes and any('逐字' in gap for gap in result.gaps)

def test_same_pdf_contained_reads_do_not_repeat_but_other_sources_stay():
    full=evidence('header 处方10mg footer')[0]
    subset={**full,'id':'s2','text':'处方10mg','locator':'p2'}
    independent={**subset,'id':'s3','source_url':'https://other.example/paper'}
    chunks=source_chunks([full,subset,independent])
    assert {c['id'] for c in chunks}=={'s1','s3'}


def test_decision_receives_saved_identity_findings_without_raw_source_dump():
    import json
    class CapturingModel(Model):
        async def ainvoke(self, messages):
            self.messages = messages
            return await super().ainvoke(messages)
    previous = report(formulations=[formula()])
    previous['findings'] = [dict(section='reference',title='Saved identity',
        text='Holder and historical label already read; current eligibility unresolved',
        basis='source',source_ids=['s1'],applicability='this version only')]
    model = CapturingModel([dict(summary='comparison',gaps=[])])
    result = asyncio.run(staged_origin_report(model,evidence('RAW_SENTINEL'),{},previous,
        lambda r:None,lambda *a:None,lambda r,e:(r,[]),max_chunks=0))
    payload = json.loads(model.messages[-1]['content'])
    assert payload['findings'][0]['source_ids'] == ['s1']
    assert 'current eligibility unresolved' in payload['findings'][0]['text']
    assert 'RAW_SENTINEL' not in model.messages[-1]['content']
    assert payload['pending_chunks'] == 1
    assert result.findings[0].title == 'Saved identity'


def test_formula_chunks_outrank_dense_directory_and_clinical_doses():
    directory={**evidence()[0],'id':'directory','source_url':'https://example.org/directory',
        'text':'上市目录 '+ '20mg 40mg 80mg 100mg '*80}
    clinical={**evidence()[0],'id':'clinical','source_url':'https://example.org/clinical',
        'text':'DOSAGE AND ADMINISTRATION '+ '20mg 40mg '*60}
    label={**evidence()[0],'id':'label','source_url':'https://example.org/label',
        'text':'6.1 List of excipients: water for injection.'}
    patent={**evidence()[0],'id':'patent','source_url':'https://example.org/patent',
        'text':'Example 1 Formulation. Drug 5mg was dissolved in water.'}
    chunks=source_chunks([directory,clinical,label,patent])
    assert [x['id'] for x in chunks][:2]==['patent','label']
    assert {x['id'] for x in chunks}=={'directory','clinical','label','patent'}
    assert [x['chunk_id'] for x in chunks]==[x['chunk_id'] for x in source_chunks([directory,clinical,label,patent])]

def test_decision_keeps_label_comparison_when_findings_do_not_contain_it():
    import json
    class CapturingModel(Model):
        async def ainvoke(self, messages):
            self.messages=messages
            return await super().ainvoke(messages)
    previous=report(formulations=[formula()],decision_comparison={
        'title':'Stage 1 label','candidates':['Target US version'],
        'rows':[{'metric':'Label excipients','values':['lactose, PEO; current version pending'],
                 'source_ids':['s1']}], 'recommendation':'old preference',
        'reasons':[], 'limitations':[], 'next_steps':[]})
    model=CapturingModel([dict(summary='new comparison',origin_recommendation=None,decision_comparison=None)])
    result=asyncio.run(staged_origin_report(model,evidence(),{},previous,
        lambda r:None,lambda *a:None,lambda r,e:(r,[]),max_chunks=0))
    payload=json.loads(model.messages[-1]['content'])
    row=payload['prior_comparison']['rows'][0]
    assert row['source_ids']==['s1']
    assert row['values']==['lactose, PEO; current version pending']
    assert result.origin_recommendation is None and result.decision_comparison is None

def test_fact_quotes_saved_without_formula_and_fabricated_quote_rejected():
    value=CompactExtraction.model_validate({'facts':[{'title':'identity','quote':'Compound A is the potassium salt.','locator':'definition'},{'title':'wrong','quote':'Commercial formula confirmed.','locator':'none'}]})
    result=expand_extraction(value,evidence('Compound A is the potassium salt.')[0],{})
    assert len(result.findings)==1
    assert result.findings[0].source_ids==['s1']
    assert result.gaps and not result.formulations


def test_recovery_runs_bounded_batches_without_repeating_decision():
    from virtual_reactor_api.origin_delivery import recover_origin_batches
    ev=evidence('Example 1 '+('x'*18000))
    model=Model([{'formulas':[]}]*3)
    result=asyncio.run(recover_origin_batches(model,ev,{},None,lambda r:None,lambda *a:None,lambda r,e:(r,[]),stage=2,max_rounds=3,max_chunks=1))
    assert len(result.origin_extraction_done)==3
    assert 'OriginDecision' not in model.calls
    assert any('分段整理待续' in x for x in result.gaps)


def test_recovery_stops_on_error_and_resume_preserves_successful_chunks():
    from virtual_reactor_api.origin_delivery import recover_origin_batches
    ev=evidence('Example 1 '+('x'*18000))
    model=Model([{'formulas':[]},TimeoutError()])
    events=[]
    result=asyncio.run(recover_origin_batches(model,ev,{},None,lambda r:None,lambda *a:events.append(a),lambda r,e:(r,[]),stage=2,max_chunks=2))
    assert len(result.origin_extraction_done)==1
    assert any(x[0]=='origin_recovery_paused' for x in events)
    resumed=asyncio.run(recover_origin_batches(Model([{'formulas':[]}]),ev,{},result,lambda r:None,lambda *a:None,lambda r,e:(r,[]),stage=2,max_rounds=1,max_chunks=1))
    assert len(resumed.origin_extraction_done)==2

def test_explicit_new_no_recommendation_does_not_resurrect_old_choice():
    old=report(formulations=[formula()],origin_recommendation={'formula_title':'例1','rationale':'old','process':'old'})
    model=Model([dict(summary='not sufficient',origin_recommendation=None,decision_comparison=None)])
    result=asyncio.run(staged_origin_report(model,[],{},old,lambda r:None,lambda *a:None,lambda r,e:(r,[]),max_chunks=0))
    assert result.origin_recommendation is None
    assert old['origin_recommendation']['formula_title']=='例1'


def test_recovery_cancellation_propagates_without_next_round():
    from virtual_reactor_api.origin_delivery import recover_origin_batches
    import pytest
    model=Model([asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(recover_origin_batches(model,evidence(),{},None,lambda r:None,lambda *a:None,lambda r,e:(r,[]),stage=2))
    assert model.calls==['CompactExtraction']


def test_stage_two_no_pending_chunks_returns_typed_report_without_mutation():
    import json
    from virtual_reactor_api.origin_delivery import recover_origin_batches
    from virtual_reactor_api.capsule_models import ResearchReport
    from virtual_reactor_api.capsule_research import validate_report
    previous=dict(summary='saved stage',findings=[],gaps=['science pending'])
    original=json.dumps(previous,sort_keys=True)
    model=Model([])
    result=asyncio.run(recover_origin_batches(model,[],{},previous,lambda r:None,lambda *a:None,lambda r,e:(r,[]),stage=2))
    assert isinstance(result,ResearchReport) and not model.calls
    validated,issues=validate_report(result,[],origin_phase=2)
    assert validated.summary=='saved stage' and 'science pending' in validated.gaps
    assert json.dumps(previous,sort_keys=True)==original


def test_phase_three_defers_decision_until_all_chunks_read():
    from virtual_reactor_api.origin_delivery import recover_origin_batches
    ev=evidence('Example 1 '+('x'*18000))
    model=Model([{'formulas':[]}])
    events=[]
    result=asyncio.run(recover_origin_batches(model,ev,{},None,lambda r:None,lambda *a:events.append(a),lambda r,e:(r,[]),stage=3,max_rounds=1,max_chunks=1))
    assert model.calls==['CompactExtraction']
    assert any(e[0]=='origin_decision_deferred' for e in events)
    assert len(result.origin_extraction_done)==1
