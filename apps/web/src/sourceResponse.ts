// Source-study coordinates only. Never evaluate a target formulation here.
export function sourceResponse(coefficients:number[],pgs:number,mcc:number){
 if(coefficients.length!==6||![...coefficients,pgs,mcc].every(Number.isFinite)||pgs<5||pgs>15||mcc<10||mcc>60)throw Error('超出西地那非来源设计域');
 const x=(pgs-10)/5,z=(mcc-35)/25;
 return coefficients.reduce((sum,b,i)=>sum+b*[1,x,z,x*z,x*x,z*z][i],0);
}
