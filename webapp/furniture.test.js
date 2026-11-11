import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {extent,fitItem,contains,meshBounds,validateLayout,appearance,partsFor} from './static/furniture.js';

const catalog=JSON.parse(readFileSync(new URL('./static/furniture-catalog.json',import.meta.url)));
const bounds={minX:0,minZ:-8,maxX:10,maxZ:0};
const bed={id:'bed1',type:'bed',x:4,z:-4,width:1.8,depth:2,height:1,rotation:90,color:'#91aabd'};

test('rotated hit testing and clamping agree with GLB X/Z axes',()=>{
  const e=extent(bed);assert.ok(Math.abs(e.x-1)<1e-10);assert.ok(Math.abs(e.z-.9)<1e-10);
  assert.equal(contains(bed,4.95,-4),true);assert.equal(contains(bed,4,-3.05),false);
  const moved={...bed,x:20,z:-20};assert.equal(fitItem(moved,bounds),true);
  assert.ok(Math.abs(moved.x-9)<1e-10);assert.ok(Math.abs(moved.z+7.1)<1e-10);
  assert.equal(fitItem({...bed,width:12},bounds),false);
});
test('model bounds map Z-up mesh vertices to the original Y-up GLB frame',()=>{
  const actual=meshBounds([{positions:[0,8,0,10,0,2.8,2,3,-.12]}]);
  for(const key of Object.keys(bounds))assert.ok(Math.abs(actual[key]-bounds[key])<1e-10);
});
test('imports reject unknown types, oversized scenes and non-finite coordinates',()=>{
  const valid={version:1,items:[bed],finishes:{floor:'oak',wall:'ivory'}};
  assert.deepEqual(validateLayout(valid,catalog,bounds).items,[{...bed,variant:'standard',material:'default'}]);
  for(const change of [{x:NaN},{height:Infinity},{width:0},{color:'red'},{type:'script'},{x:10},{id:'../'}]){
    assert.throws(()=>validateLayout({...valid,items:[{...bed,...change}]},catalog,bounds));
  }
  assert.throws(()=>validateLayout({...valid,items:[bed,bed]},catalog,bounds));
  assert.throws(()=>validateLayout({...valid,items:Array(201).fill(bed)},catalog,bounds));
  assert.throws(()=>validateLayout({...valid,finishes:{floor:'toString',wall:'ivory'}},catalog,bounds));
});

test('appearance changes retain the rough-layout placement and reject unsupported combinations',()=>{
  const sofa={...bed,type:'sofa'},definition=catalog.find(c=>c.id==='sofa');
  const changed=appearance(sofa,definition,{variant:'chaise-left',material:'leather',color:'#a56e46'});
  for(const key of ['id','type','x','z','width','depth','height','rotation'])assert.equal(changed[key],sofa[key]);
  assert.notDeepEqual(partsFor(definition,changed.variant),definition.parts);
  assert.throws(()=>appearance(sofa,definition,{variant:'oval'}));
  assert.throws(()=>appearance(sofa,definition,{material:'ceramic'}));
  assert.equal(sofa.variant,undefined);
});
