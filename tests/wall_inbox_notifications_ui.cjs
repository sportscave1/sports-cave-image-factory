const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:process.env.TEST_BROWSER||'chrome',headless:true});
 const page=await browser.newPage();page.setDefaultTimeout(15000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const ids=[1,2,3].map(i=>'00000000-0000-0000-0000-'+String(i).padStart(12,'0'));
 const seen=new Set();let polls=0,arrived=false;
 await page.exposeFunction('fixtureSeen',id=>seen.add(id));
 await page.addInitScript(()=>addEventListener('message',event=>{
   if(event.data?.type==='sc:wall-inbox-seen')void window.fixtureSeen(event.data.id);
 }));
 await page.route('**/api/os/top-bar/**',async route=>{
   let payload={ok:true,items:[],results:[]};
   if(route.request().url().endsWith('/notifications')){
     polls++;const unread=ids.slice(0,arrived?3:1).filter(id=>!seen.has(id));
     payload={ok:true,wall_unread_count:unread.length,notifications:unread.map((id,i)=>({
       title:'New image received in Wall Inbox.',subtitle:'Fixture '+id,
       route_key:'social_media_wall_previews',wall_preview_id:id}))};
   }else if(route.request().url().endsWith('/order-status'))payload={ok:true,action_required_count:7,badge_label:'7',notification:{}};
   await route.fulfill({json:payload});
 });
 await page.goto('http://127.0.0.1:8876/?notifications_fixture=1');
 const parent=page.locator('[class*="st-key-sidebar-disclosure-social-"]');
 const badge=parent.locator('.sc-orders-action-badge');
 await badge.getByText('1',{exact:true}).waitFor();assert.equal(seen.size,0);
 for(const expanded of [true,false,true]){
   await parent.getByRole('button').click();
   await page.locator('.st-key-sidebar-disclosure-social-'+(expanded?'open':'closed')).waitFor();
   await badge.getByText('1',{exact:true}).waitFor();
   assert.equal(await badge.count(),1);
   assert.equal(await page.locator('.st-key-sidebar-row-social_media_wall_previews .sc-orders-action-badge').count(),0);
   assert.equal(seen.size,0,'opening or closing Social Media must not mark previews read');
 }
 const initialPolls=polls;
 arrived=true;
 await page.waitForFunction(()=>document.getElementById('sports-cave-os-top-bar')?.dataset.installStage==='ready');
 await page.waitForTimeout(31000);assert.ok(polls>initialPolls,'existing heartbeat automatically refreshed notifications');
 await badge.getByText('3',{exact:true}).waitFor();
 for(const [width,height] of [[1440,900],[768,1024],[390,844],[320,568]]){
   await page.setViewportSize({width,height});await page.locator('#sc-os-notifications').click();
   await page.getByRole('button').filter({hasText:'New image received in Wall Inbox.'}).first().waitFor();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await page.locator('#sc-os-notifications').click();
 }
 await page.setViewportSize({width:1440,height:900});
 for(let index=0;index<3;index++){
   await page.locator('#sc-os-notifications').click();
   await page.locator('.sc-os-notification-item').first().click();
   const dialog=page.getByRole('dialog');await dialog.waitFor();
   await dialog.frameLocator('iframe').locator('.viewer img').waitFor();
   // The receipt reaches the shared shell immediately, without waiting 30 seconds.
   const expected=2-index;
   if(expected)await badge.getByText(String(expected),{exact:true}).waitFor({timeout:10000});
   else await badge.waitFor({state:'detached',timeout:10000});
   assert.equal(seen.size,index+1);
   await page.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});
 }
 await page.locator('#sc-os-notifications').click();await page.getByText('No new notifications',{exact:true}).waitFor();
 assert.equal(await page.locator('.st-key-sidebar-row-orders .sc-orders-action-badge').textContent(),'7');
 assert.deepEqual(errors,[]);
 // Test the actual image-load acknowledgement independently of the Streamlit fixture.
 await page.setContent('<iframe></iframe>');
 const frame=page.frames()[1];await frame.setContent(fs.readFileSync('components/wall_preview_gallery/index.html','utf8'));
 await page.evaluate(()=>{window.galleryEvents=[];addEventListener('message',e=>{if(e.data.type==='streamlit:setComponentValue')galleryEvents.push(e.data.value)})});
 await page.evaluate(()=>document.querySelector('iframe').contentWindow.postMessage({type:'streamlit:render',args:{mode:'viewer',id:'broken',image:'data:image/png;base64,broken'}},'*'));
 await page.waitForTimeout(300);assert.equal(await page.evaluate(()=>galleryEvents.length),0,'failed image load stays unread');
 await browser.close();console.log('PASS: shared heartbeat, 3→2→1→0, deep links, immediate clearing, Orders preserved, four viewport sizes, failed image stays unread.');
})().catch(error=>{console.error(error);process.exitCode=1});
