"""Real HTTP flow, ownership boundaries, persistence and malformed uploads."""
import io
import json
import tempfile
import time
import unittest
import copy
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from webapp.app import create_app
from webapp.geometry import ROOT

HEADERS={'X-Blueprint-Request':'1'}


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app=create_app(self.temp.name)
        self.client=TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__,None,None,None)

    def register(self,name='test_user'):
        response=self.client.post('/api/register',headers=HEADERS,json={'username':name,'password':'test-password-2026'})
        self.assertEqual(response.status_code,200,response.text)
        return response

    def upload(self,image=None,name='test.png'):
        if image is None:
            image=(ROOT/'examples/user-floorplan-2026-11-06/input.png').read_bytes()
        return self.client.post('/api/jobs',headers=HEADERS,files={'file':(name,image,'image/png')},data={'parameters':'{}'})

    def completed(self,jid):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            response=self.client.get('/api/jobs/'+jid)
            data=response.json()
            if data['status'] in ['done','error']:
                self.assertEqual(data['status'],'done',data)
                return data
            time.sleep(.15)
        self.fail('Reconstruction timed out')

    def test_registration_login_logout_and_session_survives_new_client(self):
        response=self.register()
        self.assertIn('httponly',response.headers['set-cookie'].lower())
        self.assertEqual(self.client.get('/api/me').json()['user']['username'],'test_user')
        fresh=TestClient(self.app);fresh.cookies.update(self.client.cookies)
        self.assertEqual(fresh.get('/api/me').json()['user']['username'],'test_user')
        self.client.post('/api/logout',headers=HEADERS)
        self.assertIsNone(fresh.get('/api/me').json()['user'])
        wrong=self.client.post('/api/login',headers=HEADERS,json={'username':'test_user','password':'bad'})
        self.assertEqual(wrong.status_code,401)
        valid=self.client.post('/api/login',headers=HEADERS,json={'username':'test_user','password':'test-password-2026'})
        self.assertEqual(valid.status_code,200)

    def test_requires_authentication_and_csrf_header(self):
        self.assertEqual(self.client.get('/api/jobs').status_code,401)
        self.assertEqual(self.upload().status_code,401)
        response=self.client.post('/api/register',json={'username':'blocked','password':'test-password-2026'})
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.client.get('/static/app.js').headers['cache-control'],'no-cache')

    def test_actual_upload_model_download_and_cross_account_isolation(self):
        self.register('owner')
        response=self.upload(name='../../户型.png')
        self.assertEqual(response.status_code,202,response.text)
        job=self.completed(response.json()['id'])
        self.assertEqual(job['name'],'户型.png')
        self.assertEqual(job['result']['method'],'reviewed')
        self.assertEqual(job['result']['door_count'],7)
        model=self.client.get(f"/api/jobs/{job['id']}/files/model.glb")
        self.assertEqual(model.content[:4],b'glTF')
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/files/request.json").status_code,404)
        self.client.post('/api/logout',headers=HEADERS);self.register('other_user')
        self.assertEqual(self.client.get('/api/jobs').json()['jobs'],[])
        self.assertEqual(self.client.get('/api/jobs/'+job['id']).status_code,404)
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/files/model.glb").status_code,404)

    def test_revision_creates_new_version_and_preserves_original(self):
        self.register()
        job=self.completed(self.upload().json()['id'])
        plan=job['result']['plan']
        response=self.client.post(f"/api/jobs/{job['id']}/revise",headers=HEADERS,json={
            'params':{**job['params'],'wall_height':3.2},'walls':plan['walls'],'doors':plan['doors'][:-1]})
        self.assertEqual(response.status_code,202,response.text)
        revised=self.completed(response.json()['id'])
        self.assertNotEqual(revised['id'],job['id'])
        self.assertEqual(revised['result']['wall_height'],3.2)
        self.assertEqual(revised['result']['door_count'],6)
        original=self.client.get('/api/jobs/'+job['id']).json()
        self.assertEqual(original['result']['door_count'],7)

    def test_rejects_corrupt_oversized_and_invalid_dimension_inputs(self):
        self.register()
        self.assertEqual(self.upload(b'not an image').status_code,400)
        response=self.client.post('/api/jobs',headers=HEADERS,files={'file':('a.png',b'wrong','image/png')},data={'parameters':json.dumps({'door_height':4,'wall_height':2.8})})
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.upload(b'x'*(12*1024*1024+1)).status_code,413)

    def test_generic_floorplan_is_reconstructed_without_fixture(self):
        self.register()
        image=Image.new('RGB',(500,400),'white');draw=ImageDraw.Draw(image)
        draw.rectangle((50,50,450,350),outline='black',width=7)
        draw.line((250,50,250,350),fill='black',width=7)
        buffer=io.BytesIO();image.save(buffer,format='PNG')
        job=self.completed(self.upload(buffer.getvalue()).json()['id'])
        self.assertEqual(job['result']['method'],'linework')
        self.assertGreaterEqual(job['result']['wall_count'],5)
        self.assertTrue(job['result']['closed_meshes'])

    def manual_request(self):
        return {'name':'手绘两居室','depth_m':9,'params':{'width_m':12},
                'walls':[[[32,32],[160,32]],[[160,32],[160,128]],[[160,128],[32,128]],
                         [[32,128],[32,32]],[[96,32],[96,128]]],
                'doors':[[[96,64],[96,96]]]}

    def test_manual_drawing_bypasses_recognition_keeps_scale_and_supports_decoration(self):
        import trimesh
        self.register('manual_owner')
        data=self.manual_request()
        response=self.client.post('/api/jobs/manual',headers=HEADERS,json=data)
        self.assertEqual(response.status_code,202,response.text)
        job=self.completed(response.json()['id']);jid=job['id']
        self.assertEqual(job['result']['method'],'manual')
        self.assertEqual(job['result']['plan']['walls'],data['walls'])
        self.assertEqual(job['result']['door_count'],1)
        self.assertEqual(job['result']['plan']['width'],384)
        glb=self.client.get(f'/api/jobs/{jid}/files/model.glb').content
        scene=trimesh.load(io.BytesIO(glb),file_type='glb',force='scene')
        # A 4 x 3m room in a 12 x 9m canvas stays 4 x 3m between wall centerlines.
        self.assertAlmostEqual(scene.extents[0],4.16,places=4)
        self.assertAlmostEqual(scene.extents[2],3.16,places=4)
        surfaces=self.client.get(f'/api/jobs/{jid}/surfaces').json()['surfaces']
        self.assertEqual(sum(s['kind']=='floor' for s in surfaces),2)
        url=f'/api/jobs/{jid}/layout';layout=self.client.get(url).json()
        layout['items']=[dict(id='manual_chair',type='chair',x=1,z=-1,width=.45,depth=.45,height=.85,rotation=0,color='#91aabd')]
        self.assertEqual(self.client.put(url,headers=HEADERS,json=layout).status_code,200)
        self.assertEqual(self.client.get(f'/api/jobs/{jid}/furnished.glb').content[:4],b'glTF')
        revised=self.client.post(f'/api/jobs/{jid}/revise',headers=HEADERS,json={
            'params':{**job['params'],'wall_height':3.1,'width_m':15},'walls':data['walls'],'doors':[]})
        self.assertEqual(revised.status_code,202,revised.text)
        new=self.completed(revised.json()['id'])
        self.assertEqual(new['result']['plan']['source'],'manual')
        self.assertEqual(new['result']['door_count'],0)
        self.assertEqual(new['result']['wall_height'],3.1)
        resized=trimesh.load(io.BytesIO(self.client.get(f"/api/jobs/{new['id']}/files/model.glb").content),file_type='glb',force='scene')
        self.assertAlmostEqual(resized.extents[0],5.16,places=4)
        self.assertEqual(self.client.get('/api/jobs/'+jid).json()['result']['door_count'],1)
        self.client.post('/api/logout',headers=HEADERS);self.register('manual_other')
        self.assertEqual(self.client.get('/api/jobs/'+jid).status_code,404)
        self.assertEqual(self.client.post(f'/api/jobs/{jid}/revise',headers=HEADERS,json={
            'params':job['params'],'walls':data['walls'],'doors':[]}).status_code,404)

    def test_manual_drawing_rejects_open_outside_or_floating_door_input(self):
        data=self.manual_request()
        self.assertEqual(self.client.post('/api/jobs/manual',headers=HEADERS,json=data).status_code,401)
        self.register()
        self.assertEqual(self.client.post('/api/jobs/manual',json=data).status_code,403)
        cases=[]
        for key,value in [('walls',data['walls'][:2]),('walls',[[[-1,0],[4,0]]]),
                          ('doors',[[[180,180],[210,180]]]),('depth_m',101),('walls',data['walls']*100)]:
            case=copy.deepcopy(data);case[key]=value;cases.append(case)
        for case in cases:
            response=self.client.post('/api/jobs/manual',headers=HEADERS,json=case)
            self.assertEqual(response.status_code,422,response.text)
        self.assertEqual(self.client.get('/api/jobs').json()['jobs'],[])

    def test_faded_small_scan_retains_outer_and_internal_walls(self):
        self.register()
        image=Image.new('RGB',(360,270),(220,215,208));draw=ImageDraw.Draw(image)
        draw.rectangle((35,30,320,240),outline=(130,130,130),width=3)
        draw.line((180,30,180,240),fill=(130,130,130),width=3)
        buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=80)
        job=self.completed(self.upload(buffer.getvalue()).json()['id'])
        self.assertGreaterEqual(job['result']['wall_count'],5)
        self.assertTrue(job['result']['closed_meshes'])

    def test_chunked_body_limit_does_not_require_content_length(self):
        def chunks():
            for _ in range(14):
                yield b'x'*(1024*1024)
        response=self.client.post('/api/register',headers=HEADERS,content=chunks())
        self.assertEqual(response.status_code,413)

    def test_furnishing_persists_exports_and_is_owner_scoped(self):
        import trimesh
        self.register('furniture_owner')
        job=self.completed(self.upload().json()['id'])
        url=f"/api/jobs/{job['id']}/layout"
        document=self.client.get(url).json()
        self.assertEqual(document['revision'],0)
        original=self.client.get(f"/api/jobs/{job['id']}/files/model.glb").content
        document['items']=[dict(id='bed_1',type='bed',x=3,z=-4,width=1.8,depth=2,height=1.05,rotation=90,color='#91aabd')]
        document['finishes']={'floor':'oak','wall':'ivory'}
        response=self.client.put(url,headers=HEADERS,json=document)
        self.assertEqual(response.status_code,200,response.text)
        saved=response.json()
        self.assertEqual(saved['revision'],1)
        # Existing cookies also access the saved layout through a freshly opened app.
        with TestClient(create_app(self.temp.name)) as reopened:
            reopened.cookies.update(self.client.cookies)
            self.assertEqual(reopened.get(url).json(),saved)
        exported=self.client.get(f"/api/jobs/{job['id']}/furnished.glb")
        self.assertEqual(exported.content[:4],b'glTF')
        scene=trimesh.load(io.BytesIO(exported.content),file_type='glb',force='scene')
        parts=[scene.geometry[name] for name in scene.geometry if name.startswith('furniture_bed_1_')]
        self.assertGreaterEqual(len(parts),6)
        furniture=trimesh.util.concatenate(parts)
        # In GLB space the 90-degree bed spans 2m on X and 1.8m on Z at the saved center.
        self.assertAlmostEqual(furniture.bounds[:,0].mean(),3,places=4)
        self.assertAlmostEqual(furniture.bounds[:,2].mean(),-4,places=4)
        self.assertAlmostEqual(furniture.extents[0],2,places=4)
        self.assertAlmostEqual(furniture.extents[2],1.8,places=4)
        floor=next(mesh for name,mesh in scene.geometry.items() if name.startswith('floor'))
        self.assertEqual(floor.visual.material.baseColorFactor.tolist()[:3],[200,173,130])
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/files/model.glb").content,original)
        # A second page cannot silently overwrite a newer layout.
        stale=self.client.put(url,headers=HEADERS,json=document)
        self.assertEqual(stale.status_code,409)
        self.assertEqual(self.client.get(url).json(),saved)
        saved['items']=[]
        self.assertEqual(self.client.put(url,headers=HEADERS,json=saved).json()['revision'],2)
        self.client.post('/api/logout',headers=HEADERS)
        self.assertEqual(self.client.get(url).status_code,401)
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/surfaces").status_code,401)
        self.register('furniture_other')
        self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.put(url,headers=HEADERS,json=saved).status_code,404)
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/furnished.glb").status_code,404)
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/surfaces").status_code,404)

    def test_furnishing_rejects_invalid_documents_without_overwriting(self):
        self.register()
        job=self.completed(self.upload().json()['id'])
        url=f"/api/jobs/{job['id']}/layout"
        valid={'version':1,'revision':0,'finishes':{'floor':'original','wall':'original'},'items':[
            dict(id='sofa_1',type='sofa',x=3,z=-4,width=2.4,depth=.9,height=.85,rotation=0,color='#99ab96')]}
        for key,value in [('type','unknown'),('width',-2),('x',float('nan')),('x',999),('rotation',360),('color','red')]:
            malformed=copy.deepcopy(valid);malformed['items'][0][key]=value
            response=self.client.put(url,headers={**HEADERS,'Content-Type':'application/json'},content=json.dumps(malformed))
            self.assertEqual(response.status_code,422,(key,response.text))
        for items in [valid['items']*2,valid['items']*201]:
            self.assertEqual(self.client.put(url,headers=HEADERS,json={**valid,'items':items}).status_code,422)
        self.assertEqual(self.client.put(url,json=valid).status_code,403)
        self.assertEqual(self.client.get(url).json()['items'],[])

    def test_furnishing_needs_completed_job(self):
        self.register()
        store=self.app.state.store
        user=store.verify('test_user','test-password-2026')
        store.add_job('waiting',user['id'],'waiting.png',{})
        self.assertEqual(self.client.get('/api/jobs/waiting/layout').status_code,409)
        self.assertEqual(self.client.put('/api/jobs/waiting/layout',headers=HEADERS,json={}).status_code,409)
        self.assertEqual(self.client.get('/api/jobs/waiting/furnished.glb').status_code,409)
        self.assertEqual(self.client.get('/api/jobs/waiting/surfaces').status_code,409)

    def test_decoration_roundtrip_legacy_defaults_and_textured_export(self):
        import trimesh
        self.register()
        job=self.completed(self.upload().json()['id'])
        url=f"/api/jobs/{job['id']}/layout"
        item=dict(id='sofa',type='sofa',x=3,z=-4,width=2.4,depth=1.4,height=.85,rotation=90,color='#a56e46')
        old={'version':1,'revision':0,'items':[item],'finishes':{'floor':'original','wall':'original'}}
        # Simulate a document written by the previous version of the application.
        self.app.state.store.save_layout(job['id'],old)
        layout=self.client.get(url).json()
        self.assertEqual(layout['items'][0]['variant'],'standard')
        self.assertEqual(layout['items'][0]['material'],'default')
        decorated={**layout['items'][0],'variant':'chaise-left','material':'fabric'}
        layout['items']=[decorated]
        response=self.client.put(url,headers=HEADERS,json=layout)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.get(url).json()['items'],[decorated])
        for key in ['x','z','width','depth','height','rotation']:
            self.assertEqual(decorated[key],item[key])
        exported=self.client.get(f"/api/jobs/{job['id']}/furnished.glb")
        scene=trimesh.load(io.BytesIO(exported.content),file_type='glb',force='scene')
        parts=[mesh for name,mesh in scene.geometry.items() if name.startswith('furniture_sofa_')]
        textured=[mesh for mesh in parts if mesh.visual.material.baseColorTexture is not None]
        self.assertGreater(len(textured),0)
        self.assertEqual(textured[0].visual.material.baseColorTexture.size,(128,128))
        self.assertEqual(float(textured[0].visual.uv.max()),4)
        self.assertAlmostEqual(textured[0].visual.material.roughnessFactor,.98)
        self.assertEqual(textured[0].visual.material.baseColorFactor.tolist()[:3],[165,110,70])
        saved=response.json()
        for patch in [{'variant':'not-real'},{'material':'ceramic'}]:
            bad={**saved,'items':[{**decorated,**patch}]}
            self.assertEqual(self.client.put(url,headers=HEADERS,json=bad).status_code,422)
        self.assertEqual(self.client.get(url).json(),saved)

    def test_local_surface_finishes_persist_and_export_without_changing_structure(self):
        import numpy as np
        import trimesh
        from webapp.surfaces import get_surfaces, _surfaces
        self.register()
        job=self.completed(self.upload().json()['id'])
        base=f"/api/jobs/{job['id']}"
        original=self.client.get(base+'/files/model.glb').content
        regions=self.client.get(base+'/surfaces').json()['surfaces']
        floors=[s for s in regions if s['kind']=='floor'];walls=[s for s in regions if s['kind']=='wall']
        self.assertGreater(len(floors),1);self.assertGreater(len(walls),1)
        _surfaces.cache_clear()
        self.assertEqual(get_surfaces(Path(self.temp.name)/'jobs'/job['id'])['surfaces'],regions)
        # The finish skins retain all original vertical wall areas, including door holes.
        source=trimesh.load(io.BytesIO(original),file_type='glb',force='scene')
        wall_mesh=next(m for n,m in source.geometry.items() if n.startswith('wall'))
        expected=wall_mesh.area_faces[np.abs(wall_mesh.face_normals[:,1])<.01].sum()
        skins=[]
        for part in walls:
            mesh=trimesh.Trimesh(np.array(part['positions']).reshape(-1,3),np.array(part['indices']).reshape(-1,3),process=False)
            self.assertTrue(np.all(mesh.face_normals @ part['normal'] > .99))
            skins.append(mesh)
        self.assertAlmostEqual(sum(m.area for m in skins),float(expected),places=3)
        layout=self.client.get(base+'/layout').json()
        layout['finishes'].update(floorStyle={'material':'wood','color':'#c8ad82'},wallStyle={'material':'painted','color':'#eee9dc'},surfaces={
            floors[0]['id']:{'material':'tile','color':'#abb9c1'},walls[0]['id']:{'material':'wallpaper','color':'#91aabd'}})
        saved=self.client.put(base+'/layout',headers=HEADERS,json=layout)
        self.assertEqual(saved.status_code,200,saved.text)
        self.assertEqual(self.client.get(base+'/layout').json(),saved.json())
        exported=self.client.get(base+'/furnished.glb')
        self.assertEqual(exported.status_code,200,exported.text[:200] if exported.status_code!=200 else '')
        scene=trimesh.load(io.BytesIO(exported.content),file_type='glb',force='scene')
        for region,roughness,color in [(floors[0],.3,[171,185,193]),(walls[0],.92,[145,170,189]),(floors[1],.62,[200,173,130])]:
            mat=scene.geometry['finish_'+region['id']].visual.material
            self.assertAlmostEqual(mat.roughnessFactor,roughness)
            self.assertEqual(mat.baseColorFactor.tolist()[:3],color)
            self.assertEqual(mat.baseColorTexture.size,(256,256))
        self.assertEqual(self.client.get(base+'/files/model.glb').content,original)
        for overrides in [{floors[0]['id']:{'material':'leather','color':'#ffffff'}},{'wall-0000000000000000':{'material':'painted','color':'#ffffff'}}]:
            bad=copy.deepcopy(saved.json());bad['finishes']['surfaces']=overrides
            self.assertEqual(self.client.put(base+'/layout',headers=HEADERS,json=bad).status_code,422)
        self.assertEqual(self.client.get(base+'/layout').json(),saved.json())

    def test_every_furniture_family_has_editable_styles_and_exports(self):
        import trimesh
        from webapp.furnishing import CATALOG, Furniture
        self.register();job=self.completed(self.upload().json()['id']);base=f"/api/jobs/{job['id']}"
        layout=self.client.get(base+'/layout').json();expected={}
        for definition in CATALOG.values():
            self.assertTrue(definition.get('variants'),definition['id'])
            for variant in [{'id':'standard','parts':definition['parts']},*definition['variants']]:
                item=dict(id=definition['id']+'_'+variant['id'],type=definition['id'],x=3,z=-4,rotation=0,
                          width=definition['width'],depth=definition['depth'],height=definition['height'],
                          color='#8f9e8c',variant=variant['id'],material=definition['materials'][0])
                for material in definition['materials']:
                    Furniture.model_validate({**item,'material':material})
                layout['items'].append(item);expected['furniture_'+item['id']+'_']=len(variant['parts'])
        saved=self.client.put(base+'/layout',headers=HEADERS,json=layout)
        self.assertEqual(saved.status_code,200,saved.text)
        exported=self.client.get(base+'/furnished.glb')
        scene=trimesh.load(io.BytesIO(exported.content),file_type='glb',force='scene')
        for prefix,count in expected.items():
            self.assertEqual(sum(n.startswith(prefix) for n in scene.geometry),count,prefix)


if __name__=='__main__':
    unittest.main()
