const assert=require('node:assert/strict');
const {balancePlan,massTotal}=require('../apps/web/src/balance.ts');
const base=[{id:'a',name:'API',role:'api',amount_mg:98},{id:'m',name:'MCC',role:'excipient',amount_mg:19.6},{id:'s',name:'Starch',role:'excipient',amount_mg:14},{id:'l',name:'Lubricant',role:'excipient',amount_mg:1.4},{id:'d',name:'Disintegrant',role:'excipient',amount_mg:7}];
const low=base.map(x=>x.id==='m'?{...x,amount_mg:15}:x);
const p=balancePlan(base,low,'s');assert.equal(p.after,18.6);assert.ok(Math.abs(massTotal(p.items)-140)<1e-8);assert.equal(low[2].amount_mg,14);assert.equal(p.items[0].amount_mg,98);
const high=base.map(x=>x.id==='m'?{...x,amount_mg:25}:x);assert.equal(balancePlan(base,high,'s').after,8.6);
assert.throws(()=>balancePlan(base,high,'l'),/不足/);assert.throws(()=>balancePlan(base,low,'a'),/不能补差/);assert.throws(()=>balancePlan(base,low,''),/请选择/);assert.throws(()=>balancePlan(base,base.map(x=>({...x,amount_mg:NaN})),'s'),/正数/);
console.log('Balance checks passed: decrease, increase, API protection, insufficient amount, selection, non-finite inputs and immutability');
