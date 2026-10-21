// @vitest-environment node
import { createServer as createHTTPServer, request } from 'node:http'
import { createServer as createViteServer } from 'vite'
import { expect, it } from 'vitest'
import config from '../vite.config'

it('preserves the browser Host through the BFF auth proxy before creating a flow',async()=>{
  let observedHost=''
  const upstream=createHTTPServer((req,res)=>{observedHost=req.headers.host || '';res.writeHead(302,{Location:'/'});res.end()})
  await new Promise<void>(resolve=>upstream.listen(0,'127.0.0.1',resolve))
  const address=upstream.address()
  if (!address || typeof address==='string') throw new Error('test_server_unavailable')
  const target=`http://127.0.0.1:${address.port}`
  const existing=config.server!.proxy!['/auth']
  const authProxy=typeof existing==='string' ? target : {...existing,target}
  const vite=await createViteServer({configFile:false,logLevel:'silent',
    cacheDir:process.env.PBIAGENT_VALIDATION_CACHE,server:{host:'127.0.0.1',port:0,proxy:{'/auth':authProxy}}})
  try {
    await vite.listen()
    const local=vite.httpServer!.address()
    if (!local || typeof local==='string') throw new Error('test_server_unavailable')
    const status=await new Promise<number>((resolve,reject)=>{
      const pending=request({host:'127.0.0.1',port:local.port,path:'/auth/login',
        headers:{Host:'localhost:5173'},agent:false},response=>{response.resume();response.on('end',()=>resolve(response.statusCode!))})
      pending.on('error',reject);pending.end()
    })
    expect(status).toBe(302)
    expect(observedHost).toBe('localhost:5173')
  } finally {
    await vite.close()
    await new Promise<void>((resolve,reject)=>upstream.close(error=>error ? reject(error) : resolve()))
  }
})
