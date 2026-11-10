# Isolated AWS installation

These are source-build examples, not an instruction to alter an existing school
service. Do not point them at a production stack without a separate review.
Nothing in the local test runner sends email or deploys infrastructure.

## Requirements and review

- AWS CLI credentials under your control, Node.js 22+, Python 3.11+.
- The included examples currently target `us-east-1`.
- A private S3 artifacts bucket with public access blocked and encryption enabled.
- A verified Resend sending domain with SPF, DKIM and DMARC checked on received mail.
- A Secrets Manager secret containing JSON `{"RESEND_API_KEY":"<your key>"}`.
- Written authorization and a designated initial test recipient. The core
  `Recipient` parameter is a bootstrap recipient permitted before a directory row
  exists; set it only to an approved address. Adding/disabling directory entries
  subsequently takes precedence.

Confirm costs before deploying. Resources include DynamoDB, SQS, Lambda, API
Gateway, CloudWatch, EventBridge, Secrets Manager and Cognito Essentials. Email
provider costs and delivery restrictions apply independently.

## Build source artifacts

From the repository root:

```sh
python3 scripts/test.py
npm ci --prefix frontend
npm run test:i18n --prefix frontend
npm run build --prefix frontend
python3 infra/build_core.py
```

`build/core.json` contains inline Lambda source and can exceed CloudFormation's
direct request size. Use your private S3 bucket when deploying:

```sh
export AWS_DEFAULT_REGION=us-east-1
export ARTIFACT_BUCKET='<your-private-artifacts-bucket>'
export SENDER='noreply@example.com'
export RECIPIENT='recipient@example.com'
export RESEND_SECRET_ARN='<your-secret-arn>'

aws cloudformation deploy \
  --stack-name anti-scam-core \
  --template-file build/core.json \
  --s3-bucket "$ARTIFACT_BUCKET" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides Sender="$SENDER" Recipient="$RECIPIENT" \
    SenderIdentity="${SENDER#*@}" ResendSecretArn="$RESEND_SECRET_ARN"

aws cloudformation describe-stacks --stack-name anti-scam-core \
  --query 'Stacks[0].Outputs' --output json > build/core-outputs-list.json

python3 - <<'PYCODE'
import json
from pathlib import Path
rows=json.loads(Path('build/core-outputs-list.json').read_text())
Path('build/core-outputs.json').write_text(json.dumps({r['OutputKey']:r['OutputValue'] for r in rows}))
PYCODE

python3 infra/build_console.py
aws s3 cp build/console.zip "s3://$ARTIFACT_BUCKET/releases/console.zip" --sse AES256
aws cloudformation deploy \
  --stack-name anti-scam-console \
  --template-file build/console.json \
  --s3-bucket "$ARTIFACT_BUCKET" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides CodeBucket="$ARTIFACT_BUCKET" CodeKey=releases/console.zip \
    Sender="$SENDER" Recipient="$RECIPIENT"
```

For later releases use a **new immutable S3 key** (for example, a source hash) and
update `CodeKey` accordingly so CloudFormation notices code changes. The template
builder produces artifacts; it does not update live resources itself.

## Invited operator

Read `UserPoolId` and `ConsoleUrl` from your console stack outputs. Use Cognito to
invite the approved operator and add that user to the `operators` group. Public
self-registration is disabled. The operator sets their own password and can enroll
TOTP; never put their password in repository configuration. The example pool has
optional MFA; review whether mandatory MFA is required for your installation.

Visit the console only after verifying sign-in and unauthenticated API rejection.
Add/enable approved recipients, create a draft, inspect its exact recipient and
message, then explicitly confirm sending. Newly added recipients and drafts do
not cause immediate mail by themselves.

## Verification and rollback

1. Use a recipient you control for the first delivery test.
2. Confirm SPF/DKIM/DMARC on the **received** message; acceptance is not inbox delivery.
3. Open its link yourself, inspect the English disclosure and first-visit order,
   then verify the automatic notice and its real mailbox placement.
4. Reopen the same link: visits may increase, but the order stays unchanged and
   a sent notice must not be sent again. Scanners may have opened it first.
5. Pause the link or disable the recipient to stop further work. An in-flight
   message can still complete. Keep prior source/release keys for code rollback.

The record table is retained when the core stack is deleted. Decide separately
how to remove retained records, secrets, queues, logs, S3 artifacts and backups;
deleting a stack is not a complete personal-data erasure procedure. Do not delete
an institution's live deployment merely to test these instructions.

## Optional legacy Gophish bridge

`python3 local/gophish_bridge.py` opens a **loopback-only** SMTP capture listener
on port 2525 and a signed webhook/dashboard on port 9099. Obtain Gophish separately.
Configure its webhook signing secret using the locally generated `webhook.secret`.
The bridge accepts only example/test recipients in source and captures mail
locally; it does **not** send Gmail or Resend messages or provide independent
automatic delivery. Do not expose its dashboard to the Internet.
