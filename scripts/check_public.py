#!/usr/bin/env python3
"""Check tracked source (or clean source tree) for private data and common secrets.
This is a conservative guard, not a complete secret scanner or a security audit.
"""
from pathlib import Path
import re,subprocess,sys
root=Path(__file__).resolve().parents[1]
skip={'local-private','.git','node_modules','dist','build','__pycache__','.venv'}
proc=subprocess.run(['git','ls-files','-z'],cwd=root,capture_output=True)
paths=[root/x for x in proc.stdout.decode().split('\0') if x] if proc.returncode==0 and proc.stdout else [p for p in root.rglob('*') if p.is_file() and not any(x in skip for x in p.relative_to(root).parts) and p.suffix not in ('.pdf',)]
patterns=[r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',r'\bgh[pousr]_[A-Za-z0-9]{24,}\b',r'\bre_[A-Za-z0-9_-]{20,}\b',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b',r'\b\d{12}\b',r'https://[a-z0-9]+\.execute-api\.[a-z0-9-]+\.amazonaws\.com']
errors=[]
for p in paths:
 rel=p.relative_to(root)
 if any(x in skip for x in rel.parts) or (p.name.startswith('.env') and p.name!='.env.example') or p.suffix in ('.pdf','.zip','.eml','.db','.sqlite3','.secret','.pem','.key'):
  errors.append(str(rel)+': private/generated file tracked');continue
 try:text=p.read_text()
 except (UnicodeError,OSError):errors.append(str(rel)+': non-source file requires review');continue
 if any(re.search(pattern,text) for pattern in patterns):errors.append(str(rel)+': possible secret or live deployment identifier')
 for domain in re.findall(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})',text):
  domain=domain.lower()
  if not (domain in ('example.com','example.org','example.invalid','test.example') or domain.endswith('.example.com')):errors.append(str(rel)+': non-example email address');break
if errors:
 print('\n'.join(sorted(set(errors))));sys.exit(1)
print('PASS: reviewed source contains no detected private artifacts, non-example emails or common secret patterns.')
