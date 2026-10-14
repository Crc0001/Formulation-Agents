import assert from 'node:assert/strict';
import {stageRun,originRunStage} from '../apps/web/src/origin-stage-view.ts';
const old={id:'old',message:'【原研及处方工艺】【01阶段3】',report:{origin_recommendation:{formula_title:'old'}}};
const latest={id:'new',message:old.message,report:{origin_recommendation:null}};
assert.equal(stageRun([old,latest],3).id,'new');
assert.equal(originRunStage('【外部成果导入；原始运行 abc】'+old.message),3);
assert.equal(originRunStage('普通文字'+old.message),null);
assert.equal(stageRun([old,{id:'running',message:old.message}],3).id,'old');
console.log('Imported stage identification, withdrawn recommendation and unfinished run checks passed.');
