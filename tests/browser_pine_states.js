// Explicit SYNTHETIC fixtures; isolated browser storage, no model or map provider calls.
async page => {
  const url=page.url();
  if(!url.startsWith('http://127.0.0.1:')) throw new Error('Local server required');
  const context=await page.context().browser().newContext({viewport:{width:390,height:844}});
  const check=await context.newPage(), errors=[];
  check.on('pageerror',e=>errors.push(e.message));
  check.setDefaultTimeout(10000);
  const body={answer:'SYNTHETIC **准备：**合成材料 A。\n<svg onload=alert(1)>保持纯文本</svg>',result_status:'success',
    checklist:{status:'success',service_id:'synthetic:pine',items:[{id:'material-1',kind:'material',text:'SYNTHETIC 合成材料 A'}]},
    services:[{service_id:'synthetic:pine',name:'SYNTHETIC 测试事务',information_level:'procedure',
      required_materials:['SYNTHETIC 合成材料 A'],required_inputs:[],steps:[{mode:'online',instruction:'SYNTHETIC 合成步骤',place_ids:[]}],
      source_links:[{title:'SYNTHETIC 来源',url:'https://example.org/synthetic'}]}],places:[],citations:[]};
  let uploads=0, erased=0, failChat=false;
  try {
    await check.route('**/api/session',async route=>{const r=await route.fetch();await route.fulfill({response:r,json:{...await r.json(),images_enabled:true}});});
    await check.route('**/api/chat/stream',route=>route.fulfill({status:404,body:'SYNTHETIC stream unavailable'}));
    await check.route('**/api/chat',route=>route.fulfill({status:failChat?503:200,json:failChat?{message:'SYNTHETIC 服务暂不可用'}:body}));
    await check.route('**/api/attachments',route=>{
      uploads++;
      return route.fulfill({status:uploads===1?500:201,json:uploads===1?{message:'SYNTHETIC 上传失败，请重试'}:{attachment_id:'synthetic:attachment',name:'SYNTHETIC.png'}});
    });
    await check.route('**/api/attachments/*',route=>{
      if(route.request().method()==='DELETE') erased++;
      return route.fulfill({status:route.request().method()==='DELETE'?204:404,body:''});
    });
    await check.goto(url);await check.locator('.attach-button').waitFor();
    await check.locator('input[type=file]').setInputFiles({name:'SYNTHETIC.png',mimeType:'image/png',buffer:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ZkAAAAASUVORK5CYII=','base64')});
    await check.locator('.attachment-retry').click();
    await check.getByText('已就绪',{exact:true}).waitFor();
    const targets=await check.locator('.attachment-remove,.attach-button,#send').evaluateAll(xs=>xs.map(x=>{const r=x.getBoundingClientRect();return {w:r.width,h:r.height,right:r.right,bottom:r.bottom};}));
    if(targets.some(r=>r.w<44||r.h<44||r.right>390||r.bottom>844)) throw new Error('Attachment composer target/overflow');
    await check.screenshot({path:'output/playwright/taste-audit-20261021/after-synthetic-attachments-390.png'});
    await check.locator('.attachment-remove').click();
    await check.locator('.attachment-draft').waitFor({state:'detached'});
    if(uploads!==2)throw new Error('Retry count');
    await check.locator('#question').fill('SYNTHETIC 清单呈现测试');await check.locator('#send').click();
    await check.locator('.procedure-details>summary').click();
    await check.getByRole('button',{name:'＋ 加入办理清单',exact:true}).click();
    await check.locator('#handling-entry').click();
    await check.locator('.handling-row').click();
    await check.getByRole('checkbox',{name:'SYNTHETIC 合成材料 A',exact:true}).check();
    await check.getByText('准备齐了',{exact:true}).waitFor();
    await check.reload();await check.locator('#send:not([disabled])').waitFor();
    await check.locator('#handling-entry').click();await check.locator('.handling-row').click();
    if(!await check.getByRole('checkbox').isChecked())throw new Error('Saved progress lost');
    await check.getByRole('button',{name:'我已办完',exact:true}).click();
    await check.getByRole('button',{name:'撤销',exact:true}).click();
    await check.getByRole('checkbox',{name:'SYNTHETIC 合成材料 A',exact:true}).waitFor();
    await check.locator('#new-chat').click();await check.locator('#send:not([disabled])').waitFor();
    await check.locator('#handling-entry').click();await check.locator('.handling-row').waitFor();
    await check.getByRole('button',{name:'‹ 返回对话',exact:true}).click();
    failChat=true;
    await check.locator('#question').fill('SYNTHETIC 网络失败');await check.locator('#send').click();
    await check.locator('.card.error').waitFor();
    await check.locator('#send:not([disabled])').waitFor();
    failChat=false;
    await check.locator('#question').fill('SYNTHETIC 恢复');await check.locator('#send').click();
    await check.locator('.answer').waitFor();
    if(await check.locator('.conclusion svg').count())throw new Error('Model HTML executed');
    if(errors.length)throw new Error(errors.join('\n'));
    if(!erased)throw new Error('Removed attachment not erased');
    await check.setViewportSize({width:1440,height:900});
    await check.route('**/vendor/gsap-*.min.js',route=>route.abort());
    await check.reload();await check.locator('#send:not([disabled])').waitFor();
    await check.locator('#desktop-map').click();
    await check.waitForFunction(()=>Math.abs(document.querySelector('.chat').getBoundingClientRect().width-392)<1);
    await check.locator('#return-reading').click();
    await check.waitForFunction(()=>Math.abs(document.querySelector('.chat').getBoundingClientRect().width-540)<1);
    return {uploads,retry:true,remove:true,targets,savedChecklist:true,reload:true,newChat:true,completeUndo:true,networkRecovery:true,htmlInert:true,withoutGsap:true,pageErrors:errors.length};
  } finally {await context.close();}
}
