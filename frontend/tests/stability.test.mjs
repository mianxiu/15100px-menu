import test from 'node:test';
import assert from 'node:assert/strict';
import {stabilityIssue} from '../src/stability.mjs';

test('old English failure gains Chinese context without hiding raw evidence',()=>{
  const issue=stabilityIssue({phase:'failed',stage:'fixture',error:'An owned test document is still retained'});
  assert.equal(issue.message,'自动测试未完成');
  assert.equal(issue.stage,'创建隔离临时文档');
  assert.equal(issue.detail,'An owned test document is still retained');
});
test('cleanup failure wins display, original test failure stays in exported model',()=>{
  const model={phase:'stopped',problem:{message:'old',detail:'old raw'},cleanup_problem:{message:'new',detail:'new raw',stage:'cleanup'}};
  assert.equal(stabilityIssue(model).message,'new');assert.equal(model.problem.detail,'old raw');
  assert.equal(stabilityIssue({...model,phase:'cleaned'}),null);assert.equal(stabilityIssue({}),null);
});
