import sys,unittest,threading,copy,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_worker
app=test_worker.app
class MemoryDB:
 def __init__(self):self.rows={};self.lock=threading.RLock()
 def get_item(self,Key,**kw):
  with self.lock:return {'Item':copy.deepcopy(self.rows[Key['token']])} if Key['token'] in self.rows else {}
 def update_item(self,Key,**kw):
  with self.lock:
   row=self.rows[Key['token']];row['last_visit']=kw['ExpressionAttributeValues'][':n'];row['visits']=row.get('visits',0)+1
 def transact_write_items(self,TransactItems):
  with self.lock:
   c,l=[t['Update'] for t in TransactItems];ck=c['Key']['token']['S'];lk=l['Key']['token']['S']
   old=self.rows.get(ck);cv=c['ExpressionAttributeValues'];lv=l['ExpressionAttributeValues'];row=self.rows[lk]
   if ('first_visit' in row or (old and int(old['rank_count'])!=int(cv.get(':old',{'N':'-1'})['N'])) or (old is None and ':old' in cv)):
    raise test_worker.ClientError('TransactionCanceledException')
   rank=int(cv[':new']['N']);self.rows[ck]={'record_type':'rank_counter','rank_count':rank}
   row.update(first_visit=int(lv[':n']['N']),last_visit=int(lv[':n']['N']),click_rank=rank,visits=row.get('visits',0)+1)
class RankTests(unittest.TestCase):
 def setUp(self):
  self.db=MemoryDB();self.table=patch.object(app,'table',self.db);self.ddb=patch.object(app,'ddb',self.db);self.table.start();self.ddb.start();self.addCleanup(self.table.stop);self.addCleanup(self.ddb.stop)
 def row(self,token,group='group',owner='owner'):
  r={'token':token,'campaign':group,'authorized_by':owner,'expires_at':9999999999,'visits':0};self.db.rows[token]=r;return copy.deepcopy(r)
 def test_sequential_order(self):
  for i in range(1,4):self.assertEqual(app.record_visit(self.row(str(i)),100)['click_rank'],i)
 def test_repeat_keeps_rank(self):
  r=app.record_visit(self.row('a'),100);self.assertEqual(app.record_visit(r,101)['click_rank'],1);self.assertEqual(self.db.rows['a']['visits'],2)
 def test_campaign_scope(self):
  self.assertEqual(app.record_visit(self.row('a','A'),100)['click_rank'],1);self.assertEqual(app.record_visit(self.row('b','B'),100)['click_rank'],1)
 def test_owner_scope(self):
  self.assertEqual(app.record_visit(self.row('a',owner='A'),100)['click_rank'],1);self.assertEqual(app.record_visit(self.row('b',owner='B'),100)['click_rank'],1)
 def test_legacy_repeat_not_ranked(self):
  r=self.row('old');r['first_visit']=50;self.db.rows['old']=r
  self.assertNotIn('click_rank',app.record_visit(r,100));self.assertIn('predates',app.rank_message(r))
 def test_concurrent_same_link(self):
  stale=self.row('same')
  with ThreadPoolExecutor(max_workers=8) as e:r=list(e.map(lambda _:app.record_visit(dict(stale),100),range(8)))
  self.assertEqual({x['click_rank'] for x in r},{1});self.assertEqual(self.db.rows['same']['visits'],8);self.assertEqual(self.db.rows[app.rank_key(stale)]['rank_count'],1)
 def test_concurrent_distinct_links(self):
  rows=[self.row(str(i)) for i in range(8)]
  with ThreadPoolExecutor(max_workers=8) as e:r=list(e.map(lambda row:app.record_visit(row,100),rows))
  self.assertEqual(sorted(x['click_rank'] for x in r),list(range(1,9)))
 def test_ordinals(self):
  self.assertEqual([app.ordinal(x) for x in (1,2,3,4,11,12,13,21,22,23,111)],['1st','2nd','3rd','4th','11th','12th','13th','21st','22nd','23rd','111th'])
 def test_rank_text_is_not_human_claim(self):self.assertIn('distinct link',app.rank_message({'click_rank':2}))
 def test_html_escape_and_english(self):
  row=dict(self.row('html'),email=app.ALLOWED,campaign='<script>alert(1)</script>');self.db.rows['html']=row
  with patch.object(app,'recipient_allowed',return_value=True),patch.object(app,'record_visit',return_value=dict(row,click_rank=2)),patch.object(app,'table') as table,patch.object(app,'enqueue'):
   table.get_item.return_value={'Item':row}
   r=app.track({'pathParameters':{'token':'html'}},None)
   self.assertEqual(r['statusCode'],200);self.assertIn('lang="en"',r['body']);self.assertIn('2nd',r['body']);self.assertNotIn('<script>',r['body']);self.assertNotIn(app.ALLOWED,r['body'])
 def test_rank_failure_does_not_claim_recorded(self):
  row=dict(self.row('fail'),email=app.ALLOWED)
  with patch.object(app,'table') as table,patch.object(app,'recipient_allowed',return_value=True),patch.object(app,'record_visit',side_effect=RuntimeError()):
   table.get_item.return_value={'Item':row};self.assertEqual(app.track({'pathParameters':{'token':'fail'}},None)['statusCode'],503);table.put_item.assert_not_called()
 def test_notice_english_and_rank(self):
  row=dict(self.row('mail'),email=app.ALLOWED,first_visit=100,notice_state='pending',click_rank=3)
  with patch.object(app,'table') as table,patch.object(app,'recipient_allowed',return_value=True),patch.object(app,'send_email',return_value={'MessageId':'test','Provider':'resend'}) as send:
   table.get_item.return_value={'Item':row};app.deliver('mail');m=send.call_args.kwargs['Message'];self.assertIn('3rd',m['Body']['Text']['Data']);self.assertIn('simulated phishing',m['Body']['Text']['Data']);self.assertTrue(m['Body']['Text']['Data'].isascii())
if __name__=='__main__':unittest.main()
