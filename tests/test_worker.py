import importlib.util,sys,types,unittest,os,json,time
from unittest.mock import MagicMock,patch
os.environ.update(TABLE_NAME='test',QUEUE_URL='queue',SENDER='noreply@example.com',ALLOWED_RECIPIENT='recipient@example.com')
class ClientError(Exception):
 def __init__(self,code):self.response={'Error':{'Code':code}}
class Attr:
 def __init__(self,*a):pass
 def is_in(self,*a):return self
 def __or__(self,other):return self
mods={k:types.ModuleType(k) for k in ['boto3','botocore','botocore.exceptions','botocore.config','boto3.dynamodb','boto3.dynamodb.conditions']}
mods['boto3'].resource=MagicMock();mods['boto3'].client=MagicMock()
mods['botocore.exceptions'].ClientError=ClientError
mods['botocore.config'].Config=MagicMock()
mods['boto3.dynamodb.conditions'].Attr=Attr
sys.modules.update(mods)
spec=importlib.util.spec_from_file_location('app',str(__import__('pathlib').Path(__file__).resolve().parents[1]/'backend/worker.py'));app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
real_allowed=app.recipient_allowed
class Tests(unittest.TestCase):
 def setUp(self):
  app.table=MagicMock();app.sqs=MagicMock();app.ses=MagicMock();app.recipient_allowed=MagicMock(side_effect=lambda email:email==app.ALLOWED)
  self.item={'token':'abc','email':app.ALLOWED,'expires_at':int(time.time())+100,'notice_state':'pending','first_visit':int(time.time()),'campaign':'unit'}
  app.table.get_item.return_value={'Item':self.item}
 def test_valid_visit(self):
  r=app.track({'pathParameters':{'token':'abc'}},None)
  self.assertEqual(r['statusCode'],200);app.table.put_item.assert_called_once();self.assertNotIn('email',app.table.put_item.call_args.kwargs['Item']);app.sqs.send_message.assert_called_once();self.assertEqual(app.table.update_item.call_count,2)
 def test_invalid_link(self):
  app.table.get_item.return_value={};self.assertEqual(app.track({'pathParameters':{'token':'abc'}},None)['statusCode'],404);app.sqs.send_message.assert_not_called()
 def test_expired_link(self):
  self.item['expires_at']=0;self.assertEqual(app.track({'pathParameters':{'token':'abc'}},None)['statusCode'],404)
 def test_block_other_recipient(self):
  self.item['email']='other@example.com';self.assertEqual(app.track({'pathParameters':{'token':'abc'}},None)['statusCode'],403)
 def test_success(self):
  app.ses.send_email.return_value={'MessageId':'test-id'};app.deliver('abc');app.ses.send_email.assert_called_once();self.assertEqual(app.table.update_item.call_args.kwargs['ExpressionAttributeValues'][':s'],'sent')
 def test_dedup_sent(self):
  self.item['notice_state']='sent';app.deliver('abc');app.ses.send_email.assert_not_called()
 def test_conditional_lock(self):
  app.table.update_item.side_effect=ClientError('ConditionalCheckFailedException');app.deliver('abc');app.ses.send_email.assert_not_called()
 def test_ambiguous_delivery(self):
  app.ses.send_email.side_effect=TimeoutError();app.deliver('abc');self.assertEqual(app.table.update_item.call_args.kwargs['ExpressionAttributeValues'][':s'],'uncertain')
 def test_known_failure_retry(self):
  app.ses.send_email.side_effect=ClientError('MessageRejected')
  with self.assertRaises(ClientError):app.deliver('abc')
  self.assertEqual(app.table.update_item.call_args.kwargs['ExpressionAttributeValues'][':s'],'pending')
 def test_retry_limit(self):
  self.item['attempts']=5;app.deliver('abc');app.ses.send_email.assert_not_called();self.assertEqual(app.table.update_item.call_args.kwargs['ExpressionAttributeValues'][':s'],'failed')
 def test_resend_transport(self):
  import io
  app._resend_key='fake-unit-test-key'
  msg={'Subject':{'Data':'test'},'Body':{'Text':{'Data':'test body'}}}
  with patch.dict(os.environ,EMAIL_PROVIDER='resend'),patch.object(app.urllib.request,'urlopen',return_value=io.BytesIO(b'{"id":"resend-test-id"}')) as call:
   result=app.send_email('abc',Source='noreply@example.com',Destination={'ToAddresses':[app.ALLOWED]},Message=msg)
   self.assertEqual(result['Provider'],'resend');self.assertEqual(result['MessageId'],'resend-test-id')
   request=call.call_args.args[0]
   self.assertEqual(request.full_url,'https://api.resend.com/emails')
   self.assertNotIn('reply_to',json.loads(request.data));self.assertNotIn('operator@example.com',request.data.decode())
   self.assertTrue(request.get_header('Idempotency-key').startswith('awareness-notice/'))
 def test_resend_failure_retry(self):
  with patch.object(app,'send_email',side_effect=app.ResendError(429,'rate_limit_exceeded')):
   with self.assertRaises(app.ResendError):app.deliver('abc')
   self.assertEqual(app.table.update_item.call_args.kwargs['ExpressionAttributeValues'][':s'],'pending')
 def test_resend_bad_auth_stops(self):
  with patch.object(app,'send_email',side_effect=app.ResendError(401,'validation_error')):
   app.deliver('abc');self.assertEqual(app.table.update_item.call_args.kwargs['ExpressionAttributeValues'][':s'],'failed')
 def test_resend_stores_provider(self):
  with patch.object(app,'send_email',return_value={'MessageId':'resend-id','Provider':'resend'}):
   app.deliver('abc');self.assertEqual(app.table.update_item.call_args.kwargs['ExpressionAttributeValues'][':p'],'resend')
 def test_initial_queue_send(self):
  self.item.update(initial_state='queued',initial_attempts=0,authorization_confirmed=True,subject='test',body='visit {{link}}',created_at=int(time.time()),expires_at=int(time.time())+86400)
  with patch.dict(os.environ,PUBLIC_BASE_URL='https://example.com'),patch.object(app,'send_email',return_value={'MessageId':'initial-id','Provider':'resend'}) as send:
   app.deliver_initial('abc');self.assertTrue(send.call_args.args[0].startswith('initial/'));self.assertEqual(app.table.update_item.call_args.kwargs['ExpressionAttributeValues'][':s'],'sent')
 def test_paused_initial_not_sent(self):
  self.item.update(initial_state='queued',authorization_confirmed=True,disabled=True)
  with patch.object(app,'send_email') as send:app.deliver_initial('abc');send.assert_not_called()
 def test_paused_notice_not_sent(self):
  self.item['disabled']=True
  with patch.object(app,'send_email') as send:app.deliver('abc');send.assert_not_called()
 def test_directory_enabled(self):
  app.table.get_item.return_value={'Item':{'record_type':'recipient','enabled':True,'authorization_confirmed':True}}
  self.assertTrue(real_allowed('other@example.com'))
 def test_directory_disabled(self):
  app.table.get_item.return_value={'Item':{'record_type':'recipient','enabled':False,'authorization_confirmed':True}}
  self.assertFalse(real_allowed(app.ALLOWED))
 def test_other_recipient_notice_destination(self):
  self.item['email']='other@example.com';app.recipient_allowed.side_effect=None;app.recipient_allowed.return_value=True
  with patch.object(app,'send_email',return_value={'MessageId':'new-id','Provider':'resend'}) as send:
   app.deliver('abc');self.assertEqual(send.call_args.kwargs['Destination']['ToAddresses'],['other@example.com'])
 def test_disabled_recipient_cancels_notice(self):
  app.recipient_allowed.side_effect=None;app.recipient_allowed.return_value=False
  with patch.object(app,'send_email') as send:
   app.deliver('abc');send.assert_not_called();self.assertEqual(app.table.update_item.call_args.kwargs['ExpressionAttributeValues'][':s'],'suppressed')
 def test_disabled_recipient_cancels_initial(self):
  self.item.update(initial_state='queued',authorization_confirmed=True);app.recipient_allowed.side_effect=None;app.recipient_allowed.return_value=False
  with patch.object(app,'send_email') as send:
   app.deliver_initial('abc');send.assert_not_called();self.assertEqual(app.table.update_item.call_args.kwargs['ExpressionAttributeValues'][':s'],'cancelled')
 def test_directory_item_not_tracking_link(self):
  app.table.get_item.return_value={'Item':{'record_type':'recipient','enabled':True}}
  self.assertEqual(app.track({'pathParameters':{'token':'recipient-foo'}},None)['statusCode'],404)
if __name__=='__main__':unittest.main()
