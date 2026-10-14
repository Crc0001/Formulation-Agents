import pytest
from virtual_reactor_api.focused_screening import ScreeningProgress,audit_progress,ScreeningBudget,ScreeningSynthesisDue
from virtual_reactor_api.origin_delivery import merge_report

def progress(**kw):
 kw.setdefault('mechanism_comparisons',[dict(stage=k,hypothesis='待核对机制解释',evidence_scope='other_drug',paired_comparison='同工艺两臂原始对照',source_ids=['s'],calculation_ids=[],response='原文响应及单位',outcome='supported',interpretation='来源支持局部解释',applicability='仅来源范围',gap='没有逐点数值，当前仅有原文定性对照',next_program_action='补查原始逐点数据') for k in ['wetting','disintegration','dispersion','late_dissolution']])
 kw.setdefault('reasoning_chain',dict(source_ids=['s'],source_comparison='同工艺两臂对照',calculation_ids=[],calculation_gap='原始数据点数未齐',observed_relation='后期降低观察',mechanism_interpretation='解聚与进液竞争',target_similarities='相同辅料配对',target_differences='API与工艺不同',transfer_level='directional_hypothesis',transfer_reason='仅用于方向研究',next_action='补查逐点数据'))
 kw.setdefault('judgment',dict(preferred_hypothesis='后期降低假设',expected_pattern='后期溶出降低',rationale='同条件对照优先于通用机制',supporting_source_ids=['s'],counterevidence='早期可能反向',assumptions='工艺条件保持一致',falsifier='同条件复验方向相反',next_program_action='补查同工艺来源并调用计算'))
 return ScreeningProgress(question='淀粉增加乳糖补差',direction='decrease',direction_reason='来源对照支持后期下降',applicable_range='仅来源区间',reversal_conditions='工艺改变可能反转',next_action='补查同工艺对照',user_action='核对条件后继续研究',evidence_choices=[dict(source_id='s',use='model_data',reason='有固定条件对照',factors='淀粉比例',response='Q30',controls='固定MCC和工艺',locator='表1')],**kw).model_dump()

def test_progress_rejects_search_lead_as_model_data():
 p=progress()
 a=audit_progress(p,[{'id':'s','basis':'search_lead','access':'snippet'}])
 assert a['issues'] and not a['steps'][1]
 a=audit_progress(p,[{'id':'s','basis':'hypothesis','access':'imported'}])
 assert any('原始数据' in x for x in a['issues'])

def test_calculation_must_be_archived_execution():
 p=progress(calculation_evidence_ids=['c'])
 src={'id':'s','basis':'source','access':'full_text'}
 assert audit_progress(p,[src,{'id':'c','basis':'hypothesis','fields':{}}])['issues']
 assert not audit_progress(p,[src,{'id':'c','basis':'hypothesis','fields':{'workflow_id':'w'}}])['issues']

def test_direction_without_adopted_evidence_is_not_certified():
 p=progress();p['evidence_choices']=[]
 assert audit_progress(p,[])['issues']
 p['direction']='unknown'
 assert not audit_progress(p,[])['steps'][1]

def test_checkpoint_survives_final_report_without_field():
 p=progress()
 merged=merge_report({'summary':'old','findings':[],'gaps':[],'screening_progress':p},{'summary':'new','findings':[],'gaps':[]})
 assert merged.screening_progress.question==p['question']

def test_budget_reserves_synthesis_and_origin_unaffected():
 b=ScreeningBudget(30)
 for _ in range(10):b.before_call()
 with pytest.raises(ScreeningSynthesisDue):b.before_call()
 assert b.limit==10

def test_legacy_report_has_no_fake_completion():
 assert audit_progress(None,[])['steps']==[False]*4
 assert merge_report(None,{'summary':'legacy','findings':[],'gaps':[]}).screening_progress is None

def test_budget_enters_synthesis_once_and_preserves_output():
 import asyncio
 from virtual_reactor_api.focused_screening import finish_on_budget
 events=[]
 async def graph():raise ScreeningSynthesisDue()
 async def writer():events.append('writer');return {'summary':'bounded'}
 out=asyncio.run(finish_on_budget(graph,writer,lambda:events.append('synthesis')))
 assert events==['synthesis','writer'] and out['structured_response']['summary']=='bounded'

@pytest.mark.parametrize('error',[TimeoutError(),ValueError('bad input')])
def test_nonbudget_errors_do_not_start_another_research(error):
 import asyncio
 from virtual_reactor_api.focused_screening import finish_on_budget
 async def graph():raise error
 async def writer():raise AssertionError('must not synthesize')
 with pytest.raises(type(error)):asyncio.run(finish_on_budget(graph,writer,lambda:None))

def test_cancellation_does_not_synthesize():
 import asyncio
 from virtual_reactor_api.focused_screening import finish_on_budget
 async def graph():raise asyncio.CancelledError()
 async def writer():raise AssertionError('must not synthesize')
 with pytest.raises(asyncio.CancelledError):asyncio.run(finish_on_budget(graph,writer,lambda:None))


def test_missing_judgment_is_explicit_not_user_choice():
 p=progress(judgment=None)
 assert any('优先判断' in x for x in audit_progress(p,[{'id':'s','basis':'source','access':'full_text'}])['issues'])

def test_source_curve_calculation_recognized():
 p=progress(calculation_evidence_ids=['c'])
 assert not audit_progress(p,[{'id':'s','basis':'source','access':'full_text'},{'id':'c','basis':'hypothesis','fields':{'source_curve_model_json':'{}'}}])['issues']


def test_quantitative_transfer_requires_target_execution():
 p=progress();p['reasoning_chain']['transfer_level']='conditional_quantitative';p['reasoning_chain']['calculation_ids']=['c']
 e=[{'id':'s','basis':'source','access':'full_text'},{'id':'c','basis':'hypothesis','fields':{'source_curve_model_json':'{}'}}]
 assert any('定量迁移' in x for x in audit_progress(p,e)['issues'])

def test_old_report_requires_reasoning_chain():
 p=progress();p['reasoning_chain']=None
 assert any('研究链' in x for x in audit_progress(p,[])['issues'])


def test_deep_budget_preserves_regular_roles():
 regular=ScreeningBudget(56);deep=ScreeningBudget(56,deep=True)
 assert regular.limit==18 and deep.limit==56
 for _ in range(56):deep.before_call()
 with pytest.raises(ScreeningSynthesisDue):deep.before_call()


def test_early_mechanism_does_not_complete_late_research():
 p=progress();p['mechanism_comparisons']=p['mechanism_comparisons'][:2]
 a=audit_progress(p,[{'id':'s','basis':'source','access':'full_text'}])
 assert any('后期溶出' in x for x in a['issues'])
 assert any('分散与有效表面积' in x for x in a['issues'])
 assert not a['steps'][-1]

@pytest.mark.parametrize('field',['source_response_model_json','pair_difference_model_json'])
def test_imported_source_calculations_recognized_without_target_upgrade(field):
 p=progress(calculation_evidence_ids=['c']);p['reasoning_chain']['calculation_ids']=['c'];p['mechanism_comparisons'][0]['calculation_ids']=['c']
 evidence=[{'id':'s','basis':'source','access':'full_text'},{'id':'c','basis':'hypothesis','fields':{field:'{}'}}]
 assert not audit_progress(p,evidence)['issues']
 p['reasoning_chain']['transfer_level']='conditional_quantitative'
 assert any('缺少目标计算' in x for x in audit_progress(p,evidence)['issues'])
