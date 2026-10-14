import copy,math
import pytest
from scipy.integrate import quad
from virtual_reactor_api.mechanistic_chain import solve,UNITS

def fixture():
 base={'id':'b','ingredients':[{'id':'api','name':'API','role':'api','amount_mg':98},{'id':'m','name':'MCC','role':'excipient','amount_mg':19.6}]}
 variant={'id':'v','title':'synthetic test','ingredients':copy.deepcopy(base['ingredients'])}
 values=dict(permeability=1e-16,surface_tension=.072,contact_angle=60,viscosity=.001,porosity=.3,pore_radius=1e-6,path_length=.002,diffusivity=1e-9,solubility=10,api_density=1500,diffusion_layer=50e-6,api_diameter=20e-6,medium_volume=.001,shell_lag=3)
 params={k:dict(value=v,unit=UNITS[k],basis='explicit_hypothesis',source_id='test',locator='synthetic numeric test only',applicability='Not a pharmaceutical prediction') for k,v in values.items()}
 data=dict(baseline_id='b',variant_id='v',mass_basis='synthetic API mass; solubility same basis',assumptions='Synthetic software test only: rigid uniform bed, instant exposure, sink, no swelling or agglomeration',arms=[dict(label='baseline',parameters=copy.deepcopy(params)),dict(label='adjusted',parameters=copy.deepcopy(params))],times_s=[0,3,5,20,60,120,240])
 return data,base,variant

def test_zero_change_mass_conservation_and_limits():
 d,b,v=fixture();r=solve(d,b,v)
 assert r['delta_percent_points']==[0]*7
 for a in r['arms']:
  q=a['dissolved_percent'];assert q==sorted(q) and q[:2]==[0,0] and abs(q[-1]-100)<1e-9
  assert all(0<=x<=100 for x in q)
  assert all(abs(x+y-100)<1e-10 for x,y in zip(q,a['undissolved_percent']))
  assert all(x<=y+1e-8 for x,y in zip(q,a['wet_percent']))

def test_independent_adaptive_quadrature_and_grid():
 d,b,v=fixture();r=solve(d,b,v);a=r['arms'][0];tw=a['wetting_time_s'];td=a['particle_dissolution_time_s']
 for t,q in zip(d['times_s'],a['dissolved_percent']):
  elapsed=max(0,t-3)
  def fun(u):
   age=elapsed-tw*u*u
   return 0 if age<=0 else 1-max(0,1-age/td)**3
  split=[min(1,math.sqrt(elapsed/tw)),min(1,math.sqrt(max(0,elapsed-td)/tw))]
  independent=100*quad(fun,0,1,points=split,epsabs=1e-11)[0]
  assert abs(q-independent)<1e-7
 assert max(abs(x-y) for x,y in zip(a['dissolved_percent'],solve(d,b,v,n=32)['arms'][0]['dissolved_percent']))<1e-8

def test_larger_particle_or_contact_angle_slows_under_fixed_other_inputs():
 d,b,v=fixture();d['arms'][1]['parameters']['api_diameter']['value']*=2
 r=solve(d,b,v);assert all(x<=1e-10 for x in r['delta_percent_points']) and min(r['delta_percent_points'])<-1
 d,b,v=fixture();d['arms'][1]['parameters']['contact_angle']['value']=80
 r=solve(d,b,v);assert r['arms'][1]['wetting_time_s']>r['arms'][0]['wetting_time_s']
 assert all(x<=1e-10 for x in r['delta_percent_points'])

@pytest.mark.parametrize('bad',['missing','unit','non_sink','angle','porosity','nan','negative_time','binding','api_mass'])
def test_reject_invalid_inputs(bad):
 d,b,v=fixture();p=d['arms'][0]['parameters']
 if bad=='missing':del p['permeability']
 if bad=='unit':p['api_diameter']['unit']='um'
 if bad=='non_sink':p['solubility']['value']=.001
 if bad=='angle':p['contact_angle']['value']=90
 if bad=='porosity':p['porosity']['value']=1
 if bad=='nan':p['diffusivity']['value']=float('nan')
 if bad=='negative_time':d['times_s'][0]=-1
 if bad=='binding':d['variant_id']='other'
 if bad=='api_mass':v['ingredients'][0]['amount_mg']=100
 with pytest.raises(ValueError):solve(d,b,v)

def test_calculation_saved_with_frozen_identity_and_provenance(tmp_path):
 from virtual_reactor_api.capsule_store import Store
 from virtual_reactor_api.capsule_models import ProjectInput,EvidenceInput
 from virtual_reactor_api.mechanistic_chain import calculate_and_save
 import json
 store=Store(tmp_path/'test.sqlite3');p=store.create_project(ProjectInput(name='test',api='API',market='test',strength='98mg',strength_basis='test'))
 data,base,variant=fixture()
 e=store.add_evidence(p['id'],EvidenceInput(section='comparison',title='synthetic test only',text='Explicit synthetic assumptions for software validation',basis='hypothesis',access='imported',applicability='Not a target prediction'))
 for arm in data['arms']:
  for parameter in arm['parameters'].values():parameter['source_id']=e['id']
 message='冻结基准：'+json.dumps(base)+'\n变化方案：'+json.dumps(variant)+'\n问题：test'
 run=store.create_run(p['id'],message)
 saved,result=calculate_and_save(store,p['id'],run['id'],data)
 assert saved['basis']=='hypothesis'
 archived=json.loads(saved['fields']['mechanistic_chain_json'])
 assert archived['input']['variant_id']=='v' and archived['variant_snapshot']==variant
 assert archived['arms'][0]['dissolved_percent']==result['arms'][0]['dissolved_percent']
 data['arms'][0]['parameters']['permeability']['basis']='source'
 with pytest.raises(ValueError):calculate_and_save(store,p['id'],run['id'],data)
