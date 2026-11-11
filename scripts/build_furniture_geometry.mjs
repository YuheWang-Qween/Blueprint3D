// Bake shared primitives so browser rendering and Python GLB exports use identical meshes.
// Three.js is pinned in webapp/package-lock.json; its license ships in static/THREE-LICENSE.txt.
import {BoxGeometry,CylinderGeometry} from '../webapp/node_modules/three/build/three.module.js';
import {RoundedBoxGeometry} from '../webapp/node_modules/three/examples/jsm/geometries/RoundedBoxGeometry.js';
import {writeFileSync} from 'node:fs';
const primitives={};
for(const [name,source] of [['box',new BoxGeometry(1,1,1)],['cylinder',new CylinderGeometry(.5,.5,1,24)],['rounded-box',new RoundedBoxGeometry(1,1,1,2,.12)]]){
  const geometry=source.index?source.toNonIndexed():source;
  const values=key=>Array.from(geometry.attributes[key].array,x=>Number(x.toFixed(6)));
  primitives[name]={positions:values('position'),normals:values('normal'),uvs:values('uv')};
}
writeFileSync(new URL('../webapp/static/furniture-geometry.json',import.meta.url),JSON.stringify(primitives)+'\n');
