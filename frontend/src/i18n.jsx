import React,{createContext,useContext,useEffect,useMemo,useState}from'react';
import messages from './messages.json';
const defaults={"defaultSubject": "A document has been shared with you: Updated activity schedule", "defaultBody": "Hello,\n\nAn updated activity schedule has been shared with you. Please review the document before the next meeting.\n\nView shared document:\n{{link}}\n\nThank you,\nDocument Notifications"};
const I18n=createContext(null);
export function getLanguage(){try{return localStorage.getItem('beacon_language')==='en'?'en':'zh';}catch{return'zh';}}
export function translate(key,language=getLanguage()){if(typeof key!=='string')return key;return language==='en'?(messages[key]??key):(defaults[key]??key);}
export function LanguageProvider({children}){const[language,setLanguage]=useState(getLanguage);useEffect(()=>{document.documentElement.lang=language==='en'?'en':'zh-CN';document.title=language==='en'?'BEACON · Awareness Console':'信标 · 演练控制台';try{localStorage.setItem('beacon_language',language);}catch{}},[language]);const value=useMemo(()=>({language,setLanguage,t:key=>translate(key,language)}),[language]);return <I18n.Provider value={value}>{children}</I18n.Provider>}
export function useI18n(){return useContext(I18n)}
export function LanguageSwitch(){const{language,setLanguage}=useI18n();return <label className="language-control">语言 / Language<select aria-label="Language / 语言" value={language} onChange={e=>setLanguage(e.target.value)}><option value="zh">简体中文</option><option value="en">English</option></select></label>}
