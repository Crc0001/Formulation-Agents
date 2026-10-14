export type Mixture = {changing_material:string;balancing_material:string;amount_unit:string;changing_before:number;changing_after:number;balancing_before:number;balancing_after:number};
export function mixtureScenario(before:number,after:number,m:Mixture,share:number){
 const total=m.changing_before+m.balancing_before;
 const x0=100*m.changing_before/total,x1=100*m.changing_after/total;
 if(![before,after,total,x0,x1,share].every(Number.isFinite)||total<=0||x0===x1||Math.abs(total-m.changing_after-m.balancing_after)>1e-7)throw Error('无效的配对组成');
 if(share<Math.min(x0,x1)-1e-8||share>Math.max(x0,x1)+1e-8)throw Error('超出文献端点区间');
 const w=(share-x0)/(x1-x0);
 return {w,total,x0,x1,changing:total*share/100,balancing:total*(1-share/100),linear:(1-w)*before+w*after,logLinear:before>0&&after>0?Math.exp((1-w)*Math.log(before)+w*Math.log(after)):null};
}
