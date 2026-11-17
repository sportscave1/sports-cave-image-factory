const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');

(async()=>{
 const browser=await chromium.launch({channel:process.env.TEST_BROWSER||'chrome',headless:true});
 try {
  const page=await browser.newPage();
  page.setDefaultTimeout(15000);
  const errors=[];
  const requests=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/os/top-bar/**',async route=>{
   const url=new URL(route.request().url());
   requests.push(url);
   const payload=url.pathname.endsWith('/order-status')
    ? {ok:true,action_required_count:7,badge_label:'7',notification:{}}
    : {ok:true,notifications:[],results:[]};
   await route.fulfill({json:payload});
  });
  await page.goto('http://127.0.0.1:8876/?notifications_fixture=1');
  const unread=name=>page.getByRole('button',{name,exact:false});
  await unread('3 unread').waitFor();
  const gallery=page.frameLocator('iframe[title="wall_preview_inbox.wall_preview_gallery"]').first();
  await gallery.getByRole('button',{name:'View Artwork 0',exact:true}).getByText('Loading preview…').waitFor();
  await gallery.getByRole('button',{name:'View Artwork 0',exact:true}).locator('img').waitFor();
  const social=page.locator('[class*="st-key-sidebar-disclosure-social-"]');
  await social.getByRole('button',{name:'Social Media'}).click();
  await page.getByRole('button',{name:'Social overview'}).waitFor();
  assert.equal(await social.locator('.sc-orders-action-badge').count(),0);
  assert.equal(await page.locator('.st-key-sidebar-website-children').getByRole('button',{name:'Wall Preview Inbox'}).count(),1);
  await page.locator('#sc-os-notifications').click();
  await page.getByText('No new notifications',{exact:true}).waitFor();
  await page.locator('#sc-os-notifications').click();
  assert.ok(requests.every(url=>!url.searchParams.has('counts_only')));
  await gallery.getByRole('checkbox',{name:/Select Artwork 0/}).check();
  await gallery.getByRole('button',{name:'Mark as read',exact:true}).click();
  await unread('2 unread').waitFor();
  await unread('2 unread').click();
  await page.getByRole('button',{name:'Artwork 1',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.frameLocator('iframe').locator('.viewer img').waitFor();
  await page.waitForFunction(()=>document.querySelector('[role="dialog"] iframe')?.contentDocument?.querySelector('img')?.naturalWidth>0);
  await dialog.getByText('Fixture image read').waitFor();
  await dialog.getByRole('button',{name:'Close',exact:true}).click();
  await dialog.waitFor({state:'hidden'});
  await unread('1 unread').waitFor();
  await unread('1 unread').click();
  await page.getByRole('button',{name:'Mark all as read',exact:true}).click();
  await page.getByText('No unread previews',{exact:true}).waitFor();
  assert.equal(await page.locator('.st-key-sidebar-row-orders .sc-orders-action-badge').textContent(),'7');
  assert.deepEqual(errors,[]);

  await page.setContent('<iframe></iframe>');
  const frame=page.frames()[1];
  await frame.setContent(fs.readFileSync('components/wall_preview_gallery/index.html','utf8'));
  await page.evaluate(()=>{
   window.galleryEvents=[];
   addEventListener('message',event=>{
    if(event.data.type==='streamlit:setComponentValue')galleryEvents.push(event.data.value);
   });
  });
  await page.evaluate(()=>document.querySelector('iframe').contentWindow.postMessage({type:'streamlit:render',
   args:{mode:'viewer',id:'broken',image:'data:image/png;base64,broken'}},'*'));
  await page.waitForTimeout(300);
  assert.equal(await page.evaluate(()=>galleryEvents.length),0,'failed image load stays unread');
  console.log('PASS: inbox-only notifications, selected and all receipts, automatic image receipt, Orders preserved.');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
