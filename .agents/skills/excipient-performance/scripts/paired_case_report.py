"""Render explicit research results; never infer an excipient coefficient.
Usage: python paired_case_report.py case.json --output report_directory
"""
import argparse
import hashlib
import html
import json
import math
import textwrap
from pathlib import Path
from urllib.parse import urlsplit

ORIGINS={'original_table','figure_digitized','author_text','target_measurement','explicit_assumption','source_interpolation'}
KINDS={'observed','simulation','baseline','prediction'}
LABELS={'observed':'来源实测/估读','simulation':'模拟','baseline':'目标基线','prediction':'条件预测·需要实验确认'}
ORIGIN_LABELS={'original_table':'原文数值表','figure_digitized':'原图数字化近似读数','author_text':'作者正文数值','target_measurement':'目标实测','explicit_assumption':'明确假设','source_interpolation':'来源数据插值'}
EVALUATIONS={'calibration':'同数据校准','held_out_arm':'留出处方检查','independent_study':'独立研究检查'}


def need(ok,message):
    if not ok:
        raise ValueError(message)


def finite(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)


def validate(case):
    need(case.get('schema_version')==1,'schema_version must be 1')
    need(bool(case.get('title')),'title required')
    endpoint=case['endpoint']
    for key in ('name','x_label','x_unit','y_unit'):
        need(isinstance(endpoint.get(key),str) and bool(endpoint[key]),f'endpoint {key} required')
    bounds=endpoint.get('bounds')
    if bounds is not None:
        need(len(bounds)==2 and all(finite(v) for v in bounds) and bounds[0]<bounds[1],'invalid endpoint bounds')
    warnings=[]; metrics=[]
    gap_report=case.get('report_kind')=='mechanism_gap'
    if gap_report:
        need(case.get('validation',{}).get('status')=='unvalidated','mechanism_gap must be unvalidated')
    for side in ('source','target'):
        panel=case[side]
        for key in ('title','method','changes'):
            need(isinstance(panel.get(key),str) and bool(panel[key]),f'{side} {key} required')
        refs=panel.get('references',[])
        need(side!='source' or bool(refs),'source reference required')
        for ref in refs:
            need(bool(ref.get('label')) and urlsplit(ref.get('url','')).scheme in ('http','https'),'reference must be labelled http(s) URL')
        series=panel.get('series',[])
        gap=panel.get('gap')
        need(bool(series) or (isinstance(gap,str) and bool(gap.strip()) and (side=='target' or gap_report)),f'{side}.series required; missing source data requires report_kind=mechanism_gap and a nonempty source.gap string')
        if gap_report:need(all(s.get('kind') in ('observed','baseline') for s in series),'mechanism_gap can preserve observations/baselines but cannot contain simulations/predictions')
        ids={s.get('id') for s in series}
        need(None not in ids and '' not in ids and len(ids)==len(series),'unique nonempty series IDs required')
        by_id={s['id']:s for s in series}
        for s in series:
            kind=s.get('kind')
            need(kind in KINDS and bool(s.get('label')),'invalid series kind/label')
            need(kind in ({'observed','simulation'} if side=='source' else {'baseline','prediction'}),'series in wrong panel')
            pts=s.get('points',[])
            need(bool(pts),'empty series: use target gap instead')
            need(all(isinstance(p,list) and len(p)==2 and all(finite(v) for v in p) for p in pts),'finite numeric [x,y] pairs required')
            need(all(pts[i][0]<pts[i+1][0] for i in range(len(pts)-1)),'x coordinates must increase strictly')
            if bounds and any(p[1]<bounds[0] or p[1]>bounds[1] for p in pts):
                warnings.append(f'{side}/{s["id"]}有值超出指标参考范围；原值保留，未裁剪。')
            if kind in ('observed','baseline'):
                need(s.get('origin') in ORIGINS,'explicit observed/baseline origin required')
            if kind=='observed':
                need(s['origin'] not in ('explicit_assumption','source_interpolation'),'source observations cannot be assumed or interpolated values')
            if kind=='simulation':
                need(s.get('evaluation') in EVALUATIONS,'simulation evaluation role required')
                observed=by_id.get(s.get('comparison_to'),{})
                need(observed.get('kind')=='observed','simulation must refer to observed series')
                predicted=dict(pts)
                need(all(x in predicted for x,y in observed['points']),'simulation must include each observation x for residual calculation')
                residual=[predicted[x]-y for x,y in observed['points']]
                metrics.append({'series':s['label'],'evaluation':EVALUATIONS[s['evaluation']],
                    'n':len(residual),'rmse':math.sqrt(sum(r*r for r in residual)/len(residual)),
                    'max_abs_error':max(abs(r) for r in residual),'residuals':residual,'unit':endpoint['y_unit']})
            if kind=='prediction':
                need(s.get('classification')=='conditional','prediction must be explicitly conditional in this renderer')
                base=by_id.get(s.get('comparison_to'),{})
                need(base.get('kind')=='baseline','prediction requires identified baseline')
                need(pts[0][0]>=base['points'][0][0] and pts[-1][0]<=base['points'][-1][0],'prediction exceeds declared baseline x domain')
        if side=='source' and not gap_report:
            need(sum(s['kind']=='observed' for s in series)>=2,'source requires at least two identified experimental arms')
    model=case['model']
    need(bool(model.get('id')) and bool(model.get('equation')),'model ID and equation required')
    for p in model.get('parameters',[]):
        need(all(p.get(k) not in (None,'') for k in ('name','value','unit','basis','source')),'every parameter needs value, units, basis and source')
        need(finite(p['value']),'parameter value must be finite numeric')
    predictions=[s for s in case['target'].get('series',[]) if s['kind']=='prediction']
    transfer=case['transfer']
    if predictions:
        need(transfer.get('status')=='conditional' and bool(transfer.get('assumptions')),'conditional transfer assumptions required')
        need(bool(model.get('parameters')),'prediction requires explicit parameter provenance')
    need('uncovered' in transfer,'uncovered effects must be explicitly listed, even if empty')
    validation=case['validation']
    train=set(validation.get('calibration_families',[]));test=set(validation.get('validation_families',[]))
    need(not train.intersection(test),'study families overlap between calibration and validation')
    need(validation.get('status') in ('unvalidated','calibrated','independently_checked'),'invalid validation status')
    independent=validation['status']=='independently_checked' or any(s.get('evaluation')=='independent_study' for s in case['source'].get('series',[]))
    if independent:
        need(bool(test),'independent study check requires validation family IDs')
    return {'metrics':metrics,'warnings':warnings,
            'verification_scope':'结构与声明核查，不证明研究独立性、模型适用性或参数真实性'}


