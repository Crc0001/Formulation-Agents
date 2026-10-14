import importlib.util
from pathlib import Path
from virtual_reactor_api.origin_completion import execution_detail


def item(status='中断待核'):
    return dict(name='drug',project_id='p',status=status,phases=[dict(phase=2,run_id='r')])


def run(gaps=None):
    return dict(id='r',status='partial',report=dict(summary='saved',gaps=gaps or []))


def test_old_rate_limit_gap_is_not_current_interface_failure():
    r=run(['来源段 old@0 提取未完成（OpenAIRateLimitError）','分段整理待续：20段尚未完成'])
    r['error']='阶段交付未完成：来源段 429abc 提取未完成（OpenAIRateLimitError）'
    d=execution_detail(item(),r)
    assert d['code']=='awaiting_resume' and d['pending_chunks']==20
    assert d['requires_human_verification'] is None


def test_current_timeout_and_rate_limit():
    for name,code in [('TimeoutError','timeout'),('OpenAIRateLimitError','rate_limited')]:
        d=execution_detail(item(),run(),[dict(kind='origin_extract_error',payload={'error_type':name})])
        assert d['code']==code


def test_delivered_is_still_scientifically_unverified():
    d=execution_detail(item('三阶段已交付，待逐项验收'),run(['来源冲突，待核']))
    assert d['code']=='delivered' and d['scientific_status']=='尚未科学核验'


def test_queued_retry_and_no_progress_hold():
    r=run();i=item()
    assert execution_detail(i,r,supervision={'run_id':'r','status':'no_progress'})['code']=='no_progress'
    assert execution_detail(i,r,supervision={'run_id':'old','status':'no_progress'})['code']=='awaiting_resume'
    i.update(status='排队',phases=[],retry_request={'phase':2})
    assert execution_detail(i,None)['phase']==2
    assert execution_detail(i,None)['code']=='queued'


def test_supervisor_progress_only_credits_new_checkpoints():
    spec=importlib.util.spec_from_file_location('resume102',Path('scripts/resume_batch102.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    before={'report':{'origin_extraction_done':['a']}}
    assert m.progressed(before,{'report':{'origin_extraction_done':['a','b']}})
    assert not m.progressed(before,{'report':{'origin_extraction_done':['a'],'summary':'rewritten'}})
    # Historical duplicates do not count as fresh work.
    assert not m.progressed(before,{'report':{'origin_extraction_done':['a','a']}})
