from copy import deepcopy
import unittest
from desktop_recorder.contract import identity, Invalid, validate, FORMAT
from uuid import uuid4

class ImageCopyContractTests(unittest.TestCase):
    def target(self):
        return dict(app='C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe', window_key='Sports Cave OS',
                    control_type='Button', automation_id='copyImage', name='Copy black frame',
                    postcondition='sports-cave.product-image-copy.v1',
                    browser=dict(profile='11111111-1111-4111-8111-111111111111',page='https://sports-cave-image-factory.onrender.com/?page=product_uploads',frame='top',control='document',product='a'*64),
                    scope=[dict(control_type='Group',automation_id='root',name=''),
                           dict(control_type='Document',automation_id='RootWebArea',name=''),
                           dict(control_type='Document',automation_id='sc-product-upload-copy',name='product_upload_gallery.product_upload_gallery')])
    def test_valid_product_copy(self):
        identity(self.target())
    def test_reject_wrong_source(self):
        for field,value in [('automation_id','copyPrompt'),('name','Copy image'),('control_type','Edit')]:
            t=self.target(); t[field]=value
            with self.subTest(field=field), self.assertRaises(Invalid): identity(t)
    def test_reject_unbound_product_or_frame(self):
        t=self.target(); del t['browser']['product']
        with self.assertRaises(Invalid): identity(t)
        t=self.target(); t['scope'][2]['automation_id']='other-frame'
        with self.assertRaises(Invalid): identity(t)

    def test_image_paste_lineage_and_destination(self):
        source=dict(version=2,kind='invoke',requires=['uia.invoke.v2'],target=self.target(),timeout_ms=30000)
        destination=dict(app=self.target()['app'],window_key='ChatGPT',control_type='Edit',automation_id='',
            name='New chat in SC Mockups/Uploads',scope=[],browser=dict(profile='11111111-1111-4111-8111-111111111111',
            page='https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project',frame='top',control='document'))
        paste=dict(version=3,kind='image_paste',requires=['image.paste.v3'],target=destination,timeout_ms=30000)
        def task(actions):
            return dict(format=FORMAT,version=1,id=str(uuid4()),name='Image paste test',starting_context=dict(mode='prepared',binding=None),actions=actions)
        validate(task([source,paste]))
        for actions in ([paste],[source,paste,paste]):
            with self.assertRaises(Invalid):validate(task(actions))
        for field,value in [('page','https://chatgpt.com/c/unrelated'),('frame','other')]:
            bad=deepcopy(paste);bad['target']['browser'][field]=value
            with self.subTest(field=field),self.assertRaises(Invalid):validate(task([source,bad]))
        bad=deepcopy(paste);bad['value']={'image':'never persist'}
        with self.assertRaises(Invalid):validate(task([source,bad]))
        bad=deepcopy(paste);bad['requires']=['transfer.paste.v3']
        with self.assertRaises(Invalid):validate(task([source,bad]))
