import assert from 'node:assert/strict';
import {mixtureScenario} from '../apps/web/src/mixture-scenario.ts';
const m={changing_material:'S',balancing_material:'L',amount_unit:'parts',changing_before:0,changing_after:40,balancing_before:100,balancing_after:60};
const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-10);
close(mixtureScenario(100,25,m,0).linear,100);
close(mixtureScenario(100,25,m,40).logLinear,25);
const mid=mixtureScenario(100,25,m,20);close(mid.linear,62.5);close(mid.logLinear,50);close(mid.changing+mid.balancing,100);
for(let x=0;x<=40;x+=.5){const r=mixtureScenario(7,7,m,x);close(r.linear,7);close(r.logLinear,7);close(r.changing+r.balancing,100);}
assert.throws(()=>mixtureScenario(100,25,m,41));
assert.equal(mixtureScenario(0,25,m,20).logLinear,null);
console.log('Endpoint reproduction, zero effect, mass balance, geometric midpoint and domain checks passed');
