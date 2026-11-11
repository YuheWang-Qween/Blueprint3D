import * as THREE from 'three';
import primitives from './static/furniture-geometry.json' with {type:'json'};
import profiles from './static/material-profiles.json' with {type:'json'};
import {partsFor,radians} from './static/furniture.js';

export function createFurniture(item,definition,textureFor=()=>null){
  const group=new THREE.Group();group.name='furniture_'+item.id;
  group.userData.furnitureId=item.id;group.userData.signature=JSON.stringify(item);
  group.position.set(item.x,0,item.z);group.rotation.y=-radians(item.rotation);
  for(const part of partsFor(definition,item.variant)){
    const body=part.color==='body',profile=profiles[body?(item.material||'default'):'default'];
    const source=primitives[part.shape],geometry=new THREE.BufferGeometry();
    geometry.setAttribute('position',new THREE.Float32BufferAttribute(source.positions,3));
    geometry.setAttribute('normal',new THREE.Float32BufferAttribute(source.normals,3));
    geometry.setAttribute('uv',new THREE.Float32BufferAttribute(source.uvs.map(v=>v*(profile.repeat||1)),2));
    const [w,h,d]=part.size.map((v,i)=>v*[item.width,item.height,item.depth][i]);geometry.scale(w,h,d);
    const material=new THREE.MeshStandardMaterial({color:body?item.color:part.color,
      roughness:profile.roughness,metalness:profile.metalness,map:profile.texture?textureFor(profile.texture):null});
    const mesh=new THREE.Mesh(geometry,material);
    mesh.userData.furnitureId=item.id;mesh.userData.body=body;
    mesh.position.fromArray(part.position.map((v,i)=>v*[item.width,item.height,item.depth][i]));group.add(mesh);
  }
  return group;
}

export function disposeFurniture(group){group.traverse(o=>{o.geometry?.dispose();o.material?.dispose();});}
