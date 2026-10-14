"""Synthetic table fixture only; no private batch identifiers or measurements."""
from types import SimpleNamespace
from virtual_reactor_api.capsule_dissolution import matched_formulation_rows


def test_exact_row_not_discontinuous_model_quote():
    text='表 1.2-3 合成单元测试表（非实验数据）\n取样时间（分钟）\n5 10 15 20 30\n'
    text+='\n'.join(f'处方{i}（SYNTH-{i:02d}） '+ ' '.join(str(i*5+j) for j in range(5)) for i in range(1,10))
    c=SimpleNamespace(locator='表1.2-3',formula_title='DOE F2（SYNTH-02）',time_min=[5,10,15,20,30],percent=[10,11,12,13,14],sample='处方2；SYNTH-02；合成测试')
    quote=matched_formulation_rows(c,[{'text':text}])
    assert quote and quote in text and 'SYNTH-09' in quote
    c.sample='SYNTH-03'
    assert matched_formulation_rows(c,[{'text':text}]) is None
    c.sample='SYNTH-02';c.time_min=[5,10,15,25,30]
    assert matched_formulation_rows(c,[{'text':text}]) is None
