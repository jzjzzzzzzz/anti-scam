"""Authorized security-awareness link recorder. No credential collection."""
import os,json,time,html,secrets,hashlib,urllib.request,urllib.error
from datetime import datetime,timezone
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr
TABLE=os.environ['TABLE_NAME']
table=boto3.resource('dynamodb').Table(TABLE)
sqs=boto3.client('sqs')
ddb=boto3.client('dynamodb')
ses=boto3.client('ses',config=__import__('botocore.config',fromlist=['Config']).Config(retries={'max_attempts':0},connect_timeout=5,read_timeout=15))
ALLOWED=os.environ['ALLOWED_RECIPIENT']

class ResendError(Exception):
 def __init__(self,status,name='ResendError'):
  self.status=status;self.name=name
  super().__init__(name)

_resend_key=None
def send_email(token,Source,Destination,Message):
 global _resend_key
 if os.environ.get('EMAIL_PROVIDER','ses')!='resend':
  return dict(ses.send_email(Source=Source,Destination=Destination,Message=Message),Provider='ses')
 if _resend_key is None:
  raw=boto3.client('secretsmanager').get_secret_value(SecretId=os.environ['RESEND_SECRET_ARN'])['SecretString']
  _resend_key=json.loads(raw)['RESEND_API_KEY']
 payload={'from':Source,'to':Destination['ToAddresses'],'subject':Message['Subject']['Data'],'text':Message['Body']['Text']['Data']}
 if Message['Body'].get('Html'):payload['html']=Message['Body']['Html']['Data']
 req=urllib.request.Request('https://api.resend.com/emails',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+_resend_key,'Content-Type':'application/json','User-Agent':'AwarenessSelfTest/1.0','Idempotency-Key':'awareness-notice/'+hashlib.sha256(token.encode()).hexdigest()},method='POST')
 try:
  with urllib.request.urlopen(req,timeout=15) as resp:result=json.load(resp)
 except urllib.error.HTTPError as e:
  try:name=json.loads(e.read()).get('name','ResendError')
  except Exception:name='ResendError'
  raise ResendError(e.code,name) from None
 if not result.get('id'):raise ResendError(502,'missing_message_id')
 return {'MessageId':result['id'],'Provider':'resend'}

def recipient_allowed(email):
 if not isinstance(email,str) or not email:return False
 row=table.get_item(Key={'token':'recipient#'+hashlib.sha256(email.strip().lower().encode()).hexdigest()},ConsistentRead=True).get('Item')
 if row is None:return email==ALLOWED
 return row.get('record_type')=='recipient' and row.get('enabled') is True and row.get('authorization_confirmed') is True

def response(code,body):
 return {'statusCode':code,'headers':{'content-type':'text/html; charset=utf-8','cache-control':'no-store','referrer-policy':'no-referrer','content-security-policy':"default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",'x-content-type-options':'nosniff'},'body':body}

def enqueue(token):
 sqs.send_message(QueueUrl=os.environ['QUEUE_URL'],MessageBody=json.dumps({'token':token}))

def rank_key(item):
 # Exact campaign name + owning administrator; never publish identities.
 scope=json.dumps([item.get('authorized_by','legacy'),item.get('campaign','')],ensure_ascii=False)
 return 'rank#'+hashlib.sha256(scope.encode()).hexdigest()

