"""Isolated reconstruction process, called only with a server-owned job directory."""
import json
import os
import sys
import traceback
from pathlib import Path

from .geometry import ROOT, reconstruct, write_model


def neural(directory, params):
    import numpy as np
    import pyvista as pv
    import trimesh
    sys.path.insert(0,str(ROOT/'ForgeFloor'))
    from extruder import NeuralInferenceOrchestrator, ForgePlanPipeline
    image=directory/'input.png'
    working=directory/'inference'
    orchestrator=NeuralInferenceOrchestrator(str(ROOT))
    success,files,errors=orchestrator.run_both(str(image),str(working))
    if not success:
        raise ValueError('增强识别失败，请检查服务器上的权重和推理依赖。')
    mask=np.loadtxt(files['sema_csv'],delimiter=',')
    rows,cols=np.where(mask>0)
    if not len(cols):
        raise ValueError('没有识别到房间区域，请尝试线稿建模。')
    scale=params['width_m']/max(int(cols.max()-cols.min()),1)
    result=ForgePlanPipeline(str(working),str(ROOT)).run(
        sema_path=files['sema_csv'],split_path=files['split_csv_pipeline'],underlay_path=str(image),
        wall_height=params['wall_height']/scale,wall_thickness=params['wall_thickness']/scale,
        door_height=params['door_height']/scale,room_height=0,window_base_height=.8/scale,
        window_vertical_size=min(1.1,params['wall_height']-.8)/scale,
        flip_y=True,flip_x=False,rotation=0,show_input_image=False,show_segmentation=False,show_interactive=False)
    if not result['success']:
        raise ValueError('识别结果未形成有效模型，请尝试线稿建模并校正墙线。')
    meshes={}
    blocks=pv.read(working/'scene.vtm')
    for name,mesh in zip(blocks.keys(),blocks):
        mesh=mesh.triangulate()
        meshes[name]=trimesh.Trimesh(vertices=mesh.points*scale,faces=mesh.faces.reshape(-1,4)[:,1:],process=False)
    triangles=write_model(meshes,directory)
    import shutil,zipfile
    shutil.copyfile(working/'architectural_overlay.png',directory/'overlay.png')
    info={'triangles':triangles,'wall_count':None,'door_count':None,'width_m':params['width_m'],
          'wall_height':params['wall_height'],'units':'meters; user-estimated scale','method':'neural',
          'note':'增强识别结果，请对照原图检查房间分隔与门窗位置。','closed_meshes':True,'plan':None}
    (directory/'result.json').write_text(json.dumps(info,ensure_ascii=False))
    with zipfile.ZipFile(directory/'model.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in ['model.glb','model.obj','model.mtl','result.json','overlay.png']:
            z.write(directory/name,name)
    return info


def main():
    directory=Path(sys.argv[1]).resolve()
    options=json.loads((directory/'request.json').read_text())
    try:
        if options['params']['engine']=='neural':
            neural(directory,options['params'])
        else:
            reconstruct(directory/'input.png',directory,options['params'],options.get('plan'))
    except Exception as error:
        message=str(error) if isinstance(error,ValueError) else '处理未完成，请换一张清晰户型图或联系管理员检查运行环境。'
        (directory/'error.txt').write_text(message)
        traceback.print_exc()
        sys.exit(1)


if __name__=='__main__':
    main()
