export type MassItem={id:string;name:string;role:string;amount_mg:number};
export function massTotal(items:MassItem[]){return items.reduce((s,x)=>s+Number(x.amount_mg),0)}
export function balancePlan<T extends MassItem>(base:T[],items:T[],id:string){
 if([...base,...items].some(x=>!Number.isFinite(x.amount_mg)||x.amount_mg<=0))throw Error('请先填齐有效的正数用量');
 const target=items.find(x=>x.id===id);
 if(!target||target.role!=='excipient')throw Error('请选择现有辅料补差，原料药和胶囊壳不能补差');
 const delta=massTotal(base)-massTotal(items),amount=Number((target.amount_mg+delta).toFixed(9));
 if(amount<=0)throw Error('该辅料不足以扣减差额，请选择其他辅料或允许总量改变');
 return {delta,before:target.amount_mg,after:amount,items:items.map(x=>x.id===id?{...x,amount_mg:amount}:x)};
}
