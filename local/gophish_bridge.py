#!/usr/bin/env python3
"""Loopback-only SMTP capture + signed Gophish webhook/outbox for this test.
Gmail connector dispatch is performed by the current chat, NOT this daemon.
"""
import hashlib,hmac,html,json,secrets,socketserver,sqlite3,threading
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
BASE=Path(__file__).resolve().parent
SECRET_FILE=BASE/'webhook.secret'
if not SECRET_FILE.exists():
    SECRET_FILE.write_text(secrets.token_hex(32));SECRET_FILE.chmod(0o600)
SECRET=SECRET_FILE.read_text().strip()

def db():
    c=sqlite3.connect(BASE/'bridge.sqlite3',timeout=15)
    c.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,event TEXT,time TEXT,email TEXT,campaign INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY,campaign INTEGER,email TEXT,event_time TEXT,status TEXT DEFAULT "pending",gmail_id TEXT,UNIQUE(campaign,email))')
    return c
with db(): pass

class SMTP(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(30)
        self.wfile.write(b'220 localhost training capture\r\n')
        recipient=None
        while True:
            line=self.rfile.readline(8192)
            if not line:return
            verb=line.split(b' ',1)[0].strip().upper()
            if verb in (b'EHLO',b'HELO'):self.wfile.write(b'250 localhost\r\n')
            elif verb==b'MAIL':self.wfile.write(b'250 OK\r\n')
            elif verb==b'RCPT':
                recipient=line.decode().split(':',1)[1].strip().strip('<>')
                self.wfile.write(b'250 OK\r\n' if recipient in ('recipient@example.com','local-test@example.invalid') else b'550 test recipient only\r\n')
            elif verb==b'DATA' and recipient:
                self.wfile.write(b'354 end with dot\r\n');data=bytearray()
                while True:
                    chunk=self.rfile.readline(65536)
                    if not chunk:return
                    if chunk==b'.\r\n':break
                    data.extend(chunk[1:] if chunk.startswith(b'..') else chunk)
                    if len(data)>2_000_000:return
                capture=BASE/('captured-'+secrets.token_hex(6)+'.eml');capture.write_bytes(data);capture.chmod(0o600)
                self.wfile.write(b'250 captured locally only\r\n')
            elif verb==b'QUIT':self.wfile.write(b'221 bye\r\n');return
            elif verb in (b'RSET',b'NOOP'):self.wfile.write(b'250 OK\r\n')
            else:self.wfile.write(b'502 unsupported\r\n')

class HTTP(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,status,body,mime='text/html; charset=utf-8'):
        p=body.encode();self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(p)));self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Frame-Options','DENY');self.end_headers();self.wfile.write(p)
    def do_POST(self):
        if self.path!='/webhook':return self.reply(404,'not found')
        try:n=int(self.headers.get('Content-Length','0'))
        except ValueError:return self.reply(400,'bad length')
        if not 0<n<65536:return self.reply(413,'too large')
        data=self.rfile.read(n)
        sig='sha256='+hmac.new(SECRET.encode(),data,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig,self.headers.get('X-Gophish-Signature','')):return self.reply(403,'bad signature')
        try:e=json.loads(data)
        except ValueError:return self.reply(400,'bad json')
        if e.get('success') is True:return self.reply(200,'OK')
        name=e.get('message','');email=e.get('email','');campaign=e.get('campaign_id',0);time=e.get('time',datetime.now(timezone.utc).isoformat())
        with db() as c:
            c.execute('INSERT INTO events(event,time,email,campaign) VALUES(?,?,?,?)',(name,time,email,campaign))
            if name=='Clicked Link' and email in ('recipient@example.com','local-test@example.invalid'):
                c.execute('INSERT OR IGNORE INTO outbox(campaign,email,event_time) VALUES(?,?,?)',(campaign,email,time))
        return self.reply(200,'OK')
    def do_GET(self):
        if self.path!='/':return self.reply(404,'not found')
        with db() as c:
            rows=c.execute('SELECT event,time,email,campaign FROM events ORDER BY id DESC LIMIT 30').fetchall()
            jobs=c.execute('SELECT email,status,gmail_id FROM outbox ORDER BY id DESC').fetchall()
        tr=''.join('<tr>'+''.join('<td>'+html.escape(str(v or '—'))+'</td>' for v in row)+'</tr>' for row in rows)
        jr=''.join('<li>'+html.escape(f'{e}：{s}；Gmail ID：{i or "尚未发送"}')+'</li>' for e,s,i in jobs)
        body='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Gophish 实测记录</title><style>body{font:16px/1.7 system-ui;max-width:1100px;margin:40px auto;padding:20px;background:#f3f6fa;color:#173043}section{background:white;border:1px solid #dce5ec;border-radius:14px;padding:24px;margin:20px 0}td,th{text-align:left;padding:12px;border-bottom:1px solid #dce5ec}table{width:100%;font-size:14px}a{color:#176bbb}</style><h1>Gophish 实测记录</h1><p>本机测试 · 刷新查看最新事件 · 不收集密码</p><section><h2>点击提醒发件队列</h2><p>pending = 已入队，尚未发送；sent = Gmail 已确认发送。本次由当前聊天连接器接力，服务自身没有 Gmail 凭证。</p><ul>'''+jr+'''</ul></section><section><h2>已验证签名的 Gophish 事件</h2><table><tr><th>事件</th><th>时间（UTC）</th><th>收件人</th><th>批次</th></tr>'''+tr+'''</table></section><p>“Email Sent”在本配置中只代表本地 SMTP 已接收，不代表学校邮箱已收到。真实投递以 Gmail 发送结果为准。链接访问可能由安全扫描触发，并不证明本人点击。</p><a href="http://127.0.0.1:3333/">Gophish 管理后台</a></html>'''
        self.reply(200,body)

if __name__=='__main__':
    class Server(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
    smtp=Server(('127.0.0.1',2525),SMTP)
    threading.Thread(target=smtp.serve_forever,daemon=True).start()
    print('SMTP capture: 127.0.0.1:2525; signed webhook/dashboard: http://127.0.0.1:9099',flush=True)
    ThreadingHTTPServer(('127.0.0.1',9099),HTTP).serve_forever()
