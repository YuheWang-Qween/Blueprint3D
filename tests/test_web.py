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
        self.register('furniture_other')
        self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.put(url,headers=HEADERS,json=saved).status_code,404)
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/furnished.glb").status_code,404)

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


if __name__=='__main__':
    unittest.main()
