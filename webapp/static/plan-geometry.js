const clone=value=>structuredClone(value);
export const DRAWING_UNITS=32;
export const blankPlan=(width,depth)=>({width:width*DRAWING_UNITS,height:depth*DRAWING_UNITS,walls:[],doors:[],source:'manual'});
export function metersPerUnit(plan,widthM){
  if(plan.source==='manual')return widthM/plan.width;
  const xs=plan.walls.flat().map(p=>p[0]);return widthM/(xs.length?Math.max(Math.max(...xs)-Math.min(...xs),1):plan.width);
}
export function project(point,line){const [a,b]=line,dx=b[0]-a[0],dy=b[1]-a[1],den=dx*dx+dy*dy,t=den?Math.max(0,Math.min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/den)):0;return [a[0]+t*dx,a[1]+t*dy];}
export const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
export function nearest(point,lines){let result=null;lines.forEach((line,index)=>{const p=project(point,line),d=distance(p,point);if(!result||d<result.distance)result={point:p,distance:d,index,line};});return result;}
export function rectangle(a,b){return [[a,[b[0],a[1]]],[[b[0],a[1]],b],[b,[a[0],b[1]]],[[a[0],b[1]],a]].map(clone);}
export function appendWalls(existing,lines){return [...existing,...lines.filter(l=>!existing.some(e=>(distance(e[0],l[0])<.001&&distance(e[1],l[1])<.001)||(distance(e[0],l[1])<.001&&distance(e[1],l[0])<.001)))];}
export function eraseWall(plan,index){const wall=plan.walls[index];plan.doors=plan.doors.filter(line=>!line.every(p=>distance(p,project(p,wall))<.001));plan.walls.splice(index,1);}
export function validateDraft(data){
  if(data?.version!==1||typeof data.name!=='string'||!data.name.trim()||data.name.length>80)throw Error('手绘草稿格式无效。');
  if(!Number.isFinite(data.params?.width_m)||data.params.width_m<2||data.params.width_m>100||!Number.isFinite(data.depth_m)||data.depth_m<2||data.depth_m>100)throw Error('画布尺寸无效。');
  for(const [key,min,max] of [['wall_height',1.8,8],['door_height',1.5,5],['wall_thickness',.06,.6]])if(!Number.isFinite(data.params[key])||data.params[key]<min||data.params[key]>max)throw Error('手绘草稿中的尺寸无效。');
  if(data.params.door_height>=data.params.wall_height)throw Error('门高需要低于墙高。');
  const plan=blankPlan(data.params.width_m,data.depth_m);
  for(const key of ['walls','doors']){
    if(!Array.isArray(data[key])||data[key].length>450)throw Error('手绘线段数量无效。');
    for(const line of data[key])if(!Array.isArray(line)||line.length!==2||!line.every(p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)&&p[0]>=0&&p[0]<=plan.width&&p[1]>=0&&p[1]<=plan.height)||distance(...line)<1)throw Error('手绘草稿中的线段无效。');
    plan[key]=clone(data[key]);
  }
  return plan;
}

export function planToWorld(plan,widthM){
  const points=plan.walls.flat(),minX=Math.min(...points.map(p=>p[0])),maxY=Math.max(...points.map(p=>p[1])),scale=metersPerUnit(plan,widthM);
  const convert=line=>line.map(([x,y])=>[(x-minX)*scale,(y-maxY)*scale]);
  return {walls:plan.walls.map(convert),doors:plan.doors.map(convert)};
}
