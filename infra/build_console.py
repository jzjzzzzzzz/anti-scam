import json,zipfile,hashlib,shutil
from pathlib import Path
B=Path(__file__).resolve().parents[1]
BUILD=B/'build'
BUILD.mkdir(exist_ok=True)
D=json.loads((BUILD/'core-outputs.json').read_text())
ref=lambda x:{'Ref':x};arn=lambda x:{'Fn::GetAtt':[x,'Arn']};sub=lambda x:{'Fn::Sub':x}
api=D['BaseUrl'].split('//')[1].split('.')[0];base=D['BaseUrl'];table=D['TableName'];queue=D['QueueUrl'];account=queue.split('/')[3]
R={}
R['UserPool']={'Type':'AWS::Cognito::UserPool','DeletionPolicy':'Retain','UpdateReplacePolicy':'Retain','Properties':{'UserPoolName':'anti-scam-console','UserPoolTier':'ESSENTIALS','AdminCreateUserConfig':{'AllowAdminCreateUserOnly':True},'UsernameAttributes':['email'],'AutoVerifiedAttributes':['email'],'UsernameConfiguration':{'CaseSensitive':False},'Policies':{'PasswordPolicy':{'MinimumLength':14,'RequireLowercase':True,'RequireUppercase':True,'RequireNumbers':True,'RequireSymbols':True,'TemporaryPasswordValidityDays':7}},'AccountRecoverySetting':{'RecoveryMechanisms':[{'Name':'verified_email','Priority':1}]},'MfaConfiguration':'OPTIONAL','EnabledMfas':['SOFTWARE_TOKEN_MFA']}}
R['Client']={'Type':'AWS::Cognito::UserPoolClient','Properties':{'UserPoolId':ref('UserPool'),'ClientName':'anti-scam-console-web','GenerateSecret':False,'AllowedOAuthFlowsUserPoolClient':True,'AllowedOAuthFlows':['code'],'AllowedOAuthScopes':['openid','email','profile'],'CallbackURLs':[base+'/console'],'LogoutURLs':[base+'/console'],'SupportedIdentityProviders':['COGNITO'],'ExplicitAuthFlows':['ALLOW_USER_PASSWORD_AUTH','ALLOW_REFRESH_TOKEN_AUTH','ALLOW_USER_SRP_AUTH'],'PreventUserExistenceErrors':'ENABLED','EnableTokenRevocation':True,'AccessTokenValidity':30,'IdTokenValidity':30,'RefreshTokenValidity':1,'TokenValidityUnits':{'AccessToken':'minutes','IdToken':'minutes','RefreshToken':'days'}}}
prefix='anti-scam-'+api+'-'+account
R['Domain']={'Type':'AWS::Cognito::UserPoolDomain','Properties':{'Domain':prefix,'UserPoolId':ref('UserPool'),'ManagedLoginVersion':2}}
R['ManagedBranding']={'Type':'AWS::Cognito::ManagedLoginBranding','Properties':{'UserPoolId':ref('UserPool'),'ClientId':ref('Client'),'UseCognitoProvidedValues':True}}
R['Domain']['DependsOn']='ManagedBranding'
R['Operators']={'Type':'AWS::Cognito::UserPoolGroup','Properties':{'UserPoolId':ref('UserPool'),'GroupName':'operators','Description':'Invited console administrators'}}
assume={'Version':'2012-10-17','Statement':[{'Effect':'Allow','Principal':{'Service':'lambda.amazonaws.com'},'Action':'sts:AssumeRole'}]}
for n in ['Public','Admin']:
 stmts=[{'Effect':'Allow','Action':['logs:CreateLogStream','logs:PutLogEvents'],'Resource':sub('arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/${AWS::StackName}-*:log-stream:*')}]
 if n=='Admin':stmts += [{'Effect':'Allow','Action':['dynamodb:GetItem','dynamodb:Scan','dynamodb:PutItem','dynamodb:UpdateItem'],'Resource':f'arn:aws:dynamodb:us-east-1:{account}:table/{table}'},{'Effect':'Allow','Action':'sqs:SendMessage','Resource':f'arn:aws:sqs:us-east-1:{account}:{queue.rsplit("/",1)[1]}'}]
 R[n+'Role']={'Type':'AWS::IAM::Role','Properties':{'AssumeRolePolicyDocument':assume,'Policies':[{'PolicyName':'ConsoleBoundedAccess','PolicyDocument':{'Version':'2012-10-17','Statement':stmts}}]}}
 R[n+'Logs']={'Type':'AWS::Logs::LogGroup','Properties':{'LogGroupName':sub('/aws/lambda/${AWS::StackName}-'+n.lower()),'RetentionInDays':7}}
 R[n]={'Type':'AWS::Lambda::Function','DependsOn':n+'Logs','Properties':{'FunctionName':sub('${AWS::StackName}-'+n.lower()),'Runtime':'python3.13','Architectures':['arm64'],'MemorySize':256,'Timeout':20,'Role':arn(n+'Role'),'Handler':'console.'+n.lower(),'Code':{'S3Bucket':ref('CodeBucket'),'S3Key':ref('CodeKey')},'Environment':{'Variables':{'TABLE_NAME':table,'QUEUE_URL':queue,'BASE_URL':base,'SENDER':ref('Sender'),'ALLOWED_RECIPIENT':ref('Recipient'),'CLIENT_ID':ref('Client'),'AUTH_DOMAIN':f'https://{prefix}.auth.us-east-1.amazoncognito.com'}}}}
 R[n+'Integration']={'Type':'AWS::ApiGatewayV2::Integration','Properties':{'ApiId':api,'IntegrationType':'AWS_PROXY','IntegrationUri':arn(n),'PayloadFormatVersion':'2.0','TimeoutInMillis':20000}}
 R[n+'Invoke']={'Type':'AWS::Lambda::Permission','Properties':{'Action':'lambda:InvokeFunction','FunctionName':ref(n),'Principal':'apigateway.amazonaws.com','SourceArn':f'arn:aws:execute-api:us-east-1:{account}:{api}/*'}}
