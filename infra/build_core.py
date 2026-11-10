import json
from pathlib import Path
B=Path(__file__).resolve().parents[1]
BUILD=B/'build'
BUILD.mkdir(exist_ok=True)
code=(B/'backend/worker.py').read_text()
ref=lambda x:{'Ref':x}
arn=lambda x:{'Fn::GetAtt':[x,'Arn']}
sub=lambda x:{'Fn::Sub':x}
r={}
r['Records']={'Type':'AWS::DynamoDB::Table','DeletionPolicy':'Retain','UpdateReplacePolicy':'Retain','Properties':{'BillingMode':'PAY_PER_REQUEST','OnDemandThroughput':{'MaxReadRequestUnits':10,'MaxWriteRequestUnits':10},'AttributeDefinitions':[{'AttributeName':'token','AttributeType':'S'}],'KeySchema':[{'AttributeName':'token','KeyType':'HASH'}],'TimeToLiveSpecification':{'AttributeName':'ttl','Enabled':True},'SSESpecification':{'SSEEnabled':True},'PointInTimeRecoverySpecification':{'PointInTimeRecoveryEnabled':False}}}
r['DeadLetters']={'Type':'AWS::SQS::Queue','Properties':{'MessageRetentionPeriod':1209600,'SqsManagedSseEnabled':True}}
r['Notices']={'Type':'AWS::SQS::Queue','Properties':{'VisibilityTimeout':180,'MessageRetentionPeriod':1209600,'SqsManagedSseEnabled':True,'RedrivePolicy':{'deadLetterTargetArn':arn('DeadLetters'),'maxReceiveCount':5}}}
assume={'Version':'2012-10-17','Statement':[{'Effect':'Allow','Principal':{'Service':'lambda.amazonaws.com'},'Action':'sts:AssumeRole'}]}
logpolicy={'Effect':'Allow','Action':['logs:CreateLogStream','logs:PutLogEvents'],'Resource':sub('arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/${AWS::StackName}-*:log-stream:*')}
def role(name,stmts):
 r[name]={'Type':'AWS::IAM::Role','Properties':{'AssumeRolePolicyDocument':assume,'Policies':[{'PolicyName':'AwarenessOnly','PolicyDocument':{'Version':'2012-10-17','Statement':[logpolicy]+stmts}}]}}
role('TrackRole',[{'Effect':'Allow','Action':['dynamodb:GetItem','dynamodb:UpdateItem','dynamodb:PutItem'],'Resource':arn('Records')},{'Effect':'Allow','Action':'sqs:SendMessage','Resource':arn('Notices')}])
role('WorkerRole',[{'Effect':'Allow','Action':['dynamodb:GetItem','dynamodb:UpdateItem'],'Resource':arn('Records')},{'Effect':'Allow','Action':['sqs:ReceiveMessage','sqs:DeleteMessage','sqs:GetQueueAttributes'],'Resource':arn('Notices')},{'Effect':'Allow','Action':'secretsmanager:GetSecretValue','Resource':ref('ResendSecretArn')}])
role('RecoverRole',[{'Effect':'Allow','Action':['dynamodb:Scan','dynamodb:UpdateItem'],'Resource':arn('Records')},{'Effect':'Allow','Action':'sqs:SendMessage','Resource':arn('Notices')}])
for name,handler,rol,conc in [('Track','track','TrackRole',2),('Worker','worker','WorkerRole',2),('Recover','recover','RecoverRole',1)]:
 r[name+'Logs']={'Type':'AWS::Logs::LogGroup','Properties':{'LogGroupName':sub('${AWS::StackName}-unused') if False else sub('/aws/lambda/${AWS::StackName}-'+name.lower()),'RetentionInDays':7}}
 r[name]={'Type':'AWS::Lambda::Function','DependsOn':name+'Logs','Properties':{'FunctionName':sub('${AWS::StackName}-'+name.lower()),'Runtime':'python3.13','Architectures':['arm64'],'MemorySize':128,'Timeout':30,'Role':arn(rol),'Handler':'index.'+handler,'Code':{'ZipFile':code},'Environment':{'Variables':{'TABLE_NAME':ref('Records'),'QUEUE_URL':ref('Notices'),'SENDER':ref('Sender'),'ALLOWED_RECIPIENT':ref('Recipient')}}}}
