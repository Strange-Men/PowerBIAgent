import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { normalizeLocale } from '../i18n'
import { projectPresentation } from '../api/client'
import type { AssistantMessage, PresentationEnvelope, RuntimeMode } from '../types'

export interface ProjectionContext {
  mode: RuntimeMode
  cloud?: boolean
  csrf?: string
  generation?: number
  conversationId?: string | null
  onAuthInvalid?: () => void
}

export function usePresentation(message: AssistantMessage, context?: ProjectionContext) {
  const {i18n}=useTranslation()
  const locale=normalizeLocale(i18n.language)
  const [projected,setProjected]=useState<{key:string;answer:string;presentation:PresentationEnvelope}|null>(null)
  const [failed,setFailed]=useState<string|null>(null)
  // A projection failure is only evidence of a language switch when the reader's
  // locale actually moved.  The ref holds the locale of the previous attempt so
  // a first-load failure is never reported as a language switch.
  const previousLocale=useRef(locale)
  const [switched,setSwitched]=useState(false)
  const {mode='real',cloud=false,csrf='',generation=0,conversationId=null,onAuthInvalid}=context||{}
  const key=JSON.stringify([message.id,locale,mode,cloud,generation,conversationId])
  const enabled=Boolean(context)
  useEffect(()=>{
    if (!message.presentationAvailable || !enabled) return
    const switchedByUser=previousLocale.current!==locale
    previousLocale.current=locale
    const controller=new AbortController()
    let active=true
    void projectPresentation(message.id,locale,mode,cloud,csrf,generation,controller.signal)
      .then(value=>{if(active){setProjected({key,answer:value.answer,presentation:value.presentation});setFailed(null);setSwitched(false)}})
      .catch(error=>{if(active && error?.name!=='AbortError'){
        setFailed(key)
        setSwitched(switchedByUser)
        if(error?.status===401)onAuthInvalid?.()
      }})
    return ()=>{active=false;controller.abort()}
  },[message.id,message.presentationAvailable,locale,mode,cloud,csrf,generation,conversationId,key,onAuthInvalid,enabled])
  return {value:projected?.key===key?projected:null,failed:failed===key,
    languageSwitched:failed===key&&switched,
    pending:Boolean(context && message.presentationAvailable && projected?.key!==key && failed!==key),locale}
}