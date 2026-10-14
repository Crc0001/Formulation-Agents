"""Portable, standard-library calculator. No network, database or formula writes."""
import argparse
import json
import math
from pathlib import Path

MODEL_ID = 'linear-powder-yield-v1'

def number(value, name, lower=0, upper=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{name}: finite number required')
    if value < lower or (upper is not None and value > upper):
        raise ValueError(f'{name}: outside allowed range')
    return value

def solve(data):
    if data.get('schema_version') != 1 or data.get('model_id') != MODEL_ID:
        raise ValueError('Unsupported schema_version or model_id')
    if data.get('units') != {'stress': 'kPa', 'angle': 'deg'}:
        raise ValueError('Explicit kPa and deg units required; convert before calling')
    conditions = data['conditions']
    pre = number(conditions['pre_shear_kPa'], 'pre_shear_kPa')
    domain = conditions['normal_stress_domain_kPa']
    if len(domain) != 2: raise ValueError('Two domain endpoints required')
    low, high = [number(x, 'domain') for x in domain]
    if not low < high < pre: raise ValueError('Require 0 <= domain low < high < pre-shear')
    if not str(conditions.get('domain_basis', '')).strip(): raise ValueError('Domain basis required')
    stress = data['normal_stress_kPa']
    if not isinstance(stress, list) or not 1 <= len(stress) <= 1000: raise ValueError('1–1000 coordinates required')
    for s in stress: number(s, 'normal_stress_kPa', low, high)
    if any(b <= a for a,b in zip(stress, stress[1:])): raise ValueError('Coordinates must increase')
    arms = data['arms']
    if not isinstance(arms, list) or len(arms) != 2: raise ValueError('Exactly two explicit arms required')
    curves=[]; slopes=[]
    for arm in arms:
        for key in ('id','material','state','parameter_kind'):
            if not isinstance(arm.get(key),str) or not arm[key].strip(): raise ValueError(f'{key} required')
        if arm['parameter_kind'] not in ('author_fitted_parameters','target_fitted_parameters','explicit_scenario'):
            raise ValueError('Unsupported parameter_kind; do not label fitted parameters raw measurements')
        source=arm['provenance']
        if not source.get('url','').startswith(('https://','http://')) or not source.get('locator'):
            raise ValueError('Parameter URL and locator required')
        c=number(arm['C_kPa'],'C_kPa')
        phi=number(arm['phi_deg'],'phi_deg',0,89.9)
        slope=math.tan(math.radians(phi)); slopes.append(slope)
        curves.append([c+s*slope for s in stress])
    if arms[0]['id']==arms[1]['id']: raise ValueError('Distinct arm IDs required')
    delta=[b-a for a,b in zip(*curves)]
    denominator=slopes[1]-slopes[0]
    cross=(arms[0]['C_kPa']-arms[1]['C_kPa'])/denominator if denominator else None
    return {'schema_version':1,'model_id':MODEL_ID,'result_kind':'parameter_reconstruction',
        'equation':'tau_kPa = C_kPa + normal_stress_kPa * tan(phi_deg * pi / 180)',
        'input':data,'normal_stress_kPa':stress,'tau_kPa':dict(zip([a['id'] for a in arms],curves)),
        'delta_kPa':delta,'relative_change_percent':[None if a==0 else 100*d/a for a,d in zip(curves[0],delta)],
        'algebraic_crossing_kPa':cross,'crossing_in_declared_domain':cross is not None and low<=cross<=high,
        'validation':{'numerical_execution':True,'independent_scientific_validation':False},
        'target_dissolution_prediction':None,
        'limitations':['Parameter reconstruction, not raw measured shear points.',
          'Declared domain and source provenance require human or agent verification; this calculator does not verify papers.',
          'No uncertainty interval: joint parameter covariance is not supplied.',
          'Algebraic crossing is not a verified process threshold.',
          'No mapping from particle size or excipient name to C/phi; no automatic mixture or dissolution transfer.']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.input.resolve()==args.output.resolve(): parser.error('Output must not overwrite input')
    if args.output.exists(): parser.error('Output exists; choose a new output path')
    try:
        result=solve(json.loads(args.input.read_text(encoding='utf-8-sig')))
    except (ValueError,KeyError,TypeError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'model_id':MODEL_ID,'output':str(args.output),'result_kind':result['result_kind']}))

if __name__=='__main__': main()