r['Worker']['Properties']['Environment']['Variables'].update(EMAIL_PROVIDER='resend',RESEND_SECRET_ARN=ref('ResendSecretArn'),PUBLIC_BASE_URL={'Fn::GetAtt':['Api','ApiEndpoint']})
r['WorkerMapping']={'Type':'AWS::Lambda::EventSourceMapping','Properties':{'EventSourceArn':arn('Notices'),'FunctionName':ref('Worker'),'BatchSize':1,'FunctionResponseTypes':['ReportBatchItemFailures'],'ScalingConfig':{'MaximumConcurrency':2}}}
r['Schedule']={'Type':'AWS::Events::Rule','Properties':{'ScheduleExpression':'rate(5 minutes)','State':'ENABLED','Targets':[{'Arn':arn('Recover'),'Id':'Recovery'}]}}
r['ScheduleInvoke']={'Type':'AWS::Lambda::Permission','Properties':{'Action':'lambda:InvokeFunction','FunctionName':ref('Recover'),'Principal':'events.amazonaws.com','SourceArn':arn('Schedule')}}
r['Api']={'Type':'AWS::ApiGatewayV2::Api','Properties':{'Name':sub('${AWS::StackName}-links'),'ProtocolType':'HTTP'}}
r['Integration']={'Type':'AWS::ApiGatewayV2::Integration','Properties':{'ApiId':ref('Api'),'IntegrationType':'AWS_PROXY','IntegrationUri':arn('Track'),'PayloadFormatVersion':'2.0','TimeoutInMillis':10000}}
r['Route']={'Type':'AWS::ApiGatewayV2::Route','Properties':{'ApiId':ref('Api'),'RouteKey':'GET /t/{token}','Target':{'Fn::Join':['',['integrations/',ref('Integration')]]}}}
r['Stage']={'Type':'AWS::ApiGatewayV2::Stage','Properties':{'ApiId':ref('Api'),'StageName':'$default','AutoDeploy':True,'DefaultRouteSettings':{'ThrottlingBurstLimit':5,'ThrottlingRateLimit':2}}}
r['ApiInvoke']={'Type':'AWS::Lambda::Permission','Properties':{'Action':'lambda:InvokeFunction','FunctionName':ref('Track'),'Principal':'apigateway.amazonaws.com','SourceArn':sub('arn:${AWS::Partition}:execute-api:${AWS::Region}:${AWS::AccountId}:${Api}/*/GET/t/*')}}
r['QueueAlarm']={'Type':'AWS::CloudWatch::Alarm','Properties':{'AlarmDescription':'Awareness: notification failures in DLQ; inspect queue and records','Namespace':'AWS/SQS','MetricName':'ApproximateNumberOfMessagesVisible','Dimensions':[{'Name':'QueueName','Value':{'Fn::GetAtt':['DeadLetters','QueueName']}}],'Statistic':'Maximum','Period':300,'EvaluationPeriods':1,'Threshold':1,'ComparisonOperator':'GreaterThanOrEqualToThreshold','TreatMissingData':'notBreaching'}}
t={'AWSTemplateFormatVersion':'2010-09-09','Description':'Isolated self-test awareness link tracking with persistent records and automatic educational notice; no existing server changes.','Parameters':{'ResendSecretArn':{'Type':'String'},'SenderIdentity':{'Type':'String','Default':'example.com'},'Sender':{'Type':'String','Default':'noreply@example.com'},'Recipient':{'Type':'String','Default':'recipient@example.com'}},'Resources':r,'Outputs':{'BaseUrl':{'Value':{'Fn::GetAtt':['Api','ApiEndpoint']}},'TableName':{'Value':ref('Records')},'QueueUrl':{'Value':ref('Notices')},'DeadLetterQueueUrl':{'Value':ref('DeadLetters')},'WorkerName':{'Value':ref('Worker')},'RecoverName':{'Value':ref('Recover')}}}
(BUILD/'core.json').write_text(json.dumps(t,ensure_ascii=False,separators=(',',':')))
print('Template size', (BUILD/'core.json').stat().st_size)