def ordinal(n):
 n=int(n)
 return str(n)+('th' if 10<n%100<14 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th'))

def rank_message(item):
 if item.get('click_rank'):
  return 'Your link was the '+ordinal(item['click_rank'])+' distinct link recorded in this campaign since ranking was enabled.'
 return 'A click-order number is unavailable for this link because its first visit predates ranking.'

def record_visit(item,now):
 token=item['token']
 for attempt in range(6):
  if 'first_visit' in item:
   table.update_item(Key={'token':token},UpdateExpression='SET last_visit=:n ADD visits :one',ConditionExpression='attribute_exists(#t) AND (attribute_not_exists(disabled) OR disabled=:f) AND expires_at>=:n',ExpressionAttributeNames={'#t':'token'},ExpressionAttributeValues={':n':now,':one':1,':f':False})
   return item
  key=rank_key(item)
  counter=table.get_item(Key={'token':key},ConsistentRead=True).get('Item',{})
  previous=int(counter.get('rank_count',0));rank=previous+1
  counter_values={':r':{'S':'rank_counter'},':new':{'N':str(rank)}}
  if counter:
   condition='rank_count=:old';counter_values[':old']={'N':str(previous)}
  else:condition='attribute_not_exists(#t)'
  try:
   ddb.transact_write_items(TransactItems=[
    {'Update':{'TableName':TABLE,'Key':{'token':{'S':key}},'UpdateExpression':'SET record_type=:r,rank_count=:new','ConditionExpression':condition,**({'ExpressionAttributeNames':{'#t':'token'}} if not counter else {}),'ExpressionAttributeValues':counter_values}},
    {'Update':{'TableName':TABLE,'Key':{'token':{'S':token}},'UpdateExpression':'SET first_visit=:n,last_visit=:n,click_rank=:rank ADD visits :one','ConditionExpression':'attribute_exists(#t) AND attribute_not_exists(first_visit) AND (attribute_not_exists(disabled) OR disabled=:f) AND expires_at>=:n','ExpressionAttributeNames':{'#t':'token'},'ExpressionAttributeValues':{':n':{'N':str(now)},':rank':{'N':str(rank)},':one':{'N':'1'},':f':{'BOOL':False}}}}
   ])
   return dict(item,first_visit=now,last_visit=now,click_rank=rank)
  except ClientError as e:
   if e.response['Error']['Code'] not in ('TransactionCanceledException','TransactionConflictException'):raise
   reasons=e.response.get('CancellationReasons',[])
   if any(r.get('Code') not in (None,'None','ConditionalCheckFailed','TransactionConflict') for r in reasons):raise
   item=table.get_item(Key={'token':token},ConsistentRead=True).get('Item',{})
   if not item or item.get('disabled') or int(item.get('expires_at',0))<now:raise
   time.sleep(.025*(attempt+1))
 raise RuntimeError('Visit ranking contention')

def track(event,context):
 token=event.get('pathParameters',{}).get('token','')
 if not token or len(token)>80:return response(404,'Link not found')
 now=int(time.time())
 item=table.get_item(Key={'token':token},ConsistentRead=True).get('Item')
 if not item or item.get('record_type') not in (None,'link') or int(item.get('expires_at',0))<now or item.get('disabled'):return response(404,'Link not found or expired')
 if not recipient_allowed(item['email']):return response(403,'Recipient is not enabled')
 try:item=record_visit(item,now)
 except Exception:return response(503,'Visit could not be recorded. Please try again shortly.')
 table.put_item(Item={'token':'event#'+token+'#'+secrets.token_hex(12),'record_type':'event','link_token':token,'visited_at':now,'ttl':now+90*86400})
 try:
  table.update_item(Key={'token':token},UpdateExpression='SET notice_state=:p',ConditionExpression='notice_state=:a',ExpressionAttributeValues={':p':'pending',':a':'armed'})
 except ClientError as e:
  if e.response['Error']['Code']!='ConditionalCheckFailedException':raise
 try:enqueue(token)
 except Exception:pass
 rank=html.escape(rank_message(item))
 campaign=html.escape(str(item.get('campaign','')))
 return response(200,f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Security awareness exercise</title><style>body{{font:17px/1.7 system-ui;max-width:720px;margin:60px auto;padding:24px;color:#171717}}section{{background:#f4f4f4;border:1px solid #ccc;padding:24px}}h1{{line-height:1.2}}.rank{{font-size:24px;font-weight:700}}small{{color:#444}}</style><h1>This was a simulated phishing email</h1><p>The message and link were part of a security-awareness exercise. This is not an account-compromise alert.</p><section><p><strong>Campaign:</strong> {campaign}</p><p class="rank">{rank}</p><p>Your link visit has been recorded. The service processes an automatic educational notice; delivery status is available to the administrator.</p></section><h2>What to look for next time</h2><ul><li>Be cautious with unexpected shared documents.</li><li>Check the sender address and the actual link destination.</li><li>Confirm unexpected or urgent requests through a known channel.</li><li>Report suspicious messages to your school IT contact.</li></ul><p>No passwords or verification codes are requested or collected here.</p><small>Order counts distinct links, not verified people, within the same campaign name and administrator. Repeat visits keep the original number. Older first visits are excluded. Security scanners and forwarded links can trigger records, so this is not proof that you personally clicked.</small></html>''')

def deliver(token):
 item=table.get_item(Key={'token':token},ConsistentRead=True).get('Item',{})
 if item.get('notice_state') not in ('pending','awaiting_verification'):return
 if not recipient_allowed(item.get('email')):
  table.update_item(Key={'token':token},UpdateExpression='SET notice_state=:s',ExpressionAttributeValues={':s':'suppressed'});return
 if item.get('disabled'):
  table.update_item(Key={'token':token},UpdateExpression='SET notice_state=:s',ExpressionAttributeValues={':s':'suppressed'});return
 if int(item.get('attempts',0))>=5:
  table.update_item(Key={'token':token},UpdateExpression='SET notice_state=:s',ExpressionAttributeValues={':s':'failed'});return
 now=int(time.time())
 try:
  table.update_item(Key={'token':token},UpdateExpression='SET notice_state=:s,last_attempt=:n ADD attempts :one',ConditionExpression='notice_state=:p OR notice_state=:v',ExpressionAttributeValues={':s':'sending',':p':'pending',':v':'awaiting_verification',':n':now,':one':1})
 except ClientError as e:
  if e.response['Error']['Code']=='ConditionalCheckFailedException':return
  raise
 date=datetime.fromtimestamp(int(item['first_visit']),timezone.utc).isoformat()
 try:
  body=(f'The message was a simulated phishing email for a security-awareness exercise. This is not an account-compromise alert.\n\n'
        f'Campaign: {item["campaign"]}\nFirst recorded visit (UTC): {date}\n\n'
        +rank_message(item)+'\n\n'
        'Order counts distinct links, not verified people, for the same campaign name and administrator. Repeat visits do not change the number. First visits before ranking was enabled are excluded.\n\n'
        'This notice is sent automatically by the AWS service, normally once per link. No passwords or verification codes were requested or collected. Security scanners and forwarded links may trigger visits; this record alone does not establish who clicked.\n\n'
        'Be cautious with unexpected shared documents. Check the sender address and the actual link destination, verify unexpected or urgent requests through a known channel, and report suspicious messages to school IT.\n\n'
        'To keep the exercise results representative, please DO NOT share this message, the exercise details or your link with other participants until the exercise ends. You may still report concerns to school IT or the exercise coordinator.')
  result=send_email(token,Source=os.environ['SENDER'],Destination={'ToAddresses':[item['email']]},Message={'Subject':{'Data':'[Security awareness] Your exercise link was visited','Charset':'UTF-8'},'Body':{'Text':{'Data':body,'Charset':'UTF-8'},'Html':{'Data':email_html(body).replace('DO NOT','<strong>DO NOT</strong>'),'Charset':'UTF-8'}}})
 except ResendError as e:
  state='pending' if e.status in (408,409,429) or e.status>=500 else 'failed'
  table.update_item(Key={'token':token},UpdateExpression='SET notice_state=:s,last_error=:e',ExpressionAttributeValues={':s':state,':e':'Resend HTTP '+str(e.status)+' '+e.name})
  if state=='pending':raise
  return
 except ClientError as e:
  code=e.response['Error']['Code']
  print('SES rejection:',code,e.response['Error'].get('Message','')[:1500])
  if code=='MessageRejected' and 'not verified' in e.response['Error'].get('Message','').lower():
   table.update_item(Key={'token':token},UpdateExpression='SET notice_state=:s,last_error=:e,attempts=:z',ExpressionAttributeValues={':s':'awaiting_verification',':e':'Recipient verification required',':z':0});return
  if code in ('MessageRejected','MailFromDomainNotVerifiedException','Throttling','ThrottlingException','AccessDenied','AccessDeniedException','AccountSendingPausedException'):
   table.update_item(Key={'token':token},UpdateExpression='SET notice_state=:s,last_error=:e',ExpressionAttributeValues={':s':'pending',':e':code})
   raise
  table.update_item(Key={'token':token},UpdateExpression='SET notice_state=:s,last_error=:e',ExpressionAttributeValues={':s':'uncertain',':e':code});return
 except Exception as e:
  # SES has no idempotency key: never automatically retry ambiguous delivery.
  table.update_item(Key={'token':token},UpdateExpression='SET notice_state=:s,last_error=:e',ExpressionAttributeValues={':s':'uncertain',':e':type(e).__name__});return
 # If the following write fails, leave sending; recovery marks it uncertain, not pending.
 table.update_item(Key={'token':token},UpdateExpression='SET notice_state=:s,provider_message_id=:i,mail_provider=:p,sent_at=:n REMOVE last_error',ExpressionAttributeValues={':s':'sent',':i':result['MessageId'],':p':result.get('Provider','ses'),':n':int(time.time())})

def email_html(text):
 # User-authored body remains text, never trusted HTML.
 return '<!doctype html><html lang="en"><meta charset="utf-8"><body><div style="font:16px/1.6 Arial,sans-serif;color:#171717">'+html.escape(text).replace('\n','<br>')+'</div></body></html>'

def initial_body(item,url):
 raw=item['body'].replace('{{expire_days}}',str(max(1,(int(item['expires_at'])-int(item['created_at']))//86400)))
 plain=raw.replace('{{link}}',url)
 # Collapse the default text label and placeholder into one descriptive anchor.
 presentation=raw.replace('View shared document:\n{{link}}','{{link}}')
 markup=email_html(presentation).replace('{{link}}','<a href="'+html.escape(url,quote=True)+'">View shared document</a>')
 return {'Text':{'Data':plain,'Charset':'UTF-8'},'Html':{'Data':markup,'Charset':'UTF-8'}}

def deliver_initial(token):
 item=table.get_item(Key={'token':token},ConsistentRead=True).get('Item',{})
 if item.get('initial_state')!='queued':return
 if not recipient_allowed(item.get('email')) or not item.get('authorization_confirmed'):
  table.update_item(Key={'token':token},UpdateExpression='SET initial_state=:s',ExpressionAttributeValues={':s':'cancelled'});return
 if item.get('disabled') or int(item.get('expires_at',0))<int(time.time()):
  table.update_item(Key={'token':token},UpdateExpression='SET initial_state=:s',ExpressionAttributeValues={':s':'cancelled'});return
 if int(item.get('initial_attempts',0))>=5:
  table.update_item(Key={'token':token},UpdateExpression='SET initial_state=:s',ExpressionAttributeValues={':s':'failed'});return
 try:
  table.update_item(Key={'token':token},UpdateExpression='SET initial_state=:s,initial_last_attempt=:n ADD initial_attempts :one',ConditionExpression='initial_state=:q',ExpressionAttributeValues={':s':'sending',':q':'queued',':n':int(time.time()),':one':1})
 except ClientError as e:
  if e.response['Error']['Code']=='ConditionalCheckFailedException':return
  raise
 url=os.environ['PUBLIC_BASE_URL']+'/t/'+token
 body=initial_body(item,url)
 try:
  result=send_email('initial/'+token,Source=os.environ['SENDER'],Destination={'ToAddresses':[item['email']]},Message={'Subject':{'Data':item['subject']},'Body':body})
 except ResendError as e:
  state='queued' if e.status in (408,409,429) or e.status>=500 else 'failed'
  table.update_item(Key={'token':token},UpdateExpression='SET initial_state=:s,initial_error=:e',ExpressionAttributeValues={':s':state,':e':'Resend HTTP '+str(e.status)+' '+e.name})
  if state=='queued':raise
  return
 except Exception as e:
  table.update_item(Key={'token':token},UpdateExpression='SET initial_state=:s,initial_error=:e',ExpressionAttributeValues={':s':'uncertain',':e':type(e).__name__});return
 table.update_item(Key={'token':token},UpdateExpression='SET initial_state=:s,initial_message_id=:i,initial_sent_at=:n REMOVE initial_error',ExpressionAttributeValues={':s':'sent',':i':result['MessageId'],':n':int(time.time())})

def worker(event,context):
 failures=[]
 for r in event.get('Records',[]):
  try:
   job=json.loads(r['body'])
   if job.get('kind')=='initial':deliver_initial(job['token'])
   else:deliver(job['token'])
  except Exception:failures.append({'itemIdentifier':r['messageId']})
 return {'batchItemFailures':failures}

def recover(event,context):
 last=None;count=0;now=int(time.time())
 while True:
  kw={'FilterExpression':Attr('notice_state').is_in(['pending','awaiting_verification','sending']) | Attr('initial_state').is_in(['queued','sending'])}
  if last:kw['ExclusiveStartKey']=last
  resp=table.scan(**kw)
  for item in resp['Items']:
   if item.get('initial_state')=='queued':
    sqs.send_message(QueueUrl=os.environ['QUEUE_URL'],MessageBody=json.dumps({'token':item['token'],'kind':'initial'}))
   elif item.get('initial_state')=='sending' and int(item.get('initial_last_attempt',now))+600<now:
    table.update_item(Key={'token':item['token']},UpdateExpression='SET initial_state=:s',ConditionExpression='initial_state=:p AND initial_last_attempt=:n',ExpressionAttributeValues={':s':'uncertain',':p':'sending',':n':item['initial_last_attempt']})
   if item['notice_state'] in ('pending','awaiting_verification') and int(item.get('attempts',0))<5:enqueue(item['token']);count+=1
   elif item['notice_state']=='pending':
    table.update_item(Key={'token':item['token']},UpdateExpression='SET notice_state=:s',ConditionExpression='notice_state=:p',ExpressionAttributeValues={':s':'failed',':p':'pending'})
   elif int(item.get('last_attempt',now))+600<now:
    table.update_item(Key={'token':item['token']},UpdateExpression='SET notice_state=:s',ConditionExpression='notice_state=:p AND last_attempt=:n',ExpressionAttributeValues={':s':'uncertain',':p':'sending',':n':item['last_attempt']})
  last=resp.get('LastEvaluatedKey')
  if not last:break
 return {'requeued':count}
