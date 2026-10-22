// Synthetic layout evidence. Every API/auth request is intercepted, no real backend.
import {createRequire} from 'node:module'
import {mkdir,writeFile} from 'node:fs/promises'
import path from 'node:path'
import assert from 'node:assert/strict'
const require=createRequire(import.meta.url)
const {chromium}=require(process.env.PBI_BROWSER_MODULES ? path.join(process.env.PBI_BROWSER_MODULES,'playwright') : 'playwright')
const [baseUrl,output]=process.argv.slice(2)
assert(['localhost','127.0.0.1'].includes(new URL(baseUrl).hostname))
await mkdir(output,{recursive:true})
const browser=await chromium.launch({headless:true,channel:process.env.PBI_BROWSER_CHANNEL || undefined})
const evidence=[]
try {
  for(const width of [1280,390]) {
    const context=await browser.newContext({viewport:{width,height:900}})
    const page=await context.newPage()
    let failResources=false,foreign=0
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url())
      if(url.origin!==new URL(baseUrl).origin){foreign++;return route.abort()}
      if(!url.pathname.startsWith('/api/') && !url.pathname.startsWith('/auth/'))return route.continue()
      const json=url.pathname==='/auth/session' ? {identity_mode:'ENTRA_BFF',authenticated:true,state:'SIGNED_IN',display_name:'Synthetic',csrf_token:'synthetic',expires_in:3600}
        : url.pathname.endsWith('/status') ? {selected_model_key:null,conversation_id:null,generation:0,execution_ready:false,blockers:[]}
        : url.pathname.endsWith('/catalog') ? {product_mode:true,persistence_enabled:true,status:'ready',items:[]}
        : url.pathname.endsWith('/llm-profiles') ? {items:[{profile_key:'deepseek',display_name:'DeepSeek',model:'synthetic',available:true,default:true}]}
        : failResources && /\/(history|reports)$/.test(url.pathname) ? {failure:{code:'PERSISTENCE_UNAVAILABLE',stage:'internal',retryable:true,recovery_action:'retry'}}
        : {items:[],partial:false}
      await route.fulfill({status:failResources && /\/(history|reports)$/.test(url.pathname)?503:200,json})
    })
    await page.goto(baseUrl)
    await page.locator('.composer-anchor').waitFor()
    const before=await page.locator('.chat-main').boundingBox()
    failResources=true
    await page.reload()
    await page.locator('.sidebar-resource-status').first().waitFor({state:'attached'})
    assert.deepEqual(await page.locator('.chat-main').boundingBox(),before)
    assert.equal(await page.locator('.chat-main .sidebar-resource-status').count(),0)
    assert.equal(await page.locator('.sidebar-resource-status').count(),2)
    for(const lines of [1,3,5]) {
      await page.locator('.cloud-catalog-status p').evaluate((el,n)=>{el.style.whiteSpace='pre';el.textContent=Array(n).fill('Synthetic status').join('\n')},lines)
      await page.locator('.composer-selection').evaluate((el,n)=>{el.style.whiteSpace='pre';el.textContent=Array(n).fill('Synthetic warning').join('\n')},lines)
      const composer=await page.locator('.composer').boundingBox()
      await page.getByRole('button',{name:'打开数据与报表选项'}).click()
      const add=await page.locator('.add-menu').boundingBox()
      assert(Math.abs(composer.y-add.y-add.height-8)<1)
      assert(Math.abs(composer.x-add.x)<1)
      await page.getByRole('button',{name:'DeepSeek',exact:true}).click()
      const model=await page.locator('.model-menu').boundingBox()
      assert(Math.abs(composer.y-model.y-model.height-8)<1)
      assert(Math.abs(composer.x+composer.width-model.x-model.width)<1)
      assert.equal(add.width,model.width)
      assert(add.x>=0 && model.x>=0 && add.x+add.width<=width && model.x+model.width<=width)
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width)
      await page.screenshot({path:path.join(output,`${width}-${lines}.png`),fullPage:true})
      evidence.push({width,lines,offset:8,add,model,composer,resourceFailureLayoutStable:true})
      await page.keyboard.press('Escape')
    }
    assert.equal(foreign,0)
    await context.close()
  }
  await writeFile(path.join(output,'geometry.json'),JSON.stringify(evidence,null,2))
  console.log('PASS: desktop/mobile, 1/3/5 lines, equal width, 8px offset, isolated resource failures')
} finally {await browser.close()}
