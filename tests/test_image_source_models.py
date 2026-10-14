import pytest
from virtual_reactor_api.image_source_models import fit_arm,comparisons

def arm():
 import math
 return dict(label='test',legend_identity='test',points=[dict(time_min=t,q_percent=90*(1-math.exp(-t/10)),time_error_min=.1,q_error_pp=2) for t in [5,10,15,30,45,60]])

def test_free_platform_and_internal_selection():
 a=fit_arm(arm());assert a['selected_model'] is not None
 assert all(m['parameters']['Qinf_percent']==pytest.approx(90,abs=.1) for m in a['models'])
 assert all(len(m['residuals_pp'])==6 for m in a['models'])

def test_large_nonmonotonic_drop_rejected():
 a=arm()
 for p,q in zip(a['points'],[20,80,99,30,10,5]):p['q_percent']=q
 assert fit_arm(a)['selected_model'] is None

def test_overlap_not_significance():
 a=arm();b=arm();b['label']='b'
 for p in b['points']:p['q_percent']+=1
 assert all(p['direction']=='暂不能区分' for p in comparisons([a,b])[0]['points'])

def test_build_locks_inputs_and_rejects_pixel_mismatch(tmp_path):
 import hashlib,json
 from virtual_reactor_api.chart_digitization import Geometry,convert
 from virtual_reactor_api.image_source_models import build
 raw=b'archived fixture';sha=hashlib.sha256(raw).hexdigest();folder=tmp_path/'data/documents';folder.mkdir(parents=True);(folder/sha).write_bytes(raw)
 g=Geometry.model_validate(dict(readable=True,reason='test',x_unit='min',y_unit='%',x_ticks=[dict(pixel=p,value=v) for p,v in [(10,0),(70,30),(130,60)]],y_ticks=[dict(pixel=p,value=v) for p,v in [(110,0),(60,50),(10,100)]],series=[dict(label='A',legend_identity='circle',points=[dict(x=x,y=y,radius_px=2) for x,y in [(20,80),(30,60),(40,40),(70,25),(100,20),(130,19)]])]))
 d=dict(version='chart-pixels-v1',sha256=sha,width=140,height=120,panel='a',geometry=g.model_dump(),**convert(g,140,120))
 e=[dict(id=i,basis='image_estimate',fields={'digitized_chart_json':json.dumps(d)}) for i in ['a','b']]
 out=build(e,['a','b'],tmp_path);assert out['target_prediction'] is None
 assert build(e,['a','b'],tmp_path)['input_hash']==out['input_hash']
 d['arms'][0]['points'][0]['q_percent']+=1;e[0]['fields']['digitized_chart_json']=json.dumps(d)
 with pytest.raises(ValueError,match='复算'):build(e,['a','b'],tmp_path)
