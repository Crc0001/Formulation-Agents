import copy
from pathlib import Path
import pytest
from virtual_reactor_api.mcc_pgs import source_relations,fit_response,target_coordinates,register_sources
from virtual_reactor_api.capsule_store import Store
from virtual_reactor_api.capsule_models import ProjectInput
ROOT=Path(__file__).resolve().parents[1]

def test_independent_reconstruction_matches_published_equation_and_confirmation():
 d=source_relations(ROOT);s=d['sildenafil'];m=s['models']['q15']
 assert m['coefficients']==pytest.approx(s['published_q15_coefficients'],abs=.005)
 assert m['confirmation_prediction']==pytest.approx(95.8577947552)
 assert m['rmse']==pytest.approx(.22776897)
 assert m['mixed_derivative']==pytest.approx(-.00414)
 assert [r['delta_q10'] for r in d['vildagliptin']['pairs']]==pytest.approx([-7.79,-.31])
 assert d['tj0113']['delta_q']==[-6,3,2,1,1,1]
 assert d['tj0113']['secant_per_pgs_pp']==[-.6,.3,.2,.1,.1,.1]

def test_no_confirmation_or_holdout_leakage():
 s=source_relations(ROOT)['sildenafil'];before=fit_response(s,'q15');edited=copy.deepcopy(s)
 edited['confirmation']['q15']=1
 assert fit_response(edited,'q15')['coefficients']==before['coefficients']
 edited['q15'][4]=12
 assert fit_response(edited,'q15')['loo_predictions'][4]==before['loo_predictions'][4]
 assert fit_response(edited,'q15')['loo_rmse']>before['loo_rmse']

def test_target_identity_and_source_registration(tmp_path):
 b={'id':'b','ingredients':[{'name':'API','role':'api','amount_mg':98},{'name':'微晶纤维素','amount_mg':19.6},{'name':'预胶化淀粉','amount_mg':14},{'name':'other','amount_mg':8.4}]}
 v={'baseline_id':'b','ingredients':copy.deepcopy(b['ingredients'])}
 v['ingredients'][1]['amount_mg']=4.6;v['ingredients'][2]['amount_mg']=29
 t=target_coordinates(b,v)
 assert t['before']['pgs_pct']==10
 assert t['after']['pgs_pct']==pytest.approx(20.7142857143)
 assert t['target_prediction_available'] is False
 assert target_coordinates(b,{**v,'baseline_id':'other'}) is None
 from virtual_reactor_api.research_workflow import execute_workflow,gate_report
 b['ingredients']=[{**x,'id':str(i)} for i,x in enumerate(b['ingredients'])]
 v['ingredients']=[{**x,'id':str(i)} for i,x in enumerate(v['ingredients'])];v['id']='v'
 w=execute_workflow(ROOT,b,v,[])
 assert w['holdout_checks']==[] and w['mcc_pgs_relations']['sildenafil']['models']['q15']['loo_rmse']>0
 assert w['steps'][2]['status']=='已执行，同研究复验'
 report=gate_report({'summary':'原报告完整保留。第二句话。'},dict(w,id='test'))
 assert report['summary'].endswith('原报告完整保留。第二句话。')
 s=Store(tmp_path/'case.sqlite3');p=s.create_project(ProjectInput(name='test',api='test',market='test',strength='test',strength_basis='test'))
 r=s.create_run(p['id'],'test');ids=register_sources(s,p['id'],r['id'],ROOT)
 assert len(ids)==3 and register_sources(s,p['id'],r['id'],ROOT)==ids
 assert all(e['basis']=='source' and 'models' not in e['text'] for e in s.rows('evidence',p['id']))
