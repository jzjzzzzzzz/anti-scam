import {useI18n,LanguageProvider,LanguageSwitch,getLanguage} from './i18n.jsx';
import React, { useState, useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import { api, callback, config, hasToken, login, logout } from './auth';
import './style.css';
const labels = {
  armed: '未访问',
  pending: '待处理',
  sending: '发送中',
  sent: '已发送',
  failed: '发送失败',
  uncertain: '需核实',
  awaiting_verification: '等待验证',
  suppressed: '已停止',
  draft: '草稿',
  queued: '已入队',
  cancelled: '已取消'
};
const fmt = (timestamp,language=getLanguage()) => timestamp ? new Date(Number(timestamp)*1000).toLocaleString(language==='en'?'en-US':'zh-CN',{hour12:false}) : '—';
function MailPreview({body='',url}) {
  const parts=body.replaceAll('View shared document:\n{{link}}','{{link}}').split('{{link}}');
  return <pre>{parts.map((part,i)=><React.Fragment key={i}>{i>0&&<a href={url} target="_blank" rel="noopener noreferrer">View shared document</a>}{part}</React.Fragment>)}</pre>;
}
function Icon({
  name
}) {
  const paths = {
    shield: 'M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6Z',
    list: 'M8 5H5v16h14V5h-3 M9 3h6v5H9Z M8 12h8 M8 16h8',
    click: 'm5 3 14 11-7 1-3 6Z M13 16l4 5',
    mail: 'M3 5h18v14H3Z M3 6l9 7 9-7',
    refresh: 'M20 7A9 9 0 1 0 21 14 M20 3v5h-5',
    plus: 'M12 4v16 M4 12h16',
    user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M4 21v-3a8 8 0 0 1 16 0v3'
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.list} /></svg>;
}
function Badge({
  state
}) {
  const {t,language} = useI18n();
  return <span className={'badge ' + (state === 'sent' ? 'success' : state === 'failed' || state === 'uncertain' ? 'warning' : '')}>{t(labels[state] || state || '—')}</span>;
}
function App() {
  const {t,language} = useI18n();
  const [ready, setReady] = useState(false),
    [data, setData] = useState(null),
    [tab, setTab] = useState('演练管理'),
    [error, setError] = useState(''),
    [notice, setNotice] = useState(''),
    [busy, setBusy] = useState(false),
    [drawer, setDrawer] = useState(false),
    [selected, setSelected] = useState(null),
    [confirm, setConfirm] = useState(null);
  async function load() {
    setBusy(true);
    try {
      const j = await api('dashboard');
      setData(j);
      setError('');
    } catch (e) {
      setError(e.message);
      if (!hasToken()) setData(null);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    (async () => {
      try {
        await config();
        await callback();
        if (hasToken()) await load();
      } catch (e) {
        setError(e.message);
      }
      setReady(true);
    })();
  }, []);
  useEffect(() => {
    if (!data) return;
    const i = setInterval(load, 20000);
    return () => clearInterval(i);
  }, [!!data]);
  async function action(row, kind) {
    setBusy(true);
    try {
      const r = await api('campaigns/' + row.token + '/' + kind, {
        method: 'POST',
        body: '{}'
      });
      setNotice(r.message);
      setConfirm(null);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const rows = data?.campaigns || [],
    events = data?.events || [],
    row = rows.find(x => x.token === selected);
  return <div className="shell"><aside><div className="brand"><Icon name="shield" /><strong>{t("信标")}<span>/ BEACON</span></strong></div><LanguageSwitch/><nav>{[['演练管理', 'list'], ['点击记录', 'click'], ['收件人管理', 'user'], ['发信设置', 'mail']].map(([n, i]) => <button key={n} className={tab === n ? 'active' : ''} onClick={() => setTab(n)}><Icon name={i} />{t(n)}</button>)}</nav><div className="account"><Icon name="user" /><span>{t("登录管理员")}</span>{data && <button onClick={logout}>{t("退出")}</button>}</div></aside><main>{!data ? <div className="login"><Icon name="shield" /><h1>{t("登录控制台")}</h1><p>{t("使用安全登录方式访问信标 / BEACON 控制台。")}</p><p className="muted">{t("仅限受邀管理员，未登录不能查看演练数据或发信。")}</p>{error && <div role="alert" className="error">{t(error)}</div>}<button className="primary" onClick={login} disabled={!ready}><Icon name="shield" />{t("使用安全登录")}</button></div> : <><header><div><h1>{t(tab)}</h1><p>{t(tab === '演练管理' ? '创建邮件演练，查看访问与自动提醒。' : tab === '点击记录' ? '记录链接访问时间；访问不等于本人点击。' : tab === '收件人管理' ? '管理授权收件人，添加邮箱不会自动发送邮件。' : '发信身份与访问权限由后台统一管理。')}</p></div><div className="actions"><button onClick={load} disabled={busy}><Icon name="refresh" />{t("刷新")}</button><button className="primary" onClick={() => setDrawer(true)}><Icon name="plus" />{t("创建演练")}</button></div></header>{error && <div role="alert" className="error">{t(error)}</div>}{notice && <div role="status" className="notice">{t(notice)}<button onClick={() => setNotice('')}>×</button></div>}
{tab === '演练管理' && <><div className="metrics">{[['演练总数', rows.length], ['访问次数', rows.reduce((a, r) => a + Number(r.visits || 0), 0)], ['已发送提醒', rows.filter(r => r.notice_state === 'sent').length]].map(([n, v]) => <div key={n}><span>{t(n)}</span><strong>{v}</strong></div>)}</div><div className="table-wrap"><table><thead><tr>{['演练名称', '收件人', '访问次数', '提醒状态', '创建时间'].map(h => <th key={h}>{t(h)}</th>)}</tr></thead><tbody>{rows.map(r => <tr key={r.token} className={r.token === selected ? 'selected' : ''} tabIndex="0" onClick={() => setSelected(r.token)} onKeyDown={e => e.key === 'Enter' && setSelected(r.token)}><td><strong>{r.campaign}</strong>{r.disabled && <small>{t(r.initial_state === 'draft' ? '草稿' : '已暂停')}</small>}</td><td>{r.email}</td><td>{r.visits || 0}</td><td><Badge state={r.notice_state} /></td><td>{fmt(r.created_at,language)}</td></tr>)}</tbody></table>{!rows.length && <p className="empty">{t("还没有演练，点击“创建演练”开始。")}</p>}</div><p className="muted footnote">{t("同一管理员使用完全相同的演练名称即可合并统计首次访问顺序；按链接而非人数排名。")}<br/>{t("提醒按链接去重 · 访问可能来自安全扫描。")}{t(data.truncated ? ' 数据较多，当前为部分记录。' : '')}</p>
{row && <section className="detail"><div className="section-title"><h2>{t("演练详情")}</h2><button onClick={() => setSelected(null)}>{t("关闭详情")}</button></div><div className="detail-meta"><span>{t("初始邮件：")}<Badge state={row.initial_state || 'sent'} /></span><span>{t("自动提醒：")}<Badge state={row.notice_state} /></span><span>{t("首次访问顺序：")}{row.click_rank ? "#" + row.click_rank : t("未分配")}</span><span>{t("最近访问时间：")}{fmt(row.last_visit,language)}</span></div><div className="preview"><b>{t("原始邮件内容（预览）")}</b><p><b>{t("主题：")}</b>{row.subject || t('历史演练，未保存邮件模板')}</p><MailPreview body={row.body || ''} url={row.url}/></div><div className="actions"><button onClick={() => {
                setTab('点击记录');
              }}>{t("查看访问记录")}</button><button onClick={() => navigator.clipboard.writeText(row.url).then(() => setNotice('链接已复制'))}>{t("复制链接")}</button>{row.initial_state === 'draft' && <button className="primary" onClick={() => setConfirm({
                kind: 'send',
                row
              })}>{t("预览并发送")}</button>}{!row.disabled && <button onClick={() => setConfirm({
                kind: 'pause',
                row
              })}>{t("暂停链接")}</button>}</div>{(row.last_error || row.initial_error) && <p className="error">{t(row.initial_error || row.last_error)}</p>}<p className="muted">{t("有效期至")}{fmt(row.expires_at,language)}{t("· 提醒服务")}{row.mail_provider || t(row.ses_message_id ? 'SES（历史）' : '尚未触发')} · {row.provider_message_id || row.ses_message_id || t('尚无提醒发送编号')}</p></section>}</>}
{tab === '点击记录' && <><div className="section-title"><p>{t("显示最近")}{events.filter(e=>!selected||e.link_token===selected).length}{t("条访问记录")}{t(selected ? ' · 当前选中演练' : '')}</p>{selected && <button onClick={() => setSelected(null)}>{t("显示全部")}</button>}</div><div className="table-wrap"><table><thead><tr><th>{t("演练名称")}</th><th>{t("访问时间（本机时区）")}</th><th>{t("事件类型")}</th></tr></thead><tbody>{events.filter(e => !selected || e.link_token === selected).map(e => <tr key={e.token}><td>{rows.find(r => r.token === e.link_token)?.campaign || t('历史链接')}</td><td>{fmt(e.visited_at,language)}</td><td>{t("链接访问")}</td></tr>)}</tbody></table></div></>}
{tab === '收件人管理' && <Recipients recipients={data.recipients || []} onChanged={async message => {
          setNotice(message);
          await load();
        }} />}
{tab === '发信设置' && <section className="settings"><h2>{t("已验证的发信身份")}</h2><dl><dt>{t("发件地址")}</dt><dd>{data.sender}</dd><dt>{t("邮件服务")}</dt><dd>Resend</dd><dt>{t("已启用收件人")}</dt><dd>{(data.recipients || []).filter(r => r.enabled).length}{t("位 · 在“收件人管理”中维护")}</dd><dt>{t("自动提醒")}</dt><dd>{t("开启 · 同一链接正常情况下只提醒一次")}</dd><dt>{t("登录保护")}</dt><dd>{t("Amazon Cognito · 仅限受邀管理员")}</dd><dt>{t("密钥")}</dt><dd>{t("由后台加密保存，浏览器不可读取")}</dd></dl><p className="muted">{t("收件人由管理员逐一授权添加；发件身份与密钥仍由后台保护。")}</p></section>}
</>}{drawer && <Create onClose={() => setDrawer(false)} recipients={data?.recipients || []} email={data?.recipient} onCreated={async t => {
        setDrawer(false);
        setSelected(t);
        setTab('演练管理');
        setNotice('草稿已创建，尚未发送邮件。');
        await load();
      }} />}{confirm && <div className="overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-title"><section className="confirm"><h2 id="confirm-title">{t(confirm.kind === 'send' ? '确认发送演练邮件' : '确认暂停链接')}</h2><p>{confirm.row.campaign}</p>{confirm.kind === 'send' ? <><p>{t("发件人：")}{data.sender}<br />{t("收件人：")}{confirm.row.email}</p><div className="preview"><b>{confirm.row.subject}</b><MailPreview body={confirm.row.body || ''} url={confirm.row.url}/></div><p className="muted">{t("只发送给上述已授权收件人；入队不代表已送达。")}</p></> : <p>{t("暂停后新的链接访问将被拒绝，正在进行的发送可能已经完成。")}</p>}<div className="actions"><button onClick={() => setConfirm(null)}>{t("取消")}</button><button className="primary" disabled={busy} onClick={() => action(confirm.row, confirm.kind)}>{t(busy ? '处理中…' : confirm.kind === 'send' ? '确认发送' : '暂停链接')}</button></div></section></div>}</main></div>;
}
function Create({
  onClose,
  onCreated,
  email,
  recipients
}) {
  const {t,language} = useI18n();
  const enabled = recipients.filter(r => r.enabled);
  const [emailChoice, setEmailChoice] = useState(enabled.some(r => r.email === email) ? email : enabled[0]?.email || '');
  const [name, setName] = useState(''),
    [subject, setSubject] = useState(()=>t('defaultSubject')),
    [body, setBody] = useState(()=>t('defaultBody')),
    [days, setDays] = useState(30),
    [consent, setConsent] = useState(false),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api('campaigns', {
        method: 'POST',
        body: JSON.stringify({
          name,
          subject,
          body,
          days: Number(days),
          consent,
          email: emailChoice
        })
      });
      await onCreated(r.token);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return <div className="drawer-overlay"><section className="drawer" role="dialog" aria-modal="true" aria-labelledby="create-title"><div className="section-title"><h2 id="create-title">{t("创建演练")}</h2><button aria-label={t("关闭创建表单")} onClick={onClose}>×</button></div><form onSubmit={submit}><label>{t("演练名称 *")}<input required maxLength="100" value={name} onChange={e => setName(e.target.value)} placeholder={t("新一期安全意识演练")} autoFocus /></label><label>{t("收件人 *")}<select required value={emailChoice} onChange={e => setEmailChoice(e.target.value)}><option value="" disabled>{t("请选择已启用的收件人")}</option>{enabled.map(r => <option key={r.email} value={r.email}>{(r.system_default?t("原学校邮箱"):r.label) ? (r.system_default?t("原学校邮箱"):r.label) + " · " : ""}{r.email}</option>)}</select></label><p className="muted">{t("每个演练只发给一位收件人；可先在“收件人管理”中添加并启用邮箱。")}</p><label>{t("邮件主题 *")}<input required maxLength="180" value={subject} onChange={e => setSubject(e.target.value)} /></label><label>{t("邮件正文 *")}<textarea required maxLength="10000" rows="9" value={body} onChange={e => setBody(e.target.value)} /></label><p className="muted">{t("保留")}{t('{{link}}')}{t("，发送时显示为 View shared document 超链接；纯文本邮件保留完整地址。")}</p><label>{t("有效期（天） *")}<input type="number" min="1" max="90" required value={days} onChange={e => setDays(e.target.value)} /></label><label className="check"><input type="checkbox" required checked={consent} onChange={e => setConsent(e.target.checked)} />{t("我确认本次为授权演练，仅用于安全意识培训。")}</label>{error && <p className="error" role="alert">{t(error)}</p>}<button className="primary full" disabled={busy || !emailChoice}>{t(busy ? '创建中…' : '创建草稿')}</button></form></section></div>;
}
function Recipients({
  recipients,
  onChanged
}) {
  const {t,language} = useI18n();
  const [email, setEmail] = useState(''),
    [label, setLabel] = useState(''),
    [consent, setConsent] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [changing, setChanging] = useState(null),
    [enableConsent, setEnableConsent] = useState(false);
  async function add(e) {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const r = await api('recipients', {
        method: 'POST',
        body: JSON.stringify({
          email,
          label,
          consent
        })
      });
      setEmail('');
      setLabel('');
      setConsent(false);
      await onChanged(r.message);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function toggle() {
    setBusy(true);
    setError('');
    try {
      const r = await api('recipients/status', {
        method: 'POST',
        body: JSON.stringify({
          email: changing.email,
          enabled: !changing.enabled,
          consent: enableConsent
        })
      });
      setChanging(null);
      setEnableConsent(false);
      await onChanged(r.message);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return <><section className="recipient-add"><h2>{t("添加收件人")}</h2><form onSubmit={add}><div className="recipient-fields"><label>{t("邮箱地址 *")}<input type="email" required maxLength="254" value={email} onChange={e => setEmail(e.target.value)} placeholder="name@example.com" /></label><label>{t("备注名称")}<input maxLength="80" value={label} onChange={e => setLabel(e.target.value)} placeholder={t("例如：已授权参与者")} /></label></div><label className="check"><input type="checkbox" required checked={consent} onChange={e => setConsent(e.target.checked)} />{t("我确认此收件人已同意参与，或属于学校已批准的演练范围。")}</label><button className="primary" disabled={busy}>{t(busy ? '处理中…' : '添加收件人')}</button></form><p className="muted">{t("添加不会发送邮件，也不会触发 AWS 邮箱验证请求。创建演练后仍需单独预览并确认发送。")}</p></section>{error && <p role="alert" className="error">{t(error)}</p>}<div className="table-wrap"><table><thead><tr><th>{t("邮箱地址")}</th><th>{t("备注")}</th><th>{t("状态")}</th><th>{t("添加时间")}</th><th>{t("操作")}</th></tr></thead><tbody>{recipients.map(r => <tr key={r.email}><td>{r.email}</td><td>{(r.system_default?t('原学校邮箱'):r.label) || '—'}</td><td><span className={'badge ' + (r.enabled ? 'success' : '')}>{t(r.enabled ? '已启用' : '已停用')}</span></td><td>{r.created_at ? fmt(r.created_at,language) : t('原有配置')}</td><td><button onClick={() => {
                setChanging(r);
                setEnableConsent(false);
              }}>{t(r.enabled ? '停用' : '启用')}</button></td></tr>)}</tbody></table></div>{changing && <div className="overlay" role="dialog" aria-modal="true" aria-labelledby="recipient-change"><section className="confirm"><h2 id="recipient-change">{t(changing.enabled ? '停用收件人' : '启用收件人')}</h2><p>{changing.email}</p>{changing.enabled ? <p>{t("停用后，该邮箱的后续初始邮件、自动提醒和追踪链接访问均会被阻止。已经在途的发送可能完成，历史记录不会删除。")}</p> : <label className="check"><input type="checkbox" checked={enableConsent} onChange={e => setEnableConsent(e.target.checked)} />{t("我确认此收件人仍属于已授权的演练范围。")}</label>}<div className="actions"><button onClick={() => setChanging(null)}>{t("取消")}</button><button className="primary" disabled={busy || !changing.enabled && !enableConsent} onClick={toggle}>{t("确认")}{t(changing.enabled ? '停用' : '启用')}</button></div></section></div>}</>;
}
createRoot(document.getElementById('root')).render(<LanguageProvider><App /></LanguageProvider>);
