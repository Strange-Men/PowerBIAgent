/** TEST ONLY: deliberately expanded resource text, never a supported product locale. */
import { createInstance } from 'i18next'
import { initReactI18next } from 'react-i18next'
import { resources } from '../i18n'

export function pseudoText(value:string) {
  return '[!! '+value.replace(/{{.*?}}|[aeiou]/gi,(part)=>part.startsWith('{{')?part:({a:'á',e:'ë',i:'ï',o:'ö',u:'ü'}[part.toLowerCase()]||part))+' ~~~~~~~~~~ !!]'
}
export function pseudoInstance() {
  const namespaces=Object.fromEntries(Object.entries(resources['en-US']).map(([ns,entries])=>[
    ns,Object.fromEntries(Object.entries(entries).map(([key,value])=>[key,pseudoText(value)])),
  ]))
  const instance=createInstance()
  void instance.use(initReactI18next).init({lng:'en-XA',supportedLngs:['en-XA'],fallbackLng:false,
    resources:{'en-XA':namespaces},defaultNS:'common',initAsync:false,interpolation:{escapeValue:false}})
  return instance
}
