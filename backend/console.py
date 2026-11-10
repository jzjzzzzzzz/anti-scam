import os,json,time,secrets,base64,mimetypes,hashlib,re
from pathlib import Path
from decimal import Decimal
import boto3
from botocore.exceptions import ClientError
T=boto3.resource('dynamodb').Table(os.environ['TABLE_NAME'])
Q=boto3.client('sqs')
ROOT=Path(__file__).parent/'web'
ALLOWED=os.environ['ALLOWED_RECIPIENT']

def out(status,data,mime='application/json; charset=utf-8'):
 body=json.dumps(data,ensure_ascii=False,default=lambda v:int(v) if isinstance(v,Decimal) else str(v)) if mime.startswith('application/json') else data
 return {'statusCode':status,'headers':{'content-type':mime,'cache-control':'no-store','x-content-type-options':'nosniff','referrer-policy':'no-referrer','content-security-policy':"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self' https://*.amazoncognito.com; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://*.amazoncognito.com"},'body':body}

def public(event,context):
 path=event.get('rawPath','')
 if path=='/console/config':
  return out(200,{'clientId':os.environ['CLIENT_ID'],'authDomain':os.environ['AUTH_DOMAIN'],'callback':os.environ['BASE_URL']+'/console'})
 if path in ('/console','/console/'):
  return out(200,(ROOT/'index.html').read_text(),'text/html; charset=utf-8')
 if path.startswith('/console-assets/'):
  name=path[len('/console-assets/'):]
  if '/' in name or '..' in name:return out(404,{'error':'Not found'})
  f=ROOT/name
  if f.is_file():
   mime=mimetypes.guess_type(name)[0] or 'application/octet-stream'
   if mime in ('text/javascript','application/javascript','text/css'):return out(200,f.read_text(),mime+'; charset=utf-8')
 return out(404,{'error':'Not found'})

def get_item(token):return T.get_item(Key={'token':token},ConsistentRead=True).get('Item')

def recipient_id(email):return 'recipient#'+hashlib.sha256(email.strip().lower().encode()).hexdigest()
def normalize_email(value):
 if not isinstance(value,str):raise ValueError('email')
 email=value.strip().lower()
 if len(email)>254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+",email):raise ValueError('email')
 return email

def recipient_allowed(email):
 row=get_item(recipient_id(email))
 if row is None:return email==ALLOWED
 return row.get('record_type')=='recipient' and row.get('enabled') is True and row.get('authorization_confirmed') is True

def recipient_list(rows):
 result=[r for r in rows if r.get('record_type')=='recipient']
 if not any(r.get('email')==ALLOWED for r in result):result.append({'token':recipient_id(ALLOWED),'record_type':'recipient','email':ALLOWED,'label':'原学校邮箱','system_default':True,'enabled':True,'authorization_confirmed':True,'created_at':0})
 return sorted(result,key=lambda r:(not r.get('enabled'),r.get('email','')))

