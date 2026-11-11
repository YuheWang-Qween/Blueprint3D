import * as THREE from 'three';

// A bounded indoor camera, independent of keyboard/touch input and WebGL rendering.
export class InteriorNavigation {
  constructor(viewer){this.viewer=viewer;this.active=false;this.eyeHeight=1.55;this.radius=.18;this.ray=new THREE.Raycaster();}
  surfaces(kind){const result=[];this.viewer.model?.traverse(o=>{if(o.isMesh&&o.name.startsWith(kind))result.push(o);});return result;}
  floorHeight(point){
    this.ray.set(new THREE.Vector3(point.x,20,point.z),new THREE.Vector3(0,-1,0));this.ray.near=0;this.ray.far=30;
    return this.ray.intersectObjects(this.floors,false)[0]?.point.y;
  }
  clear(point){
    const floor=this.floorHeight(point);if(floor===undefined)return false;
    for(const group of this.viewer.furniture.children){
      const box=new THREE.Box3().setFromObject(group);
      if(point.x>box.min.x-this.radius&&point.x<box.max.x+this.radius&&point.z>box.min.z-this.radius&&point.z<box.max.z+this.radius)return false;
    }
    for(const height of [.45,1.5]){
      const origin=new THREE.Vector3(point.x,floor+height,point.z);
      // Closed wall shells: odd intersections means the candidate is inside a wall.
      this.ray.set(origin,new THREE.Vector3(.873,0,.488).normalize());this.ray.far=10000;
      const hits=this.ray.intersectObjects(this.walls,false);let last=-1,count=0;
      for(const hit of hits)if(Math.abs(hit.distance-last)>.0001){last=hit.distance;count++;}
      if(count%2)return false;
      for(const direction of [[1,0,0],[-1,0,0],[0,0,1],[0,0,-1]]){
        this.ray.set(origin,new THREE.Vector3(...direction));this.ray.far=this.radius;
        if(this.ray.intersectObjects(this.walls,false).length)return false;
      }
    }
    return true;
  }
  enter(targetGroup){
    if(this.active)return true;
    const v=this.viewer;if(!v.model)return false;v.scene.updateMatrixWorld(true);
    this.floors=this.surfaces('floor');this.walls=this.surfaces('wall');
    const bounds=new THREE.Box3().setFromObject(v.model),center=bounds.getCenter(new THREE.Vector3());
    const candidates=[];let look=center.clone();look.y=.9;
    if(targetGroup){
      const box=new THREE.Box3().setFromObject(targetGroup);look=box.getCenter(new THREE.Vector3());
      candidates.push(new THREE.Vector3(look.x,0,box.max.z+.8),new THREE.Vector3(look.x,0,box.min.z-.8),
        new THREE.Vector3(box.max.x+.8,0,look.z),new THREE.Vector3(box.min.x-.8,0,look.z));
    }
    candidates.push(center);
    for(let x=1;x<10;x++)for(let z=1;z<10;z++)candidates.push(new THREE.Vector3(
      THREE.MathUtils.lerp(bounds.min.x,bounds.max.x,x/10),0,THREE.MathUtils.lerp(bounds.min.z,bounds.max.z,z/10)));
    const start=candidates.find(p=>this.clear(p));if(!start)return false;
    this.previous={position:v.camera.position.clone(),quaternion:v.camera.quaternion.clone(),target:v.controls.target.clone(),fov:v.camera.fov,cut:v.cutEnabled};
    this.active=true;v.controls.enabled=false;v.camera.fov=65;v.camera.updateProjectionMatrix();
    v.camera.position.set(start.x,this.floorHeight(start)+this.eyeHeight,start.z);
    if(Math.hypot(start.x-look.x,start.z-look.z)<.1)look.z-=1;
    v.camera.lookAt(look);const orientation=new THREE.Euler().setFromQuaternion(v.camera.quaternion,'YXZ');
    this.yaw=orientation.y;this.pitch=THREE.MathUtils.clamp(orientation.x,-1.1,1.1);
    v.cut(false);this.look(0,0);return true;
  }
  exit(){
    if(!this.active)return;const v=this.viewer,p=this.previous;this.active=false;
    v.camera.fov=p.fov;v.camera.updateProjectionMatrix();v.camera.position.copy(p.position);v.camera.quaternion.copy(p.quaternion);
    v.controls.target.copy(p.target);v.controls.enabled=true;v.controls.update();v.cut(p.cut);v.render();
  }
  look(dx,dy){
    if(!this.active)return;this.yaw-=dx*.004;this.pitch=THREE.MathUtils.clamp(this.pitch-dy*.004,-1.1,1.1);
    this.viewer.camera.quaternion.setFromEuler(new THREE.Euler(this.pitch,this.yaw,0,'YXZ'));this.viewer.render();
  }
  move(side,forward,seconds){
    if(!this.active)return false;
    const delta=new THREE.Vector3(side,0,-forward);if(!delta.length())return false;
    delta.normalize().applyAxisAngle(new THREE.Vector3(0,1,0),this.yaw).multiplyScalar(Math.min(seconds,.05)*1.6);
    const camera=this.viewer.camera;let moved=false;
    for(const axis of ['x','z']){
      const target=camera.position.clone();target[axis]+=delta[axis];
      if(this.clear(target)){camera.position[axis]=target[axis];moved=true;}
    }
    if(moved){camera.position.y=this.floorHeight(camera.position)+this.eyeHeight;this.viewer.render();}return moved;
  }
}
