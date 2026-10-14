"""Offline acceptance checks for the portable calculator, not pharmaceutical validation."""
import copy
import json
import math
from pathlib import Path
from powder_yield import solve

example=json.loads((Path(__file__).resolve().parents[1]/'assets/powder-yield-example.json').read_text(encoding='utf-8'))
r=solve(example)
assert math.isclose(r['tau_kPa']['unsieved'][1],.37312655972007125,abs_tol=1e-12)
assert math.isclose(r['tau_kPa']['sieved'][1],.5211289006642442,abs_tol=1e-12)
assert not r['crossing_in_declared_domain']
# Independent sin/cos evaluation catches degree conversion and transcription errors.
for arm in example['arms']:
    angle=arm['phi_deg']*math.pi/180
    for s,tau in zip(example['normal_stress_kPa'],r['tau_kPa'][arm['id']]):
        assert math.isclose(tau,arm['C_kPa']+s*math.sin(angle)/math.cos(angle),abs_tol=1e-12)
same=copy.deepcopy(example);same['arms'][1].update(C_kPa=same['arms'][0]['C_kPa'],phi_deg=same['arms'][0]['phi_deg'])
assert solve(same)['delta_kPa']==[0,0,0]
zero=copy.deepcopy(example)
for arm in zero['arms']:arm.update(C_kPa=0,phi_deg=0)
assert solve(zero)['relative_change_percent']==[None,None,None]
for mutation in ('units','domain','nan','source','negative'):
    bad=copy.deepcopy(example)
    if mutation=='units':bad['units']['stress']='Pa'
    if mutation=='domain':bad['normal_stress_kPa']=[1.2]
    if mutation=='nan':bad['arms'][0]['C_kPa']=float('nan')
    if mutation=='source':bad['arms'][0]['provenance']['locator']=''
    if mutation=='negative':bad['arms'][0]['C_kPa']=-1
    try:solve(bad)
    except ValueError:pass
    else:raise AssertionError(f'Accepted invalid input: {mutation}')
print('PASS: published example, independent numeric check, zero change, zero baseline, invalid inputs')