def render(case,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    audit=validate(case)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    frozen=json.dumps(case,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
    audit['input_sha256']=hashlib.sha256(frozen.encode('utf-8')).hexdigest()
    (output/'case.json').write_text(frozen,encoding='utf-8')
    (output/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans']
    plt.rcParams['axes.unicode_minus']=False
    fig,axes=plt.subplots(1,2,figsize=(14,5.5),layout='constrained')
    endpoint=case['endpoint'];colors=['#17658b','#c56820','#458155','#935ea4']
    all_y=[p[1] for side in ('source','target') for s in case[side].get('series',[]) for p in s['points']]
    limits=list(endpoint.get('bounds',[]))+all_y
    lo,hi=(min(limits),max(limits)) if limits else (0,1)
    if lo==hi:lo,hi=lo-1,hi+1
    for ax,side in zip(axes,('source','target')):
        panel=case[side];series=panel.get('series',[])
        roots=[s['id'] for s in series if s['kind'] in ('observed','baseline')]
        for i,s in enumerate(series):
            root=s.get('comparison_to',s['id'])
            color=colors[(roots.index(root) if root in roots else i)%len(colors)]
            if s['kind']=='prediction':color='#c56820'
            xs,ys=zip(*s['points'])
            label=s['label']+' · '+LABELS[s['kind']]
            if s['kind']=='observed':
                ax.scatter(xs,ys,facecolors='white',edgecolors=color,marker=('o','s','^','D')[i%4],s=35,label=label,zorder=3)
            else:
                ax.plot(xs,ys,ls='--' if s['kind']=='prediction' else '-',color=color,lw=2,
                        marker='o' if len(xs)==1 else None,label=label)
        ax.set_title(textwrap.fill(('左：' if side=='source' else '右：')+panel['title'],30))
        if series:
            ax.set_xlabel(endpoint['x_label']+' / '+endpoint['x_unit'])
            ax.set_ylabel(endpoint['name']+' / '+endpoint['y_unit'])
            ax.legend(fontsize=8,loc='best');ax.grid(alpha=.18);ax.margins(x=.03,y=.08)
            ax.set_ylim(lo,hi)
        else:
            ax.axis('off');ax.text(.05,.7,('来源对照数据缺口\n' if side=='source' else '目标预测缺口\n')+textwrap.fill(panel['gap'][:160],28),transform=ax.transAxes,va='top',fontsize=11)
    fig.savefig(output/'comparison.png',dpi=160);fig.savefig(output/'comparison.svg');plt.close(fig)
    esc=lambda v:html.escape(str(v),quote=True)
    def bullets(values):return '<ul>'+''.join('<li>'+esc(v)+'</li>' for v in values)+'</ul>'
    panels=[]
    for side in ('source','target'):
        p=case[side]
        refs=' · '.join('<a href="'+esc(r['url'])+'">'+esc(r['label'])+'</a>' for r in p.get('references',[]))
        origins='；'.join(esc(s['label']+': '+ORIGIN_LABELS[s['origin']]) for s in p.get('series',[]) if 'origin' in s)
        panels.append('<section><h2>'+esc(p['title'])+'</h2><p>'+esc(p['changes'])+'</p><p>'+esc(p['method'])+'</p><p>'+esc(p.get('gap',''))+'</p><small>'+origins+'</small><p>'+refs+'</p></section>')
    metrics=''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in (m['series'],m['evaluation'],m['n'],f"{m['rmse']:.3g}",f"{m['max_abs_error']:.3g}"))+'</tr>' for m in audit['metrics'])
    parameters=''.join('<tr>'+''.join('<td>'+esc(p[k])+'</td>' for k in ('name','value','unit','basis','source'))+'</tr>' for p in case['model'].get('parameters',[]))
    body='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{background:#f2f5f7;color:#203443;font:16px/1.8 'Microsoft YaHei',sans-serif;margin:0}main{max-width:1400px;margin:auto;padding:28px}h1{font-size:30px}h2{font-size:21px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}section,details{background:white;border:1px solid #d9e3e8;border-radius:10px;padding:20px;margin:16px 0}.warning{background:#fff0d8;padding:16px;border-radius:8px}img{width:100%;height:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:8px;border-bottom:1px solid #dce4ea;text-align:left}a{color:#086790}small{color:#577082}summary{cursor:pointer;font-weight:bold}.equation{white-space:pre-wrap;background:#edf5f6;padding:16px}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style><main>'''
    body+='<h1>'+esc(case['title'])+'</h1><div class="grid">'+''.join(panels)+'</div>'
    body+='<div class="warning">目标变化结果为条件预测，需要实验确认。左侧校准、留出检查与独立验证分别标记；数值误差小不等于迁移已获验证。</div>' if any(s['kind']=='prediction' for s in case['target'].get('series',[])) else '<div class="warning">目标预测未完成，右侧保留具体缺口。</div>'
    states=[('来源数据','已取得' if case['source'].get('series') else '待取得'),('来源模拟','已计算' if any(s['kind']=='simulation' for s in case['source'].get('series',[])) else '未计算'),('目标原方基线','已取得（身份见标签）' if any(s['kind']=='baseline' for s in case['target'].get('series',[])) else '待取得'),('调整预测','条件预测，待实验确认' if any(s['kind']=='prediction' for s in case['target'].get('series',[])) else '未建立')]
    body+='<section><h2>各步骤完成情况</h2>'+bullets(k+'：'+v for k,v in states)+'</section>'
    body+='<img src="comparison.svg" alt="来源实测与模拟、目标基线与条件预测双栏对照">'
    for side in ('source','target'):
        for series in case[side].get('series',[]):
            rows=''.join('<tr><td>'+esc(x)+'</td><td>'+esc(y)+'</td></tr>' for x,y in series['points'])
            body+='<details><summary>'+esc(series['label'])+' · 逐点数据</summary><p>'+esc(series.get('note',''))+'</p><table><tr><th>'+esc(endpoint['x_unit'])+'</th><th>'+esc(endpoint['y_unit'])+'</th></tr>'+rows+'</table></details>'
    if not audit['metrics']:body+='<p>尚未执行来源模拟，不生成残差或拟合误差。</p>'
    body+='<section><h2>来源模拟误差（单位：'+esc(endpoint['y_unit'])+'）</h2><table><tr><th>曲线</th><th>评估身份</th><th>点数</th><th>RMSE</th><th>最大绝对偏差</th></tr>'+metrics+'</table><p>'+esc(audit['verification_scope'])+'</p></section>'
    body+='<div class="grid"><section><h2>迁移假设</h2>'+bullets(case['transfer'].get('assumptions',[]))+'</section><section><h2>未覆盖作用</h2>'+bullets(case['transfer']['uncovered'])+'</section></div>'
    body+='<details><summary>模型、参数和依据</summary><p>'+esc(case['model']['id'])+'</p><div class="equation">'+esc(case['model']['equation'])+'</div><table><tr><th>参数</th><th>值</th><th>单位</th><th>依据类型</th><th>定位</th></tr>'+parameters+'</table></details>'
    body+='<details><summary>核查提示与冻结结果</summary>'+bullets(audit['warnings'])+'<a href="case.json">输入与逐点数据</a> · <a href="audit.json">残差与输入签名</a><p>输入SHA256：'+audit['input_sha256']+'</p></details></main></html>'
    (output/'report.html').write_text(body,encoding='utf-8')
    return audit


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case');parser.add_argument('--output',required=True)
    args=parser.parse_args()
    data=json.loads(Path(args.case).read_text(encoding='utf-8-sig'))
    audit=render(data,args.output)
    print(json.dumps({'status':'rendered','metrics':audit['metrics'],'warnings':audit['warnings']},ensure_ascii=False))
