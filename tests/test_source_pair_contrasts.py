import json
import pytest
from virtual_reactor_api.source_pair_contrasts import calculate

def sample():
    quote='A response 20 s; B response 10 s; same process, starch balances lactose.'
    metric=dict(title='example',unit='s',source_id='s',locator='table',conditions='same process',limitations='granule only',points=[dict(label='A',value=20,quote=quote),dict(label='B',value=10,quote=quote)])
    evidence=[dict(id='s',basis='source',access='full_text',text=quote),dict(id='m',basis='hypothesis',fields={'source_metric_json':json.dumps(metric)})]
    request=dict(metric_id='m',pairs=[dict(before_label='A',after_label='B',conditions='same process',comparison_basis='starch balances lactose',basis_source_id='s',basis_quote=quote)])
    return request,evidence

def test_contrast_and_reverse():
    d,e=sample();r=calculate(d,e)
    assert r['pairs'][0]['difference']==-10
    assert r['pairs'][0]['relative_change_percent']==-50
    assert r['target_prediction'] is None
    d['pairs'][0].update(before_label='B',after_label='A')
    assert calculate(d,e)['pairs'][0]['relative_change_percent']==100

def test_zero_reference():
    d,e=sample();m=json.loads(e[1]['fields']['source_metric_json']);m['points'][0]['value']=0
    e[0]['text']=e[0]['text'].replace('20','0')
    for p in m['points']:p['quote']=e[0]['text']
    e[1]['fields']['source_metric_json']=json.dumps(m);d['pairs'][0]['basis_quote']=e[0]['text']
    assert calculate(d,e)['pairs'][0]['relative_change_percent'] is None

@pytest.mark.parametrize('bad',['same','missing','invented','duplicate','wrong_source'])
def test_reject_invalid_pair(bad):
    d,e=sample();p=d['pairs'][0]
    if bad=='same':p['after_label']='A'
    if bad=='missing':p['after_label']='C'
    if bad=='invented':p['basis_quote']='invented comparison conditions'
    if bad=='duplicate':d['pairs'].append(p.copy())
    if bad=='wrong_source':e[0]['basis']='hypothesis'
    with pytest.raises(ValueError):calculate(d,e)

def test_mixture_requires_constant_sum_and_traceable_amounts():
    d,e=sample();p=d['pairs'][0]
    p['mixture']=dict(changing_material='starch',balancing_material='lactose',amount_unit='parts',changing_before=0,changing_after=10,balancing_before=20,balancing_after=10)
    p['comparison_basis']+='; 0 starch initially'
    assert calculate(d,e)['pairs'][0]['mixture']['changing_after']==10
    p['mixture']['balancing_after']=20
    with pytest.raises(ValueError,match='合计量'):calculate(d,e)
    p['mixture'].update(changing_after=7,balancing_after=13)
    with pytest.raises(ValueError,match='用量'):calculate(d,e)
