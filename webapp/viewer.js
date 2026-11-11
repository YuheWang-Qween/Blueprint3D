import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {FLOORS,WALLS,radians} from './static/furniture.js';

export class ModelViewer {
  constructor(host) {
    this.host=host;
    this.scene=new THREE.Scene();
    this.scene.background=new THREE.Color('#e7edf0');
    this.renderer=new THREE.WebGLRenderer({antialias:true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,2));
    this.renderer.outputColorSpace=THREE.SRGBColorSpace;
    this.renderer.localClippingEnabled=true;
    this.renderer.domElement.setAttribute('aria-label','可拖动旋转、滚轮缩放的三维户型模型');
    this.renderer.domElement.setAttribute('role','img');
    host.appendChild(this.renderer.domElement);
    this.camera=new THREE.PerspectiveCamera(38,1,.01,3000);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);
    this.controls.enableDamping=false;
    this.controls.maxPolarAngle=Math.PI*.495;
    this.controls.addEventListener('change',()=>this.render());
    this.scene.add(new THREE.HemisphereLight('#ffffff','#9caebe',2.5));
    const light=new THREE.DirectionalLight('#ffffff',3);
    light.position.set(-10,18,6); this.scene.add(light);
    const fill=new THREE.DirectionalLight('#c5d8ec',1.2);
    fill.position.set(8,9,-8); this.scene.add(fill);
    this.grid=new THREE.GridHelper(80,80,'#bdcbd3','#d2dce2');
    this.grid.position.y=-.15;this.scene.add(this.grid);
    this.plane=new THREE.Plane(new THREE.Vector3(0,-1,0),1.4);
    this.loadId=0;
    this.furniture=new THREE.Group();this.scene.add(this.furniture);
    this.layout=null;this.catalog=[];
    new ResizeObserver(()=>this.resize()).observe(host);
    this.resize();
  }
  resize(){
    const w=this.host.clientWidth,h=this.host.clientHeight;
    if(!w||!h)return;
    const previousAspect=this.camera.aspect;
    this.camera.aspect=w/h;this.camera.updateProjectionMatrix();
    this.renderer.setSize(w,h,false);
    if(this.span && Math.abs(previousAspect-this.camera.aspect)>.05)this.reset();
    else this.render();
  }
  render(){this.renderer.render(this.scene,this.camera);}
  async load(url){
    const id=++this.loadId;
    const response=await fetch(url,{credentials:'same-origin'});
    if(!response.ok)throw Error('模型读取失败，请刷新后重试。');
    const buffer=await response.arrayBuffer();
    const gltf=await new GLTFLoader().parseAsync(buffer,'');
    if(id!==this.loadId)return;
    if(this.model){
      this.scene.remove(this.model);
      this.model.traverse(o=>{if(o.geometry)o.geometry.dispose();if(o.material){for(const m of [].concat(o.material))m.dispose();}});
    }
    this.model=gltf.scene;this.scene.add(this.model);
    const bounds=new THREE.Box3().setFromObject(this.model);
    const center=bounds.getCenter(new THREE.Vector3());
    this.model.position.x-=center.x;this.model.position.z-=center.z;
    this.furniture.position.set(-center.x,0,-center.z);
    this.model.traverse(o=>{if(o.material)for(const m of [].concat(o.material))m.userData.baseColor=m.color?.clone();});
    const size=bounds.getSize(new THREE.Vector3());
    this.span=Math.max(size.x,size.z,size.y,2);
    this.radius=size.length()/2+size.y*.1;
    this.target=new THREE.Vector3(0,size.y*.26,0);
    this.plane.constant=size.y*.5;
    this.cut(false);this.reset();
    this.setLayout(this.layout,this.catalog);
    this.host.dataset.ready='true';
  }
  reset(){
    if(!this.span)return;
    this.camera.position.set(.85,1.13,1.25).normalize().multiplyScalar(this.fitDistance()).add(this.target);
    this.controls.target.copy(this.target);this.controls.update();this.render();
  }
  fitDistance(){
    const vertical=THREE.MathUtils.degToRad(this.camera.fov)/2;
    const horizontal=Math.atan(Math.tan(vertical)*this.camera.aspect);
    return this.radius*1.05/Math.sin(Math.min(vertical,horizontal));
  }
  top(){
    if(!this.span)return;
    this.camera.position.set(0,this.fitDistance(),.001);
    this.controls.target.set(0,0,0);this.controls.update();this.render();
  }
  cut(enabled){
    this.model?.traverse(o=>{if(o.material){for(const m of [].concat(o.material)){m.clippingPlanes=enabled?[this.plane]:[];m.needsUpdate=true;}}});
    this.render();
  }
  setLayout(layout,catalog=[]){
    this.layout=layout;this.catalog=catalog;
    for(const child of [...this.furniture.children]){
      child.traverse(o=>{o.geometry?.dispose();o.material?.dispose();});this.furniture.remove(child);
    }
    this.model?.traverse(o=>{
      if(!o.material)return;
      const kind=o.name.startsWith('floor')?'floor':o.name.startsWith('wall')?'wall':null;
      const color=kind==='floor'?FLOORS[layout?.finishes.floor]:kind==='wall'?WALLS[layout?.finishes.wall]:null;
      for(const m of [].concat(o.material)){
        if(color)m.color.set(color);else if(m.userData.baseColor)m.color.copy(m.userData.baseColor);
      }
    });
    for(const item of layout?.items||[]){
      const definition=catalog.find(c=>c.id===item.type);if(!definition)continue;
      const group=new THREE.Group();group.name='furniture_'+item.id;
      group.position.set(item.x,0,item.z);group.rotation.y=-radians(item.rotation);
      for(const part of definition.parts){
        const [w,h,d]=part.size.map((v,i)=>v*[item.width,item.height,item.depth][i]);
        const geometry=part.shape==='cylinder'?new THREE.CylinderGeometry(.5,.5,1,24):new THREE.BoxGeometry(1,1,1);
        geometry.scale(w,h,d);
        const mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:part.color==='body'?item.color:part.color,roughness:.8}));
        mesh.position.fromArray(part.position.map((v,i)=>v*[item.width,item.height,item.depth][i]));group.add(mesh);
      }
      this.furniture.add(group);
    }
    this.host.dataset.furnitureCount=String(layout?.items.length||0);
    this.render();
  }
}
