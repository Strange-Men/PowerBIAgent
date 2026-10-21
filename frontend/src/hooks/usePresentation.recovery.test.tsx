import {renderHook,waitFor} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {usePresentation} from './usePresentation'
import * as api from '../api/client'
vi.mock('../api/client',()=>({projectPresentation:vi.fn()}))

it('a later successful projection clears a transient failure for the same message',async()=>{
  vi.mocked(api.projectPresentation).mockRejectedValueOnce(new Error('temporary'))
    .mockResolvedValue({answer:'Verified answer',presentation:{blocks:[]},factual_hash:'same'} as never)
  const message={id:'request-1',role:'assistant',kind:'answer',content:'Original',presentationAvailable:true} as const
  const {result,rerender}=renderHook(({callback})=>usePresentation(message,{mode:'real',cloud:true,onAuthInvalid:callback}),
    {initialProps:{callback:()=>{}}})
  await waitFor(()=>expect(result.current.failed).toBe(true))
  rerender({callback:()=>{}})
  await waitFor(()=>expect(result.current.value?.answer).toBe('Verified answer'))
  expect(result.current.failed).toBe(false)
})
