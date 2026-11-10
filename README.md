# Anti-Scam Club

An educational anti-scam and phishing-awareness experiment: an authenticated
console, per-link visit records, immediate educational feedback and automatic
email notices. **For authorized awareness testing, not real fraud.**

> 仅用于经授权的反诈测试与安全意识培训。不收集密码或验证码。
> 发布代码或写免责声明不代表获得学校批准，也不自动满足所有法律和隐私要求。

## Intended use

Obtain written authorization from the organization responsible for the systems
and participants **before** sending an exercise. Define recipients, dates,
data access, retention and the reporting contact. Do not use this project for
unauthorized impersonation, credential harvesting, account compromise or
harassment. Keep reporting to IT available, even when asking participants not
to spoil the exercise for others. See [Responsible use](docs/RESPONSIBLE_USE.md).

These statements describe project intent and operating expectations. They do
not add field-of-use restrictions to the standard [MIT license](LICENSE), and
MIT is not institutional approval or a determination that a deployment is lawful.

## Features

- Invited-administrator sign-in using Amazon Cognito and PKCE; protected admin API.
- Individually authorized recipients, draft/preview/send and recipient disabling.
- Resend delivery with HTML and plain-text alternatives. HTML link label:
  **View shared document**, pointing to the actual exercise URL.
- A visit opens a disclosure page explaining the exercise, not an account-login form.
- First-visit order per **exact campaign name + administrator**. Repeated visits
  keep the same number; ordering counts links, not verified people.
- English automatic notice, normally once per link, including **DO NOT** share
  exercise details with other participants until the exercise ends. Reporting
  concerns to school IT or the exercise coordinator remains permitted.
- Persistent records, queue processing and scheduled recovery on AWS.
- English/Chinese administration interface and a loopback-only local demo.

Email scanners and forwarded links can trigger a visit. No visit or order number
proves who clicked, that a person read the email, or that an account was compromised.
Provider acceptance is not proof of inbox delivery or message reading.

## Repository layout

```text
backend/       Console handlers and tracking/email worker source
frontend/      React/Vite console
infra/         Generic CloudFormation template/package builders
local/         Loopback-only demo and optional Gophish capture bridge
scripts/       Offline test runner and public-source checks
tests/        Mocked backend, ranking and HTML-mail tests
docs/         Deployment, privacy and responsible-use notes
```

No production configuration, participant data, active tokens, API keys, captured
mail, database, compiled third-party runtime or live account identifiers are
included. `local-private/`, local PDFs and operational artifacts are ignored.
The optional Gophish program itself is **not** bundled or relicensed.

## Local demo (no emails)

Python 3.11+:

```sh
python3 local/demo.py --port 8765
```

Open `http://127.0.0.1:8765/`. This uses fictional participants and a local SQLite
database. The demo has **no authentication**: keep its listener on loopback; do
not expose it to the Internet. It is not the AWS administration console.

## Tests and build

```sh
python3 scripts/test.py
python3 scripts/check_public.py
npm ci --prefix frontend
npm run test:i18n --prefix frontend
npm run build --prefix frontend
```

The backend test suite is mocked and does not send email or require AWS access.
The frontend build is local; production use requires a configured backend and
Cognito. Runtime Python dependency: `boto3` (provided by the selected Lambda
runtime, or install from `requirements.txt` for local AWS development).

## AWS deployment

See [Deployment](docs/DEPLOYMENT.md). Templates are examples for a **new isolated
installation**, not instructions to update any existing school system. Building
artifacts does not deploy them. Deployment creates chargeable resources and
requires your own verified sending domain, Resend secret and authorized recipients.

## Security and data

See [Security](SECURITY.md) and [Data handling](docs/DATA_HANDLING.md).
Recipients and bearer tracking URLs must not be committed. Authentication does
not make link activity a reliable measure of an individual's behavior. Do not
use these results alone for disciplinary or other consequential decisions.

## License

[MIT](LICENSE). Dependencies retain their own licenses; see
[Third-party notices](THIRD_PARTY_NOTICES.md).
