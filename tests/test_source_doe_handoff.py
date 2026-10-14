import json,copy,pytest
from virtual_reactor_api.source_doe_handoff import prepare

def record():
 return dict(id='model',baseline_id='b',result=dict(version='image-source-model-v1',input_hash='hash',inputs=[{'source':{'sha256':'same'}}],arms=[dict(label=f'V60 {x}% w/w',source_id=str(x),points=[{'time_min':5,'q_percent':x}],models=[{'leak':True}],selected_model='weibull') for x in [5,7.5,10]]))

def test_partition_and_no_fitted_parameter_leak():
 public,private=prepare(record())
 assert [a['level'] for a in public['training']]==[5,10]
 assert private['heldout']['level']==7.5
 assert 'models' not in json.dumps(public) and 'weibull' not in json.dumps(public)
 assert public['protocol']['execution']=='pending'
 assert prepare(record())[0]['handoff_hash']==public['handoff_hash']
 r=record();r['result']['arms'][1]['points'][0]['q_percent']=99
 assert prepare(r)[0]['handoff_hash']!=public['handoff_hash']

def test_ambiguous_levels_refused():
 r=record();r['result']['arms'][1]['label']='V60 unknown'
 with pytest.raises(ValueError):prepare(r)
 r=record();r['result']['arms'][1]['label']='V60 5% w/w'
 with pytest.raises(ValueError):prepare(r)
