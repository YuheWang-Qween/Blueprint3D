import * as THREE from 'three';
import profiles from './static/material-profiles.json' with {type:'json'};
import {surfaceStyle} from './static/surface-finishes.js';

export function createSurface(part){
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(part.positions,3));
  geometry.setAttribute('normal',new THREE.Float32BufferAttribute(Array.from({length:part.positions.length/3},()=>part.normal).flat(),3));
  geometry.setIndex(part.indices);
  const mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial());
  mesh.name='finish_'+part.id;mesh.userData.surface=part;return mesh;
}

export function finishSurface(mesh,finishes,textureFor=()=>null,clippingPlanes=[]){
  const part=mesh.userData.surface,style=surfaceStyle(finishes,part.kind,part.id),signature=JSON.stringify(style);
  if(signature!==mesh.userData.finishSignature){
    const profile=profiles[style.material],repeat=profile.surfaceRepeat||1;
    mesh.geometry.setAttribute('uv',new THREE.Float32BufferAttribute(part.uvs.map(v=>v*repeat),2));
    mesh.material.dispose();const texture=profile.surfaceTexture||profile.texture;
    mesh.material=new THREE.MeshStandardMaterial({color:style.color,roughness:profile.roughness,metalness:profile.metalness,
      map:texture?textureFor(texture):null,side:THREE.DoubleSide});
    mesh.userData.finishSignature=signature;
  }
  mesh.material.clippingPlanes=clippingPlanes;mesh.material.needsUpdate=true;
}
