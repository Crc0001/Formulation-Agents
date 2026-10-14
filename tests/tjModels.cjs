const a=require('assert'),fs=require('fs'),m=require('../apps/web/src/tjModels.ts');
const d=JSON.parse(fs.readFileSync('reference/tj0113-models/computed.json'));
for(const k of ['weibull','delay'])for(const arm of ['low','high'])for(let i=0;i<5;i++)a(Math.abs(m.releaseModel(k,d.times[i],d.models[k][arm].params)-d.models[k][arm].fitted[i])<1e-9);
a(Math.abs(m.releaseModel('weibull',10,[10,1])-100*(1-Math.exp(-1)))<1e-12);
a.equal(m.releaseModel('delay',2,[.1,3]),0);
for(const k of ['weibull','delay'])for(const w of [0,.5,1]){const p=m.betweenParams(d.models[k].low.params,d.models[k].high.params,w);let prev=0;for(let t=0;t<=60;t+=.5){const q=m.releaseModel(k,t,p);a(q>=prev-1e-12&&q>=0&&q<=100);prev=q;}}
a.throws(()=>m.betweenParams([1,1],[2,2],1.1));a.throws(()=>m.sourceLinear([5,60],[30,90],75));
console.log('PASS: source cross-check, analytic special cases, bounded monotonic release, domains');
for(const k of ['weibull','delay'])for(const arm of ['low','high']){const r=d.free_models[k][arm];for(let i=0;i<5;i++)a(Math.abs(m.releaseModel(k,d.times[i],r.params)-r.fitted[i])<1e-9);a(r.rmse<d.models[k][arm].rmse);a(r.loo_params.length===5);const p=m.betweenParams(r.params,r.params,.5);a(Math.abs(p[2]-r.params[2])<1e-12);a(Math.abs(m.releaseModel(k,1e6,r.params)-r.params[2])<1e-6);}
console.log('PASS: 20 free-plateau fitted points, plateau limits and interpolation');
