import asyncio,copy
import pytest
from virtual_reactor_api.research_reuse import reuse_bundle,finish_missing_output

def variant():
 return dict(id='old',baseline_id='base',ingredients=[dict(id='s',name='淀粉',amount_mg=17,brand='A')],method='water',process='fixed',api_particle='unknown',mass_basis='mg',total_policy='fixed')

def test_identical_conditions_reuse_without_mutation():
 old=variant();new={**old,'id':'new','title':'renamed'};record={'id':'r','variant_id':'old'}
 b=reuse_bundle(new,[old,new],[record],[])
 assert b['pair_studies']==[record] and record['variant_id']=='old'

@pytest.mark.parametrize('field,value',[('baseline_id','other'),('method','acid'),('process','wet'),('api_particle','5um'),('mass_basis','g'),('total_policy','variable')])
def test_changed_conditions_do_not_reuse(field,value):
 old=variant();new={**old,'id':'new',field:value}
 assert reuse_bundle(new,[old,new],[{'variant_id':'old'}],[])['pair_studies']==[]

def test_changed_brand_or_dose_rejected():
 for field,value in [('brand','B'),('amount_mg',8.5)]:
  old=variant();new=copy.deepcopy(old);new['id']='new';new['ingredients'][0][field]=value
  assert not reuse_bundle(new,[old,new],[{'variant_id':'old'}],[])['pair_studies']

def test_missing_output_synthesizes_once():
 calls=[]
 async def synth():calls.append(1);return {'summary':'recovered'}
 out,recovered=asyncio.run(finish_missing_output(None,synth,lambda:None,lambda *a:None))
 assert recovered and len(calls)==1 and out['summary']=='recovered'

def test_failed_synthesis_retains_checkpoint():
 async def synth():raise TimeoutError()
 out,recovered=asyncio.run(finish_missing_output(None,synth,lambda:{'summary':'saved','findings':[],'gaps':[]},lambda *a:None))
 assert recovered and out.summary=='saved' and '最终结构化' in out.gaps[-1]

def test_cancellation_propagates():
 async def synth():raise asyncio.CancelledError()
 with pytest.raises(asyncio.CancelledError):asyncio.run(finish_missing_output(None,synth,lambda:{},lambda *a:None))
