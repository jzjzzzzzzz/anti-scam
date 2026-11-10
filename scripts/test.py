#!/usr/bin/env python3
"""Run mocked suites in isolated processes; never call AWS or send email."""
from pathlib import Path
import subprocess,sys
root=Path(__file__).resolve().parents[1]
for name in ('test_worker.py','test_console.py','test_rank.py','test_mail.py'):
    subprocess.run([sys.executable,str(root/'tests'/name)],cwd=root,check=True)
