// Synthetic browser evidence only. Every API/auth request is intercepted.
// Requires operator-provided Playwright modules; never starts a real backend.
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import assert from 'node:assert/strict'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PBI_BROWSER_MODULES
  ? path.join(process.env.PBI_BROWSER_MODULES, 'playwright') : 'playwright')
const [baseUrl, output, mode='after'] = process.argv.slice(2)
assert(baseUrl && output && ['before','after'].includes(mode))
assert(['127.0.0.1','localhost'].includes(new URL(baseUrl).hostname))
await mkdir(output, {recursive:true})
const browser = await chromium.launch({headless:true,channel:process.env.PBI_BROWSER_CHANNEL || undefined})
const evidence=[]
try {
  for (const [label,physicalWidth,physicalHeight,zoom] of [
    ['100',1280,800,1],['125',1280,800,1.25],['150',1280,800,1.5],['narrow',390,700,1],
  ]) {
    const context = await browser.newContext({
      viewport:{width:Math.floor(physicalWidth/zoom),height:Math.floor(physicalHeight/zoom)},deviceScaleFactor:zoom,
    })
    const page=await context.newPage()
    let foreignRequests=0
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url())
      if (url.origin!==new URL(baseUrl).origin) {foreignRequests++; return route.abort()}
      if (url.pathname.startsWith('/auth/') || url.pathname.startsWith('/api/')) {
        const json = url.pathname==='/auth/session' ? {
          identity_mode:'ENTRA_BFF',authenticated:true,state:'SIGNED_IN',display_name:'合成测试账户',
          preferred_username:null,csrf_token:'synthetic-proof',expires_in:3600,
        } : url.pathname==='/api/v1/cloud/llm-profiles' ? {items:[]} : {
          failure:{code:'AUTH_FORBIDDEN',stage:'auth',retryable:false,recovery_action:'switch_account_or_contact_admin'},
          denial_reason:'cloud_execution_blocked',
        }
        return route.fulfill({status:url.pathname.includes('/catalog')?403:200,json})
      }
      return route.continue()
    })
    await page.goto(baseUrl)
    await page.locator('.local-catalog-note[role="status"]').waitFor()
    await page.getByRole('button',{name:'重新加载数据模型'}).waitFor()
    const metrics=await page.evaluate(()=>{
      const rect=selector=>{
        const r=document.querySelector(selector).getBoundingClientRect()
        return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height}
      }
      const note=rect('.local-catalog-note[role="status"]'),composer=rect('.composer'),selection=rect('.composer-selection')
      return {note,composer,selection,width:innerWidth,height:innerHeight,
        scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,
        messageCount:document.body.textContent.split('已登录；云端业务验收尚未完成，数据问答与报表暂未开放。').length-1}
    })
    assert.equal(foreignRequests,0)
    if (mode==='after') {
      assert(metrics.note.bottom<=metrics.composer.y,'status overlaps composer')
      assert(metrics.composer.bottom<=metrics.selection.y,'selection overlaps composer')
      assert(metrics.selection.bottom<=metrics.height,'footer exceeds viewport')
      assert(metrics.scrollWidth<=metrics.width,'horizontal overflow')
      assert(metrics.scrollHeight<=metrics.height,'bottom overflow')
      assert.equal(metrics.messageCount,1,'duplicated denial message')
      await page.getByRole('button',{name:'打开数据与报表选项'}).click()
      const popover=await page.locator('.add-menu').boundingBox()
      assert(popover.x>=0 && popover.x+popover.width<=metrics.width,'popover horizontal overflow')
      assert(popover.y>=0,'popover exceeds top')
      await page.getByRole('button',{name:'关闭数据与报表选项'}).click()
    }
    await page.screenshot({path:path.join(output,`${mode}-${label}.png`),fullPage:true})
    evidence.push({label,zoom,mode,foreignRequests,...metrics})
    await context.close()
  }
  await writeFile(path.join(output,`${mode}-geometry.json`),JSON.stringify(evidence,null,2)+'\n')
  console.log(JSON.stringify(evidence.map(({label,zoom,mode,scrollWidth,width,scrollHeight,height,messageCount})=>
    ({label,zoom,mode,scrollWidth,width,scrollHeight,height,messageCount}))))
} finally {await browser.close()}
