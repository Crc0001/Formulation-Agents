export function pairedCurve(source:{times_min:number[];low:{q:number[]};high:{q:number[]}},pgsMg:number,baselinePgsMg=63){
 if(!Number.isFinite(pgsMg)||pgsMg<63||pgsMg>105||![63,105].includes(baselinePgsMg))throw Error('仅支持来源PGS63–105mg路径，不外推');
 const {times_min:times,low,high}=source;
 if(times.length<2||low.q.length!==times.length||high.q.length!==times.length||!times.every((t,i)=>Number.isFinite(t)&&(!i||t>times[i-1]))||![...low.q,...high.q].every(Number.isFinite))throw Error('来源数据不完整');
 const weight=(pgsMg-63)/42;
 const values=low.q.map((q,i)=>q+weight*(high.q[i]-q));
 const baseline=baselinePgsMg===63?low.q:high.q;
 return {pgsMg,mccMg:290-pgsMg,pgsPct:pgsMg/4.2,mccPct:(290-pgsMg)/4.2,weight,values,baseline,delta:values.map((q,i)=>q-baseline[i]),observed:pgsMg===63||pgsMg===105};
}
