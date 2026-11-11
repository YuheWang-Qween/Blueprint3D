import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {surfaceStyle,setSurfaceStyle,validateFinishes} from './static/surface-finishes.js';
import {createSurface,finishSurface} from './surface-renderer.js';
import {createFurniture} from './furniture-renderer.js';
const first='floor-0123456789abcdef',second='floor-fedcba9876543210',wall='wall-0123456789abcdef';

test('local finishes affect only one area and bulk application retains the other surface kind',()=>{
  const original=validateFinishes({floor:'oak',wall:'ivory'});
  let finishes=setSurfaceStyle(original,'wall',wall,{material:'wallpaper',color:'#91aabd'});
  finishes=setSurfaceStyle(finishes,'floor',first,{material:'tile',color:'#abb9c1'});
  assert.equal(surfaceStyle(finishes,'floor',first).material,'tile');
  assert.equal(surfaceStyle(finishes,'floor',second).color,'#c8ad82');
  const all=setSurfaceStyle(finishes,'floor',null,{material:'wood',color:'#c8ad82'});
  assert.equal(surfaceStyle(all,'floor',first).material,'wood');assert.ok(all.surfaces[wall]);
  assert.deepEqual(original.surfaces,{});
  assert.throws(()=>validateFinishes({...original,surfaces:{[first]:{material:'leather',color:'#ffffff'}}}));
  assert.throws(()=>validateFinishes({...original,surfaces:{'__proto__/bad':{material:'tile',color:'#ffffff'}}}));
});
test('surface rendering keeps source coordinates and uses the shared texture scale',()=>{
  const part={id:first,kind:'floor',positions:[2,.003,-3,3,.003,-3,2,.003,-4],normal:[0,1,0],indices:[0,1,2],uvs:[2,3,3,3,2,4]};
  const mesh=createSurface(part),finishes=setSurfaceStyle(validateFinishes({floor:'original',wall:'original'}),'floor',first,{material:'tile',color:'#abb9c1'});
  finishSurface(mesh,finishes);
  assert.equal(mesh.material.color.getHexString(),'abb9c1');assert.equal(mesh.material.roughness,.3);
  assert.equal(mesh.geometry.attributes.position.getX(0),2);assert.ok(Math.abs(mesh.geometry.attributes.uv.getY(2)-4*1.666667)<.00001);
});
test('all 20 furniture families have distinct choices with renderable body materials',()=>{
  const catalog=JSON.parse(readFileSync(new URL('./static/furniture-catalog.json',import.meta.url)));
  assert.equal(catalog.length,20);
  for(const definition of catalog){
    assert.ok(definition.variants.length,definition.id);
    for(const variant of definition.variants){
      assert.notDeepEqual(variant.parts,definition.parts,definition.id);
      for(const material of definition.materials){
        const item={...definition,id:'test',x:0,z:0,rotation:0,variant:variant.id,material,color:'#91aabd'};
        const group=createFurniture(item,definition);
        assert.equal(group.children.length,variant.parts.length);assert.ok(group.children.some(c=>c.userData.body));
        assert.ok(group.children.every(c=>c.geometry.attributes.position.array.every(Number.isFinite)));
      }
    }
  }
});
