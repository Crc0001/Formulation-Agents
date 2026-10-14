import assert from 'node:assert/strict';
import {stageRun,uniqueOriginCandidates,originRunStage} from '../apps/web/src/origin-stage-view.ts';
const first={id:'one',message:'【原研及处方工艺】【01阶段1】身份',report:{decision_comparison:{rows:[{metric:'说明书辅料组成'}]},formulations:[{title:'日本说明书'}]}};
const third={id:'three',message:'【原研及处方工艺】第三阶段：推荐',report:{origin_recommendation:{formula_title:'候选'},formulations:[{title:'候选'}],decision_comparison:{rows:[{metric:'说明书辅料组成'}]}}};
assert.equal(stageRun([first,third],1).id,'one');
assert.equal(stageRun([first,third,{id:'pending',message:first.message}],1).id,'one');
assert.equal(stageRun([first,third],3).id,'three');
assert.equal(stageRun([first,third],2),undefined);
assert.equal(originRunStage('普通研究，历史第一阶段：'),null);
assert.equal(originRunStage('【原研及处方工艺】【接续：汇总】【01阶段2】'),2);
assert.equal(uniqueOriginCandidates([third,third]).length,1);
assert.equal(uniqueOriginCandidates([third,{...third,report:{...third.report,formulations:[{title:'候选',components:[{amount_mg:1}]}]}}]).length,2);
const s=await (await fetch('http://127.0.0.1:2806/api/projects/db6a655f-75fa-4c7a-a4c9-fccbc62e3c40')).json();
for(const stage of [1,2,3]){const r=stageRun(s.origin.runs,stage);assert.ok(r,`stage ${stage}`);console.log(stage,r.id,r.report.formulations?.length);}
assert.equal(stageRun(s.origin.runs,1).report.formulations.some(f=>f.components?.length===11),true);
console.log('Stage separation, unfinished-run preservation, strict candidate deduplication and live project passed.');
