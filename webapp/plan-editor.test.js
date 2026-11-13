import test from 'node:test';
import assert from 'node:assert/strict';
import {blankPlan,rectangle,appendWalls,eraseWall,metersPerUnit,validateDraft,project,planToWorld} from './static/plan-geometry.js';

test('drawing rulers preserve meters independently of the occupied portion of the canvas',()=>{
  const plan=blankPlan(12,9);plan.walls=rectangle([32,32],[160,128]);
  assert.equal(metersPerUnit(plan,12),1/32);
  assert.equal((160-32)*metersPerUnit(plan,12),4);
  assert.equal(metersPerUnit({...plan,source:'linework'},12),12/128);
  assert.equal(metersPerUnit({...plan,walls:[],source:'linework'},12),1/32);
});
test('rough layout doors use the same scale and origin as the manual GLB',()=>{
  const plan=blankPlan(12,9);plan.walls=rectangle([32,32],[160,128]);plan.doors=[[[64,32],[96,32]]];
  const world=planToWorld(plan,12);
  assert.deepEqual(world.walls[0],[[0,-3],[4,-3]]);
  assert.deepEqual(world.doors[0],[[1,-3],[2,-3]]);
  const imported=planToWorld({...plan,source:'linework'},12);
  assert.deepEqual(imported.walls[0],[[0,-9],[12,-9]]);
});
test('room walls deduplicate and removing a wall also removes its attached doors',()=>{
  const walls=rectangle([32,32],[160,128]),plan={walls,doors:[[[64,32],[96,32]],[[160,64],[160,96]]]};
  assert.equal(appendWalls(walls,[[[160,32],[32,32]]]).length,4);
  eraseWall(plan,0);assert.equal(plan.walls.length,3);assert.deepEqual(plan.doors,[[[160,64],[160,96]]]);
  assert.deepEqual(project([200,10],[[32,32],[160,32]]),[160,32]);
});
test('draft round trip retains drawing and rejects invalid coordinates and dimensions',()=>{
  const draft={version:1,name:'手绘户型',params:{width_m:12,wall_height:2.8,door_height:2.1,wall_thickness:.16},depth_m:9,walls:rectangle([32,32],[160,128]),doors:[]};
  assert.deepEqual(validateDraft(JSON.parse(JSON.stringify(draft))).walls,draft.walls);
  assert.throws(()=>validateDraft({...draft,walls:[[[0,0],[400,0]]]}));
  assert.throws(()=>validateDraft({...draft,params:{...draft.params,width_m:NaN}}));
  assert.throws(()=>validateDraft({...draft,params:{...draft.params,door_height:3}}));
  assert.deepEqual(validateDraft({...draft,walls:[]}).walls,[]);
});
