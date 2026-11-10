import sys,unittest,json,io,time
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_worker
app=test_worker.app
class MailTests(unittest.TestCase):
 def item(self):return {'body':'Hello,\n\nView shared document:\n{{link}}\n\n<script>alert(1)</script>','created_at':0,'expires_at':86400}
 def test_anchor_and_escape(self):
  m=app.initial_body(self.item(),'https://example.invalid/t/test');h=m['Html']['Data'];self.assertEqual(h.count('View shared document'),1);self.assertIn('<a href="https://example.invalid/t/test">View shared document</a>',h);self.assertNotIn('<script>',h);self.assertIn('&lt;script&gt;',h);self.assertNotIn('{{link}}',h)
 def test_plain_fallback(self):self.assertIn('https://example.invalid/t/test',app.initial_body(self.item(),'https://example.invalid/t/test')['Text']['Data'])
 def test_multiple_placeholders(self):
  i=self.item();i['body']='{{link}} and {{link}}';self.assertEqual(app.initial_body(i,'https://example.invalid/t/test')['Html']['Data'].count('<a href='),2)
 def test_transport_includes_html_and_text(self):
  with patch.dict(app.os.environ,EMAIL_PROVIDER='resend'),patch.object(app,'_resend_key','unit-key'),patch.object(app.urllib.request,'urlopen',return_value=io.BytesIO(b'{"id":"fake"}')) as call:
   app.send_email('qa',Source='noreply@example.com',Destination={'ToAddresses':[app.ALLOWED]},Message={'Subject':{'Data':'QA'},'Body':app.initial_body(self.item(),'https://example.invalid/t/test')})
   payload=json.loads(call.call_args.args[0].data);self.assertIn('<a href=',payload['html']);self.assertIn('text',payload)
 def test_reminder_caps_and_reporting(self):
  with patch.object(app,'table') as table,patch.object(app,'recipient_allowed',return_value=True),patch.object(app,'send_email',return_value={'MessageId':'fake','Provider':'resend'}) as send:
   table.get_item.return_value={'Item':{'notice_state':'pending','email':app.ALLOWED,'first_visit':100,'campaign':'Experiment 1','click_rank':2}}
   app.deliver('qa');m=send.call_args.kwargs['Message']['Body'];self.assertIn('please DO NOT share',m['Text']['Data']);self.assertIn('until the exercise ends',m['Text']['Data']);self.assertIn('You may still report',m['Text']['Data']);self.assertIn('<strong>DO NOT</strong>',m['Html']['Data'])
if __name__=='__main__':unittest.main()
