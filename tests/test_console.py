import importlib.util,sys,types,os,json,unittest
from unittest.mock import MagicMock
os.environ.update(TABLE_NAME='test',ALLOWED_RECIPIENT='recipient@example.com',QUEUE_URL='queue',BASE_URL='https://test.example',SENDER='noreply@example.com',CLIENT_ID='client',AUTH_DOMAIN='https://auth.example')
b=types.ModuleType('boto3');b.resource=MagicMock();b.client=MagicMock();sys.modules['boto3']=b
m=types.ModuleType('botocore.exceptions')
class CE(Exception):
 def __init__(self,c):self.response={'Error':{'Code':c}}
m.ClientError=CE;sys.modules['botocore.exceptions']=m
spec=importlib.util.spec_from_file_location('beacon',str(__import__('pathlib').Path(__file__).resolve().parents[1]/'backend/console.py'));c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
real_allowed=c.recipient_allowed
class Tests(unittest.TestCase):
 def setUp(self):
  c.T=MagicMock();c.Q=MagicMock();c.T.get_item.return_value={};c.recipient_allowed=MagicMock(side_effect=lambda email:email==c.ALLOWED)
 def event(self,path,method='GET',body=None,claims=None):return {'rawPath':path,'body':json.dumps(body or {}),'requestContext':{'http':{'method':method},'authorizer':{'jwt':{'claims':claims or {'sub':'owner','username':'owner','token_use':'access','cognito:groups':'operators'}}}}}
 def form(self):return dict(name='自检',subject='test',body='测试 {{link}}',days=30,consent=True,email=c.ALLOWED)
 def test_rank_counters_are_not_campaigns(self):
  c.T.scan.return_value={'Items':[{'token':'rank#x','record_type':'rank_counter','rank_count':2},{'token':'link','record_type':'link','campaign':'unit'}]}
  r=c.admin(self.event('/admin/dashboard'),None);d=json.loads(r['body']);self.assertEqual(len(d['campaigns']),1);self.assertEqual(d['campaigns'][0]['token'],'link')
 def test_no_auth(self):self.assertEqual(c.admin({'requestContext':{}},None)['statusCode'],403)
 def test_non_operator(self):self.assertEqual(c.admin(self.event('/admin/dashboard',claims={'sub':'x','token_use':'access','cognito:groups':'viewer'}),None)['statusCode'],403)
 def test_id_token_rejected(self):self.assertEqual(c.admin(self.event('/admin/dashboard',claims={'sub':'x','token_use':'id','cognito:groups':'operators'}),None)['statusCode'],403)
 def test_create_draft(self):
  r=c.admin(self.event('/admin/campaigns','POST',self.form()),None);self.assertEqual(r['statusCode'],201)
  item=c.T.put_item.call_args.kwargs['Item'];self.assertEqual(item['initial_state'],'draft');self.assertTrue(item['disabled']);c.Q.send_message.assert_not_called()
 def test_recipient_rejected(self):
  f=self.form();f['email']='other@example.com';self.assertEqual(c.admin(self.event('/admin/campaigns','POST',f),None)['statusCode'],400)
 def test_consent_required(self):
  f=self.form();f['consent']=False;self.assertEqual(c.admin(self.event('/admin/campaigns','POST',f),None)['statusCode'],400)
 def test_link_required(self):
  f=self.form();f['body']='no link';self.assertEqual(c.admin(self.event('/admin/campaigns','POST',f),None)['statusCode'],400)
 def test_send_queue(self):
  c.T.get_item.return_value={'Item':{'email':c.ALLOWED,'authorization_confirmed':True,'subject':'test','initial_state':'draft','expires_at':9999999999}}
  self.assertEqual(c.admin(self.event('/admin/campaigns/abc/send','POST'),None)['statusCode'],202)
  self.assertEqual(json.loads(c.Q.send_message.call_args.kwargs['MessageBody'])['kind'],'initial')
 def test_no_resend(self):
  c.T.get_item.return_value={'Item':{'email':c.ALLOWED,'authorization_confirmed':True,'subject':'test','initial_state':'sent'}}
  self.assertEqual(c.admin(self.event('/admin/campaigns/abc/send','POST'),None)['statusCode'],409);c.Q.send_message.assert_not_called()
 def test_pause(self):
  c.T.get_item.return_value={'Item':{'token':'abc'}};self.assertEqual(c.admin(self.event('/admin/campaigns/abc/pause','POST'),None)['statusCode'],200)
 def test_public_traversal(self):self.assertEqual(c.public({'rawPath':'/console-assets/../console.py'},None)['statusCode'],404)
 def test_add_recipient(self):
  r=c.admin(self.event('/admin/recipients','POST',{'email':'Alice@Example.com','label':'参与者','consent':True}),None)
  self.assertEqual(r['statusCode'],201);item=c.T.put_item.call_args.kwargs['Item'];self.assertEqual(item['email'],'alice@example.com');self.assertTrue(item['enabled']);c.Q.send_message.assert_not_called()
 def test_add_requires_authorization(self):
  self.assertEqual(c.admin(self.event('/admin/recipients','POST',{'email':'alice@example.com','consent':False}),None)['statusCode'],400)
 def test_bad_recipient_header(self):
  self.assertEqual(c.admin(self.event('/admin/recipients','POST',{'email':'x@example.com\r\nBcc:other@example.com','consent':True}),None)['statusCode'],400)
 def test_disable_default_recipient(self):
  self.assertEqual(c.admin(self.event('/admin/recipients/status','POST',{'email':c.ALLOWED,'enabled':False}),None)['statusCode'],200)
  self.assertFalse(c.T.update_item.call_args.kwargs['ExpressionAttributeValues'][':v'])
 def test_enable_requires_consent(self):
  self.assertEqual(c.admin(self.event('/admin/recipients/status','POST',{'email':c.ALLOWED,'enabled':True}),None)['statusCode'],400)
 def test_duplicate_recipient(self):
  c.T.get_item.return_value={'Item':{'record_type':'recipient'}}
  self.assertEqual(c.admin(self.event('/admin/recipients','POST',{'email':'alice@example.com','consent':True}),None)['statusCode'],409)
 def test_create_other_enabled_recipient(self):
  c.recipient_allowed.return_value=True;c.recipient_allowed.side_effect=None
  f=self.form();f['email']='alice@example.com';self.assertEqual(c.admin(self.event('/admin/campaigns','POST',f),None)['statusCode'],201)
  self.assertEqual(c.T.put_item.call_args.kwargs['Item']['email'],'alice@example.com')
 def test_real_lookup_enabled(self):
  c.T.get_item.return_value={'Item':{'record_type':'recipient','enabled':True,'authorization_confirmed':True}}
  self.assertTrue(real_allowed('alice@example.com'))
 def test_real_lookup_disabled_default(self):
  c.T.get_item.return_value={'Item':{'record_type':'recipient','enabled':False,'authorization_confirmed':True}}
  self.assertFalse(real_allowed(c.ALLOWED))
if __name__=='__main__':unittest.main()
