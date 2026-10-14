from virtual_reactor_api.origin_dosage import dosage_profile,adapt_policy
from virtual_reactor_api.origin_stages import stage_policy,origin_message
from virtual_reactor_api.origin_selection import SELECTION_POLICY

def test_injection_does_not_assume_solution():
 p=dosage_profile({'dosage_form':'普乐司兰钠注射液'})
 assert p['parenteral'] and '须核对' in p['kind'] and not p['oral_solid']
 assert p['metric']=='对应剂型质量与性能证据'

def test_special_release_not_forbidden():
 for name in ['冻干注射剂','脂质体注射剂','混悬注射剂','乳状注射剂']:
  p=dosage_profile({'dosage_form':name})
  assert p['kind']==name
  text=stage_policy(3,{'dosage_form':name})
  assert '对应溶出证据' not in text
  assert '不能一律禁止释放研究' in text

def test_tablet_preserves_dissolution():
 text=adapt_policy(SELECTION_POLICY,{'dosage_form':'左氧氟沙星片剂'})
 assert '对应溶出证据' in text

def test_unknown_and_free_request():
 assert not dosage_profile({})['oral_solid']
 assert '对应剂型质量与性能证据' in origin_message('继续整理',{'dosage_form':'注射液'})
