import asyncio,copy,hashlib,io,json
import pytest
from PIL import Image
from virtual_reactor_api.table_vision import read_table,accepted_table,TableRead
from virtual_reactor_api.source_metrics import validate_metric

class Store:
 def __init__(self,root):
  b=io.BytesIO();Image.new('RGB',(400,400),'white').save(b,format='PNG');data=b.getvalue();sha=hashlib.sha256(data).hexdigest()
  (root/'data/documents').mkdir(parents=True);(root/'data/documents'/sha).write_bytes(data)
  self.es=[dict(id='p',basis='source',access='page_text',fields={'sha256':'a'*64}),dict(id='im',basis='image_estimate',access='imported',title='image',section='comparison',source_url='https://example.org',locator='page 1',fields={'sha256':sha,'source_evidence_id':'p','source_document_sha256':'a'*64})]
 def run(self,rid):return {'project_id':'pid'}
 def rows(self,*args):return self.es
 def add_evidence(self,pid,v,rid):
  e=dict(v.model_dump(),id=str(len(self.es)),run_id=rid);self.es.append(e);return e
 def event(self,*args):pass

class Model:
 def __init__(self,values):self.values=iter(values);self.prompts=[]
 def with_structured_output(self,*a):return self
 async def ainvoke(self,p):self.prompts.append(p);return next(self.values)

def reading(value='88.8±7.0'):
 return dict(readable=True,table_label='Table 3',bbox=[30,30,370,200],issues=[],cells=[dict(row=r,column=c,text=t) for r,row in enumerate([['Sample','Time s mean±SD'],['Example 7',value],['Example 8','55.2±15.1']]) for c,t in enumerate(row)])

def test_blind_agreement_and_source_calculation(tmp_path):
 s=Store(tmp_path);m=Model([reading(),reading()]);o=asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',m))
 assert o['status']=='machine_agreement' and len(m.prompts)==2
 assert '88.8' not in m.prompts[1][0]['content'][0]['text']
 e=s.es[-1];assert accepted_table(e,s.es)
 v=validate_metric(dict(title='test',unit='s',source_id=e['id'],locator='table3',conditions='printed means',limitations='not dissolution',points=[dict(label='7',value=88.8,quote='Example7 | 88.8±7.0'),dict(label='8',value=55.2,quote='Example8 | 55.2±15.1')]),s.es)
 assert '机器复核' in v['limitations']
 assert validate_metric(v,s.es)==v
 cached=asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Model([])));assert cached['cached']
 s.es[0]['fields']['sha256']='b'*64;assert not accepted_table(e,s.es)

def test_disagreement_is_preserved_and_blocked(tmp_path):
 s=Store(tmp_path);o=asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Model([reading(),reading('83.8±7.0'),reading('88.3±7.0')])) )
 assert o['status']=='unresolved' and not accepted_table(s.es[-1],s.es)
 assert len(json.loads(s.es[-1]['fields']['visual_table_json'])['reads'])==3
 assert asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Model([])))['cached']

@pytest.mark.parametrize('mode',['missing','duplicate','unclear','out_of_bounds'])
def test_bad_table_never_accepted(tmp_path,mode):
 s=Store(tmp_path);v=reading()
 if mode=='missing':v['cells'].pop()
 if mode=='duplicate':v['cells'].append(v['cells'][0])
 if mode=='unclear':v['issues']=['blurred decimal']
 if mode=='out_of_bounds':v['bbox']=[0,0,500,600]
 o=asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Model([v,v,v])))
 assert o['status']=='unresolved' and not accepted_table(s.es[-1],s.es)


def test_japanese_printed_time_header():
 from virtual_reactor_api.source_curve_models import dissolution_numbers
 assert dissolution_numbers('5分 | 10分 | 15分 | 120分')==[5,10,15,120]
 assert dissolution_numbers('実施例2 | 15.3% | 36.3%')==[15.3,36.3]


def test_blank_top_left_cell_remains_usable(tmp_path):
 s=Store(tmp_path);r=reading();r['cells'][0]['text']=''
 out=asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Model([r,r])))
 # Real EvidenceInput strips outside whitespace; an empty corner must not invalidate it.
 assert out['status']=='machine_agreement' and accepted_table(s.es[-1],s.es)

def test_printed_curve_adapter_preserves_cells_and_rejects_guessing(tmp_path):
 from virtual_reactor_api.table_vision import compare_table_curves
 s=Store(tmp_path)
 rows=[['','5分','10分','15分','30分','45分','60分'],['A','10%','25%','40%','70%','85%','90%'],['B','12%','30%','50%','80%','90%','95%']]
 r=dict(readable=True,table_label='Table 3',bbox=[30,30,370,200],issues=[],cells=[dict(row=i,column=j,text=x) for i,row in enumerate(rows) for j,x in enumerate(row)])
 o=asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Model([r,r])))
 output=compare_table_curves(s,'pid','r',o['evidence_id'],'A','B','fixed method','source only','unknown repeatability')['result']
 assert output['arms'][0]['observed_points'][0]==[5,10]
 assert output['arms'][1]['observed_points'][-1]==[60,95]
 assert len(output['arms'][0]['observed_points'])==6
 repeat=compare_table_curves(s,'pid','r',o['evidence_id'],'A','B','different wording','same source','same unknown')
 assert repeat['reused'] and repeat['result']['conditions']=='fixed method'
 assert '机器复核' in ' '.join(output['limitations'])
 with pytest.raises(ValueError):compare_table_curves(s,'pid','r',o['evidence_id'],'A','unknown','fixed','source','unknown')
 # Plain OCR alone remains inadmissible.
 with pytest.raises(ValueError):compare_table_curves(s,'pid','r','im','A','B','fixed','source','unknown')


def test_high_resolution_agreement_preserves_first_disagreement(tmp_path):
 s=Store(tmp_path)
 o=asyncio.run(read_table(s,'pid','r',tmp_path,'im','Table 3',Model([reading('83.8±7.0'),reading(),reading()])))
 v=json.loads(s.es[-1]['fields']['visual_table_json'])
 assert o['status']=='machine_agreement' and accepted_table(s.es[-1],s.es)
 assert v['accepted_read_indices']==[1,2] and '83.8' in str(v['reads'][0])
 assert '88.8' in o['text'] and '83.8' not in o['text']
