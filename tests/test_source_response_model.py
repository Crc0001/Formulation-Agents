import pytest
import numpy as np
from virtual_reactor_api.source_response_model import solve,calculate_and_save
from virtual_reactor_api.capsule_store import Store
from virtual_reactor_api.capsule_models import EvidenceInput,ProjectInput

def test_linear_units_residuals_and_no_extrapolation():
 r=solve([[1,5],[2,8],[3,11]])
 assert r['linear_slope']==pytest.approx(3)
 assert r['models'][0]['rmse']<1e-12
 assert r['models'][0]['internal_level_holdout_rmse']<1e-12
 assert r['domain']==[1,3] and len(r['models'])==1

def test_quadratic_requires_sufficient_levels():
 r=solve([[x,2+x*x] for x in range(6)])
 assert r['selected_degree']==2 and r['models'][1]['rmse']<1e-12
 with pytest.raises(ValueError):solve([[1,2],[1,3],[2,4]])

def test_quote_validation_and_idempotent_saving(tmp_path):
 s=Store(tmp_path/'t.db');p=s.create_project(ProjectInput(name='test',api='A',strength='1mg',strength_basis='active',market='test'));pid=p['id'];r=s.create_run(pid,'test')
 e=s.add_evidence(pid,EvidenceInput(section='comparison',title='source',text='x=1 y=5; x=2 y=8; x=3 y=11',basis='source',access='page_text',source_url='https://example.org',locator='table',applicability='test'))
 data=dict(title='test response',source_id=e['id'],locator='table',conditions='same method',x_name='amount',x_unit='mg',x_basis='per tablet',y_name='time',y_unit='min',confounders=['hardness varies'],points=[dict(x=x,y=y,x_quote=f'x={x}',y_quote=f'y={y}') for x,y in [(1,5),(2,8),(3,11)]])
 a=calculate_and_save(s,pid,r['id'],data);b=calculate_and_save(s,pid,r['id'],data)
 assert a['evidence_id']==b['evidence_id'] and b['reused'] and a['result']['target_prediction'] is None
 data['points'][0]['y']=6
 with pytest.raises(ValueError):calculate_and_save(s,pid,r['id'],data)
