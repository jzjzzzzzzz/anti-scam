#!/usr/bin/env python3
"""Local-only awareness training demo; standard library, no email sending."""
import argparse, html, json, secrets, sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

DB = Path(__file__).with_name('demo.sqlite3')

def connect():
    con = sqlite3.connect(DB)
    con.execute('CREATE TABLE IF NOT EXISTS recipients(token TEXT PRIMARY KEY, name TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS events(token TEXT, kind TEXT, time TEXT)')
    return con

with connect() as con:
    if not con.execute('SELECT count(*) FROM recipients').fetchone()[0]:
        con.executemany('INSERT INTO recipients VALUES (?, ?)', [(secrets.token_urlsafe(24), n) for n in ['虚拟学生 A', '虚拟学生 B', '虚拟学生 C']])

def page(title, body):
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{title}</title>
<style>body{{font:16px/1.7 system-ui;margin:48px auto;padding:0 24px;max-width:1000px;color:#172b3a;background:#f4f7fa}}section{{background:white;border:1px solid #dce4eb;border-radius:16px;padding:28px;margin:20px 0}}h1{{line-height:1.3}}a{{color:#1265ad}}button{{background:#1265ad;color:white;border:0;border-radius:8px;padding:12px 24px;font-size:16px;cursor:pointer}}table{{border-collapse:collapse;width:100%}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #dde5eb}}code{{overflow-wrap:anywhere}}.tag{{color:#577083;font-size:14px}}</style>
<p class="tag">LOCAL DEMO · 防诈培训演示 · 全部为虚拟收件人</p><h1>{title}</h1>{body}</html>'''

class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body, mime='text/html; charset=utf-8'):
        payload = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def record(self, token, kind):
        with connect() as con:
            if not con.execute('SELECT 1 FROM recipients WHERE token=?', (token,)).fetchone():
                return False
            con.execute('INSERT INTO events VALUES (?, ?, ?)', (token, kind, datetime.now(timezone.utc).isoformat()))
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/':
            with connect() as con:
                rows = con.execute("SELECT r.token,r.name,(SELECT count(*) FROM events WHERE token=r.token AND kind='visit'),(SELECT count(*) FROM events WHERE token=r.token AND kind='interaction') FROM recipients r ORDER BY name").fetchall()
            tr = ''.join(f'<tr><td>{html.escape(n)}</td><td>{v}</td><td>{i}</td><td><a href="/t/{t}" target="_blank" rel="noopener">打开独立演示链接</a></td></tr>' for t,n,v,i in rows)
            visits = sum(v > 0 for _,_,v,_ in rows)
            actions = sum(i > 0 for _,_,_,i in rows)
            self.reply(200, page('点击追踪后台', f'<section><b>访问人数：{visits} / {len(rows)}　页面交互人数：{actions} / {len(rows)}</b><p>点击下面某位虚拟学生的链接，然后回来刷新，即可看到记录变化。</p><table><tr><th>收件人</th><th>访问次数</th><th>交互次数</th><th>测试</th></tr>{tr}</table></section><section><h2>统计如何产生？</h2><p>每个随机 token 对应一个虚拟收件人。访问 /t/token 时写入 visit；按下页面按钮后写入 interaction。重复访问保留次数，人数按 token 去重。</p><p>访问 ≠ 真人点击；按钮交互也不是绝对证明。链接转发后仍记在原 token 下。本演示没有发送邮件，所以不计算送达率或真实邮件点击率。</p><p>只存随机标识、虚拟姓名、事件类型及 UTC 时间，不存 IP、密码或浏览器指纹。此后台仅限本机演示，没有身份认证，不要直接发布到公网。</p></section>'))
        elif path.startswith('/t/'):
            token = path[3:]
            if not self.record(token, 'visit'):
                return self.reply(404, 'Unknown link', 'text/plain')
            self.reply(200, page('校园活动资料 · 演示', f'<section><h2>查看活动资料</h2><p>这是一个明确标注的防诈培训演示。打开此页面已产生一条“访问”记录。</p><form method="post" action="/confirm/{html.escape(token, quote=True)}"><button type="submit">继续查看并完成演示</button></form><p>点击按钮会另外记录一次页面交互，不需要填写任何个人信息。</p></section>'))
        elif path == '/api/stats':
            with connect() as con:
                rows = con.execute('SELECT r.name,e.kind,e.time FROM events e JOIN recipients r ON e.token=r.token ORDER BY e.rowid').fetchall()
            self.reply(200, json.dumps([dict(name=n,kind=k,time=t) for n,k,t in rows], ensure_ascii=False), 'application/json; charset=utf-8')
        else:
            self.reply(404, 'Not found', 'text/plain')

    def do_POST(self):
        path = urlsplit(self.path).path
        if not path.startswith('/confirm/'):
            return self.reply(404, 'Not found', 'text/plain')
        if not self.record(path[len('/confirm/'):], 'interaction'):
            return self.reply(404, 'Unknown link', 'text/plain')
        self.reply(200, page('演示完成：识别可疑邮件', '<section><p>刚才的按钮操作已记录为“页面交互”，不是凭证泄露。</p><h2>点击前检查</h2><ul><li>发件地址是否与声称的机构一致？</li><li>是否利用紧迫感、奖励或威胁催你行动？</li><li>链接的真实域名是否可信？</li><li>能否从官网或已知联系方式核实，而不是直接点邮件？</li></ul><a href="/">返回统计后台（本地演示）</a></section>'))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    print(f'Local demo: http://127.0.0.1:{args.port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