R['Authorizer']={'Type':'AWS::ApiGatewayV2::Authorizer','Properties':{'ApiId':api,'AuthorizerType':'JWT','Name':'beacon-cognito','IdentitySource':['$request.header.Authorization'],'JwtConfiguration':{'Issuer':sub('https://cognito-idp.${AWS::Region}.amazonaws.com/${UserPool}'),'Audience':[ref('Client')]}}}
for i,route in enumerate(['GET /console','GET /console/config','GET /console-assets/{proxy+}']):
 R['PublicRoute'+str(i)]={'Type':'AWS::ApiGatewayV2::Route','Properties':{'ApiId':api,'RouteKey':route,'Target':{'Fn::Join':['',['integrations/',ref('PublicIntegration')]]}}}
R['AdminRoute']={'Type':'AWS::ApiGatewayV2::Route','Properties':{'ApiId':api,'RouteKey':'ANY /admin/{proxy+}','Target':{'Fn::Join':['',['integrations/',ref('AdminIntegration')]]},'AuthorizationType':'JWT','AuthorizerId':ref('Authorizer')}}
t={'AWSTemplateFormatVersion':'2010-09-09','Description':'Beacon: invited-admin authenticated console on existing awareness API; no public admin data, no mail credentials in browser.','Parameters':{'Sender':{'Type':'String'},'Recipient':{'Type':'String'},'CodeBucket':{'Type':'String'},'CodeKey':{'Type':'String'}},'Resources':R,'Outputs':{'ConsoleUrl':{'Value':base+'/console'},'UserPoolId':{'Value':ref('UserPool')},'ClientId':{'Value':ref('Client')},'AuthDomain':{'Value':f'https://{prefix}.auth.us-east-1.amazoncognito.com'}}}
(BUILD/'console.json').write_text(json.dumps(t,ensure_ascii=False,indent=2))
with zipfile.ZipFile(BUILD/'console.zip','w',zipfile.ZIP_DEFLATED) as z:
 z.write(B/'backend/console.py','console.py')
 for f in (B/'frontend/dist').glob('*'):
  if f.is_file():z.write(f,'web/'+f.name)
print('Console package',hashlib.sha256((BUILD/'console.zip').read_bytes()).hexdigest())
