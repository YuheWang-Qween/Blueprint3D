import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {readFileSync} from 'node:fs';
import {InteriorNavigation} from './interior-navigation.js';
import {createFurniture} from './furniture-renderer.js';
const catalog=JSON.parse(readFileSync(new URL('./static/furniture-catalog.json',import.meta.url)));

function room(){
  const scene=new THREE.Scene(),model=new THREE.Group(),furniture=new THREE.Group();scene.add(model,furniture);
  const add=(name,size,position)=>{
    const mesh=new THREE.Mesh(new THREE.BoxGeometry(...size),new THREE.MeshStandardMaterial({side:THREE.DoubleSide}));
    mesh.name=name;mesh.position.set(...position);model.add(mesh);
  };
  add('floor_slab',[8,.12,6],[0,-.06,0]);add('wall_divider',[.2,2.8,6],[0,1.4,0]);
  const camera=new THREE.PerspectiveCamera(38,1,.01,300);camera.position.set(10,12,15);
  const viewer={scene,model,furniture,camera,cutEnabled:true,controls:{enabled:true,target:new THREE.Vector3(),update(){}},render(){},cut(value){this.cutEnabled=value;}};
  scene.updateMatrixWorld(true);return viewer;
}
test('indoor camera avoids walls and floor edges, then restores the prior orbit view',()=>{
  const v=room(),nav=new InteriorNavigation(v),position=v.camera.position.clone();
  assert.equal(nav.enter(),true);assert.equal(v.controls.enabled,false);assert.equal(v.cutEnabled,false);
  assert.equal(nav.clear(new THREE.Vector3(0,0,0)),false);
  assert.equal(nav.clear(new THREE.Vector3(5,0,0)),false);
  v.camera.position.set(-1,1.55,0);nav.yaw=0;
  for(let i=0;i<100;i++)nav.move(1,0,.05);
  assert.ok(v.camera.position.x<-.2,'cannot walk through the divider');
  for(let i=0;i<150;i++)nav.move(-1,0,.05);
  assert.ok(v.camera.position.x>=-4,'cannot leave the floor');
  nav.exit();assert.deepEqual(v.camera.position.toArray(),position.toArray());assert.equal(v.camera.fov,38);assert.equal(v.cutEnabled,true);
});
test('rendered sofa variants keep their origin and use distinct geometry and PBR materials',()=>{
  const definition=catalog.find(c=>c.id==='sofa');
  const source={id:'sofa',type:'sofa',x:3,z:-4,width:2.4,depth:.9,height:.85,rotation:90,color:'#a56e46'};
  const standard=createFurniture(source,definition),variant=createFurniture({...source,variant:'chaise-left',material:'leather'},definition);
  assert.deepEqual(variant.position.toArray(),[3,0,-4]);assert.ok(Math.abs(variant.rotation.y+Math.PI/2)<1e-9);
  assert.notEqual(standard.children.length,variant.children.length);
  const body=variant.children.find(c=>c.userData.body);assert.equal(body.material.roughness,.32);assert.equal(body.material.color.getHexString(),'a56e46');
  assert.ok(variant.children.every(c=>c.geometry.attributes.uv.count===c.geometry.attributes.position.count));
  assert.equal(Math.max(...body.geometry.attributes.uv.array),3,'leather texture repeats consistently with the export profile');
});
