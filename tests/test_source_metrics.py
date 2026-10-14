import pytest
from virtual_reactor_api.source_metrics import validate_metric

def payload():
 return dict(title='flow',unit='mg/s',source_id='s',locator='Table 1',conditions='same method',limitations='pure powder only',points=[dict(label='A',value=22.9,quote='Sample A flow 22.9 mg/s'),dict(label='B',value=64.2,quote='Sample B flow 64.2 mg/s')])
def evidence():return [dict(id='s',basis='source',access='full_text',text='Sample A flow 22.9 mg/s; Sample B flow 64.2 mg/s')]
def test_valid_original_points_preserved():
 assert [x['value'] for x in validate_metric(payload(),evidence())['points']]==[22.9,64.2]
@pytest.mark.parametrize('bad',['number','quote','source','snippet','duplicate','nan'])
def test_invalid_graph_not_accepted(bad):
 p=payload();e=evidence()
 if bad=='number':p['points'][0]['value']=99
 if bad=='quote':p['points'][0]['quote']='Invented Sample A 22.9 mg/s'
 if bad=='source':p['source_id']='elsewhere'
 if bad=='snippet':e[0]['access']='snippet'
 if bad=='duplicate':p['points'][1]['label']='A'
 if bad=='nan':p['points'][0]['value']=float('nan')
 with pytest.raises(ValueError):validate_metric(p,e)

@pytest.mark.parametrize('text,expected',[
 ('value 0.76.',[.76]),('values 0.81, 0.79 to 0.76.',[.81,.79,.76]),
 ('value −0.76.',[-.76]),('value 1.2e-3.',[.0012]),('value .76.',[.76]),
 ('version1.2.3 and 1.2.3',[]),('number 1,000 and 0,76',[]),('a0.76 and 0.76mg',[]),
])
def test_numeric_tokens_preserve_boundaries(text,expected):
 from virtual_reactor_api.source_metrics import source_numbers
 assert source_numbers(text)==expected

def test_solid_fraction_sentence_restored_and_derived():
 quote='Solid fractions at 0, 5% and 20% starch were 0.81, 0.79 to 0.76.'
 p=dict(title='ribbon',unit='1',quantity='ribbon_solid_fraction',source_id='s',locator='text',conditions='author summary',limitations='not target',points=[dict(label=str(x),value=y,quote=quote) for x,y in zip([0,5,20],[.81,.79,.76])])
 e=evidence();e[0]['text']=quote
 result=validate_metric(p,e)['structure_calculation']
 assert result['porosity']==pytest.approx([.19,.21,.24])
 assert result['porosity_change_pp']==pytest.approx([0,2,5])
 assert result['geometry_factor_ratio'][0]==1
 assert result['geometry_factor_ratio'][2]==pytest.approx((.24**3/.76**2)/(.19**3/.81**2))
 p['points'][2]['value']=.7
 with pytest.raises(ValueError):validate_metric(p,e)
