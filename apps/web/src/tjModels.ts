export type FitKind='weibull'|'delay';
export function releaseModel(kind:FitKind,t:number,p:number[]){
 if(!Number.isFinite(t)||t<0||![2,3].includes(p.length)||!p.every(Number.isFinite)||p[0]<=0||(p.length===3&&p[2]<=0)||(kind==='weibull'?p[1]<=0:p[1]<0))throw Error('非法时间或参数');
 const plateau=p[2]??100;
 return kind==='weibull'?plateau*(-Math.expm1(-Math.pow(t/p[0],p[1]))):plateau*(-Math.expm1(-p[0]*Math.max(t-p[1],0)));
}
export function betweenParams(a:number[],b:number[],w:number){if(!Number.isFinite(w)||w<0||w>1)throw Error('配比越界');return [Math.exp((1-w)*Math.log(a[0])+w*Math.log(b[0])),(1-w)*a[1]+w*b[1],...(a.length===3&&b.length===3?[(1-w)*a[2]+w*b[2]]:[])]}
export function sourceLinear(times:number[],ys:number[],t:number){if(!Number.isFinite(t)||t<times[0]||t>times[times.length-1])throw Error('时间越界');const i=times.findIndex(v=>v>=t);if(i===0)return ys[0];const a=(t-times[i-1])/(times[i]-times[i-1]);return (1-a)*ys[i-1]+a*ys[i]}
