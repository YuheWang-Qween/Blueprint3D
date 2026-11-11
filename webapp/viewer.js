import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';
import {FLOORS,WALLS} from './static/furniture.js';
import {createFurniture,disposeFurniture} from './furniture-renderer.js';
import {InteriorNavigation} from './interior-navigation.js';

export class ModelViewer {
  constructor(host,{onSelect=()=>{},onNavigation=()=>{}}={}) {
    this.host=host;
    this.onSelect=onSelect;this.onNavigation=onNavigation;
    this.scene=new THREE.Scene();
    this.scene.background=new THREE.Color('#e7edf0');
    this.renderer=new THREE.WebGLRenderer({antialias:true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,2));
    this.renderer.outputColorSpace=THREE.SRGBColorSpace;
    this.renderer.toneMapping=THREE.ACESFilmicToneMapping;
    this.renderer.localClippingEnabled=true;
    this.renderer.domElement.setAttribute('aria-label','三维户型：拖动旋转，滚轮缩放，点击家具进行精装修');
    this.renderer.domElement.setAttribute('role','img');
    this.renderer.domElement.tabIndex=0;
    host.appendChild(this.renderer.domElement);
    this.camera=new THREE.PerspectiveCamera(38,1,.01,3000);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);
    this.controls.enableDamping=false;
    this.controls.maxPolarAngle=Math.PI*.495;
    this.controls.addEventListener('change',()=>this.render());
    this.scene.add(new THREE.HemisphereLight('#ffffff','#9caebe',1.3));
    const light=new THREE.DirectionalLight('#ffffff',2.2);
    light.position.set(-10,18,6); this.scene.add(light);
    const fill=new THREE.DirectionalLight('#c5d8ec',.7);
    fill.position.set(8,9,-8); this.scene.add(fill);
    this.grid=new THREE.GridHelper(80,80,'#bdcbd3','#d2dce2');
    this.grid.position.y=-.15;this.scene.add(this.grid);
    this.plane=new THREE.Plane(new THREE.Vector3(0,-1,0),1.4);
    this.loadId=0;
    this.furniture=new THREE.Group();this.scene.add(this.furniture);
    this.layout=null;this.catalog=[];
    const room=new RoomEnvironment(),pmrem=new THREE.PMREMGenerator(this.renderer);
    this.environment=pmrem.fromScene(room,.04);this.scene.environment=this.environment.texture;this.scene.environmentIntensity=.65;
    room.dispose();pmrem.dispose();
    this.textures=new Map();this.ray=new THREE.Raycaster();this.selectedId=null;this.decorating=false;this.visible=true;
    this.selectionBox=new THREE.Box3();this.selectionHelper=new THREE.Box3Helper(this.selectionBox,'#d39221');
    this.selectionHelper.visible=false;this.selectionHelper.material.depthTest=false;this.selectionHelper.renderOrder=10;this.scene.add(this.selectionHelper);
    this.navigation=new InteriorNavigation(this);this.keys=new Set();this.pointers=new Set();this.bindInteractions();
    new ResizeObserver(()=>this.resize()).observe(host);
    this.resize();
  }
  resize(){
    const w=this.host.clientWidth,h=this.host.clientHeight;
    if(!w||!h)return;
    const previousAspect=this.camera.aspect;
    this.camera.aspect=w/h;this.camera.updateProjectionMatrix();
    this.renderer.setSize(w,h,false);
    if(this.span && !this.navigation.active && Math.abs(previousAspect-this.camera.aspect)>.05){if(this.focusedId)this.focusSelected();else this.reset();}
    else this.render();
  }
  render(){this.renderer.render(this.scene,this.camera);}
  async load(url){
    this.setWalking(false);this.focusedId=null;this.select(null);
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
    this.setWalking(false);this.focusedId=null;
    this.camera.fov=38;this.camera.updateProjectionMatrix();
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
    this.setWalking(false);this.focusedId=null;
    this.camera.fov=38;this.camera.updateProjectionMatrix();
    this.camera.position.set(0,this.fitDistance(),.001);
    this.controls.target.set(0,0,0);this.controls.update();this.render();
  }
  cut(enabled){
    this.cutEnabled=enabled;
    this.model?.traverse(o=>{if(o.material){for(const m of [].concat(o.material)){m.clippingPlanes=enabled?[this.plane]:[];m.needsUpdate=true;}}});
    this.render();
  }
  setLayout(layout,catalog=[]){
    this.layout=layout;this.catalog=catalog;
    if(!layout){this.setWalking(false);this.selectedId=null;}
    const ids=new Set(layout?.items.map(item=>item.id)||[]);
    for(const child of [...this.furniture.children]){
      if(!ids.has(child.userData.furnitureId)){disposeFurniture(child);this.furniture.remove(child);}
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
      const previous=this.furniture.children.find(g=>g.userData.furnitureId===item.id);
      if(previous?.userData.signature===JSON.stringify(item))continue;
      if(previous){disposeFurniture(previous);this.furniture.remove(previous);}
      const group=createFurniture(item,definition,name=>{
        if(!this.textures.has(name)){
          const texture=new THREE.TextureLoader().load('/static/materials/'+name,()=>this.render());
          texture.colorSpace=THREE.SRGBColorSpace;texture.wrapS=texture.wrapT=THREE.RepeatWrapping;this.textures.set(name,texture);
        }
        return this.textures.get(name);
      });
      this.furniture.add(group);
    }
    this.host.dataset.furnitureCount=String(layout?.items.length||0);
    if(!ids.has(this.selectedId))this.selectedId=null;
    this.updateSelection();
    this.render();
  }
  group(id=this.selectedId){return this.furniture.children.find(g=>g.userData.furnitureId===id);}
  select(id){this.selectedId=id;this.updateSelection();this.render();}
  updateSelection(){
    this.scene.updateMatrixWorld(true);const group=this.group();
    this.selectionHelper.visible=!!group&&this.decorating;
    if(group)this.selectionBox.setFromObject(group).expandByScalar(.025);
    this.host.dataset.selectedFurniture=this.selectedId||'';
  }
  setDecorating(value){this.decorating=value;this.updateSelection();this.render();}
  setVisible(value){this.visible=value;if(!value)this.setWalking(false);}
  pick(x,y){
    if(!this.layout)return;const rect=this.renderer.domElement.getBoundingClientRect();
    this.ray.setFromCamera(new THREE.Vector2((x-rect.left)/rect.width*2-1,-(y-rect.top)/rect.height*2+1),this.camera);
    this.scene.updateMatrixWorld(true);
    const hits=this.ray.intersectObjects([this.furniture,...(this.model?[this.model]:[])],true);
    const hit=hits.find(h=>h.object.userData.furnitureId||!this.cutEnabled||h.point.y<=this.plane.constant+.001);
    const id=hit?.object.userData.furnitureId||null;this.select(id);this.onSelect(id);
  }
  focusSelected(){
    const group=this.group();if(!group)return false;this.setWalking(false);this.scene.updateMatrixWorld(true);
    const box=new THREE.Box3().setFromObject(group),center=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3());
    this.camera.fov=50;this.camera.updateProjectionMatrix();
    const vertical=THREE.MathUtils.degToRad(this.camera.fov)/2,horizontal=Math.atan(Math.tan(vertical)*this.camera.aspect);
    const distance=Math.max(1.8,size.length()*.6/Math.sin(Math.min(vertical,horizontal)));
    const direction=new THREE.Vector3(.45,1.25,1).normalize().applyAxisAngle(new THREE.Vector3(0,1,0),group.rotation.y);
    this.camera.position.copy(center).addScaledVector(direction,distance);this.controls.target.copy(center);this.controls.update();
    this.focusedId=this.selectedId;this.render();return true;
  }
  setWalking(enabled){
    if(!this.navigation)return false;
    if(enabled){if(!this.navigation.enter(this.group()))return false;}
    else{this.navigation.exit();this.keys.clear();cancelAnimationFrame(this.walkFrame);this.walkFrame=null;}
    this.grid.visible=!this.navigation.active;this.host.dataset.viewMode=this.navigation.active?'interior':'orbit';
    this.onNavigation(this.navigation.active);return true;
  }
  walkKey(key,pressed){
    if(!this.navigation.active)return;
    if(pressed)this.keys.add(key);else this.keys.delete(key);
    if(this.walkFrame)return;
    let previous=performance.now();
    const step=now=>{
      this.walkFrame=null;if(!this.navigation.active||!this.visible||!this.keys.size)return;
      const has=(...names)=>names.some(n=>this.keys.has(n));
      this.navigation.move(Number(has('d','arrowright'))-Number(has('a','arrowleft')),
        Number(has('w','arrowup'))-Number(has('s','arrowdown')),(now-previous)/1000);
      previous=now;this.walkFrame=requestAnimationFrame(step);
    };
    this.walkFrame=requestAnimationFrame(step);
  }
  bindInteractions(){
    const canvas=this.renderer.domElement;
    canvas.addEventListener('pointerdown',e=>{
      this.pointers.add(e.pointerId);if(this.pointers.size!==1){this.pointer=null;return;}if(e.button!==0)return;
      this.pointer={id:e.pointerId,x:e.clientX,y:e.clientY,lastX:e.clientX,lastY:e.clientY,moved:false};
      if(this.navigation.active){canvas.setPointerCapture(e.pointerId);canvas.focus({preventScroll:true});}
    });
    canvas.addEventListener('pointermove',e=>{
      const p=this.pointer;if(!p||p.id!==e.pointerId)return;
      if(Math.hypot(e.clientX-p.x,e.clientY-p.y)>5)p.moved=true;
      if(this.navigation.active&&p.moved)this.navigation.look(e.clientX-p.lastX,e.clientY-p.lastY);
      p.lastX=e.clientX;p.lastY=e.clientY;
    });
    canvas.addEventListener('pointerup',e=>{
      const p=this.pointer;this.pointers.delete(e.pointerId);this.pointer=null;
      if(p&&!p.moved&&p.id===e.pointerId&&this.visible)this.pick(e.clientX,e.clientY);
    });
    canvas.addEventListener('pointercancel',e=>{this.pointers.delete(e.pointerId);this.pointer=null;});
    document.addEventListener('keydown',e=>{
      if(!this.visible||!this.navigation.active)return;
      if(e.key==='Escape'){this.setWalking(false);return;}
      if(e.target.closest('input,select,textarea,button'))return;
      if(['w','a','s','d','arrowup','arrowdown','arrowleft','arrowright'].includes(e.key.toLowerCase())){e.preventDefault();this.walkKey(e.key.toLowerCase(),true);}
    });
    document.addEventListener('keyup',e=>this.walkKey(e.key.toLowerCase(),false));
    window.addEventListener('blur',()=>{this.keys.clear();this.pointer=null;this.pointers.clear();});
  }
}
