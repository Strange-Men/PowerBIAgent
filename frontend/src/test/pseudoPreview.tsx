/** Test-only entry: actual product UI with expanded bundled display resources. */
import { createRoot } from 'react-dom/client'
import { App } from '../App'
import { i18n, resources, setLocale } from '../i18n'
import { pseudoText } from './pseudoLocale'
import '../styles.css'

const preview=new URLSearchParams(location.search)
if(!preview.has('plain')) {
  for (const [namespace,entries] of Object.entries(resources['en-US'])) {
    i18n.addResourceBundle('en-US',namespace,
      Object.fromEntries(Object.entries(entries).map(([key,value])=>[key,pseudoText(value)])),true,true)
  }
}
void setLocale(preview.get('locale')||'en-US').then(()=>createRoot(document.getElementById('root')!).render(<App />))