def admin(event,context):
 claims=event.get('requestContext',{}).get('authorizer',{}).get('jwt',{}).get('claims',{})
 groups=claims.get('cognito:groups','')
 if 'operators' not in (groups if isinstance(groups,list) else groups.replace('[','').replace(']','').replace('"','').split(',')):return out(403,{'error':'需要管理员权限'})
 if claims.get('token_use')!='access':return out(403,{'error':'需要 access token'})
 path=event.get('rawPath','');method=event['requestContext']['http']['method']
 try:
  if method=='GET' and path=='/admin/dashboard':
   rows=[];cursor=None
   for _ in range(10):
    kw={'Limit':250}
    if cursor:kw['ExclusiveStartKey']=cursor
    r=T.scan(**kw);rows.extend(r['Items']);cursor=r.get('LastEvaluatedKey')
    if not cursor:break
   recipients=recipient_list(rows)
   campaigns=[r for r in rows if r.get('record_type') in (None,'link')];events=sorted([r for r in rows if r.get('record_type')=='event'],key=lambda r:r.get('visited_at',0),reverse=True)[:200]
   campaigns.sort(key=lambda r:r.get('created_at',r.get('first_visit',0)),reverse=True)
   for r in campaigns:
    r['url']=os.environ['BASE_URL']+'/t/'+r['token']
   return out(200,{'campaigns':campaigns,'events':events,'truncated':bool(cursor),'sender':os.environ['SENDER'],'recipient':ALLOWED,'recipients':recipients,'provider':'resend','user':claims.get('username','管理员')})
  if method=='POST' and path=='/admin/recipients':
   raw=event.get('body') or '{}'
   if event.get('isBase64Encoded'):raw=base64.b64decode(raw).decode()
   if len(raw)>4000:return out(413,{'error':'内容过长'})
   data=json.loads(raw);email=normalize_email(data.get('email'));label=str(data.get('label','')).strip()
   if len(label)>80:return out(400,{'error':'备注过长'})
   if data.get('consent') is not True:return out(400,{'error':'请确认收件人已同意参与或属于已批准的演练范围'})
   token=recipient_id(email);now=int(time.time())
   if get_item(token) is not None:return out(409,{'error':'该邮箱已存在，请使用启用/停用操作'})
   T.put_item(Item={'token':token,'record_type':'recipient','email':email,'label':label,'enabled':True,'authorization_confirmed':True,'authorized_by':claims['sub'],'created_at':now,'updated_at':now},ConditionExpression='attribute_not_exists(#t)',ExpressionAttributeNames={'#t':'token'})
   return out(201,{'message':'收件人已添加，尚未发送任何邮件'})
  if method=='POST' and path=='/admin/recipients/status':
   raw=event.get('body') or '{}'
   if event.get('isBase64Encoded'):raw=base64.b64decode(raw).decode()
   if len(raw)>4000:return out(413,{'error':'内容过长'})
   data=json.loads(raw);email=normalize_email(data.get('email'));enabled=data.get('enabled')
   if not isinstance(enabled,bool):return out(400,{'error':'状态格式错误'})
   if enabled and data.get('consent') is not True:return out(400,{'error':'启用前需要确认授权'})
   token=recipient_id(email);row=get_item(token)
   if row is None and email!=ALLOWED:return out(404,{'error':'未找到收件人'})
   T.update_item(Key={'token':token},UpdateExpression='SET record_type=:r,email=:e,enabled=:v,authorization_confirmed=:a,updated_at=:n,authorized_by=:u',ExpressionAttributeValues={':r':'recipient',':e':email,':v':enabled,':a':True,':n':int(time.time()),':u':claims['sub']})
   return out(200,{'message':'收件人已启用' if enabled else '收件人已停用；后续发信、提醒与链接访问将被阻止，已在途的发送可能完成'})
  if method=='POST' and path=='/admin/campaigns':
   raw=event.get('body') or '{}'
   if event.get('isBase64Encoded'):raw=base64.b64decode(raw).decode()
   if len(raw)>24000:return out(413,{'error':'内容过长'})
   data=json.loads(raw)
   name=str(data.get('name','')).strip();subject=str(data.get('subject','')).strip();body=str(data.get('body','')).strip();days=int(data.get('days',30))
   if not(1<=len(name)<=100 and 1<=len(subject)<=180 and 1<=len(body)<=10000 and 1<=days<=90):return out(400,{'error':'请检查名称、主题、正文或有效期'})
   if any(c in subject for c in '\r\n'):return out(400,{'error':'主题不能含换行'})
   if '{{link}}' not in body:return out(400,{'error':'正文必须包含 {{link}}'})
   if data.get('consent') is not True:return out(400,{'error':'请确认本次为授权演练'})
   email=normalize_email(data.get('email',ALLOWED))
   if not recipient_allowed(email):return out(400,{'error':'收件人尚未添加或已停用'})
   token=secrets.token_urlsafe(32);now=int(time.time())
   row={'token':token,'record_type':'link','campaign':name,'email':email,'subject':subject,'body':body,'created_at':now,'expires_at':now+days*86400,'ttl':now+90*86400,'notice_state':'armed','initial_state':'draft','visits':0,'disabled':True,'authorized_by':claims['sub'],'authorization_confirmed':True}
   T.put_item(Item=row,ConditionExpression='attribute_not_exists(#t)',ExpressionAttributeNames={'#t':'token'})
   return out(201,{'token':token,'message':'草稿已创建，尚未发信'})
  if method=='POST' and path.startswith('/admin/campaigns/'):
   parts=path.split('/');token=parts[3] if len(parts)==5 else '';action=parts[-1]
   row=get_item(token)
   if not row:return out(404,{'error':'未找到演练'})
   if action=='send':
    if not row.get('authorization_confirmed') or not recipient_allowed(row.get('email','')) or not row.get('subject'):return out(400,{'error':'此历史记录不能从控制台再次发送'})
    if row.get('initial_state')!='draft':return out(409,{'error':'此演练已入队或发送，不能重复发送'})
    if int(row['expires_at'])<int(time.time()):return out(400,{'error':'链接已过期，请创建新演练'})
    T.update_item(Key={'token':token},UpdateExpression='SET initial_state=:q,disabled=:f,initial_attempts=:z',ConditionExpression='initial_state=:d',ExpressionAttributeValues={':q':'queued',':f':False,':z':0,':d':'draft'})
    try:Q.send_message(QueueUrl=os.environ['QUEUE_URL'],MessageBody=json.dumps({'token':token,'kind':'initial'}))
    except Exception:pass # recover() also enqueues queued initial messages.
    return out(202,{'message':'已加入发信队列，请刷新查看实际发送状态'})
   if action=='pause':
    T.update_item(Key={'token':token},UpdateExpression='SET disabled=:v',ExpressionAttributeValues={':v':True})
    return out(200,{'message':'链接已暂停；正在进行的发送可能已经完成'})
  return out(404,{'error':'Not found'})
 except (ValueError,TypeError,json.JSONDecodeError):return out(400,{'error':'输入格式错误'})
 except ClientError as e:
  if e.response['Error']['Code']=='ConditionalCheckFailedException':return out(409,{'error':'状态已变化，请刷新后重试'})
  print('admin aws error',e.response['Error']['Code']);return out(503,{'error':'后台服务暂不可用，请稍后重试'})
