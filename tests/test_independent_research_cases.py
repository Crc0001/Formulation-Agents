import copy
import pytest
from fastapi.testclient import TestClient
from virtual_reactor_api.dual_main import create_app
from virtual_reactor_api.lab_formulations import LabDataset

def dataset(n=2):
 return dict(title='Software test',api_identity='test API',dosage_form='tablet',provenance='synthetic software test only',trials=[dict(trial_id=str(i),batch_id='batch-'+str(i),materials=[dict(name='API',role='api',amount=1,unit='mg/unit'),dict(name='乳糖',role='excipient',amount=10+i%10,unit='mg/unit'),dict(name='微晶纤维素',role='excipient',amount=20-i%10,unit='mg/unit')],process='test process',responses=[dict(metric='hardness',value=40+i,unit='N',method='test')]) for i in range(n)])

def test_duplicate_and_batch_leakage_refused():
 d=dataset();d['trials'][1]['trial_id']='0'
 with pytest.raises(ValueError):LabDataset.model_validate(d)
 d=dataset();d['trials'][1]['batch_id']=d['trials'][0]['batch_id']
 d['trials'][0]['intended_use']='training';d['trials'][1]['intended_use']='validation'
 with pytest.raises(ValueError):LabDataset.model_validate(d)

def test_independent_cases_without_origin_baseline_and_lab_import(tmp_path):
 seen=[]
 async def runner(store,rid,root):
  seen.append(store.run(rid)['message'])
  store.finish(rid,'partial',report={'summary':'test','findings':[],'gaps':[]})
 with TestClient(create_app(tmp_path,runner)) as c:
  pid=c.post('/api/projects',json=dict(name='project',api='target unrelated',market='China',strength='1mg',strength_basis='active')).json()['id'];url=f'/api/projects/{pid}'
  d=dataset(200)
  r=c.post(url+'/lab-formulation-datasets',json=d);assert r.status_code==200,r.text
  saved=r.json();assert len(saved['trials'])==200
  assert c.post(url+'/lab-formulation-datasets',json=d).json()['id']==saved['id']
  assert c.get(url+'/data-sources').json()['sources'][0]['category']=='formulation_lab'
  for mode in ['literature','laboratory']:
   body=dict(title='independent',mode=mode,materials=['乳糖','微晶纤维素'],objective='case research',dataset_id=saved['id'] if mode=='laboratory' else None)
   r=c.post(url+'/research-cases',json=body);assert r.status_code==200,r.text
   case=r.json()
   r=c.post(url+'/interaction/runs',json=dict(question='test',baseline_id=case['id'],research_target=dict(kind='pair',material_ids=['case-material-1','case-material-2'],objective='case research')))
   assert r.status_code==200,r.text
  snap=c.get(url).json();assert not snap['baselines'];assert len(snap['research_cases'])==2
  assert '独立研究对象' in seen[0] and '实验室实际制剂数据包' in seen[-1]
  assert len(c.get(url+'/topic-data').json()['packages'])==2
  bad=copy.deepcopy(d);bad['trials'][0]['materials'][1]['property_record_id']='missing'
  assert c.post(url+'/lab-formulation-datasets',json=bad).status_code==422

