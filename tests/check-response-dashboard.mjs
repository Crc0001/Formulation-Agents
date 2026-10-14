import assert from 'node:assert/strict';
import {responseGroups,responseValue} from '../apps/web/src/response-explorer.ts';
const s=await (await fetch('http://127.0.0.1:2806/api/projects/a752fc77-329d-4155-967b-fccdf2904a44')).json();
const run=s.interaction.runs.find(r=>r.id==='ac50878a-a3dd-4a96-a891-10736d6c68be');
const groups=responseGroups(s.interaction.evidence,run);
const group=groups.find(g=>g[0].reviewedPandaSeries);
assert.equal(group.length,6);
for(const r of group){
 const m=r.models.find(m=>m.degree===r.selected_degree);
 r.observed.forEach((p,i)=>assert.ok(Math.abs(responseValue(r,p[0])-m.fitted[i])<1e-9));
 assert.equal(responseValue(r,31),null);
}
assert.equal(responseGroups(s.interaction.evidence,{report:{}}).length,0);
console.log('Verified six source models against saved fitted values; domain and unrelated-case isolation passed.');
