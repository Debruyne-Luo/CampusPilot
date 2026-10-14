// Run via playwright-cli run-code --filename. All school-like content is SYNTHETIC.
async (page) => {
  const showChat=async()=>{if(await page.locator('#return-reading').isVisible()){await page.locator('#return-reading').click();await page.waitForTimeout(350);}for(let i=0;i<3&&await page.locator('#handling-panel').isVisible();i++)await page.locator('.handling-back').first().click();};
  const check = (ok, label) => { if (!ok) throw new Error(label); };
  const errors = [], checks = [];
  page.on('pageerror', e => errors.push(e.message));
  const url = 'http://127.0.0.1:8875/';
  const key = 'campuspilot:handling:v1';
  const place = {place_id:'synthetic:place:a',name:'合成测试地点 A',category:'service',hotspot:true,position:{longitude:104.14,latitude:30.67,coordinate_system:'GCJ02'}};
  const body = {
    result_status:'success',answer:'合成测试回答：先核对适用条件，再准备材料。以下内容仅用于前端验证，不是学校办事指南。',
    checklist:{status:'success',service_id:'synthetic:service:a',items:[{id:'material-a',kind:'material',text:'合成材料 A'},{id:'input-b',kind:'input',text:'合成信息 B'}]},
    services:[{service_id:'synthetic:service:a',name:'合成测试事务',audience:'合成测试对象',required_materials:['合成材料 A'],required_inputs:['合成信息 B'],entry_points:['合成入口'],limits:['合成限制，不代表学校规则'],fees:[],availability:[],source_links:[{title:'合成来源（非学校文件）',url:'https://example.org/synthetic'}],steps:[{mode:'online',instruction:'合成线上渠道',condition:'合成适用条件',place_ids:[]},{mode:'in_person',instruction:'合成窗口渠道，可选择一种方式',condition:'合成线下适用条件',place_ids:[place.place_id]}]}],
    places:[place],citations:[{id:'synthetic:evidence:a',title:'合成来源（非学校文件）',publisher:'测试发布者',date:'2026-01-01',audience:'合成测试对象',url:'https://example.org/synthetic'}]
  };
  let mode = 'success', requestCount = 0;
  const event = (name, data) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
  await page.route('**/api/session', r => r.fulfill({json:{configured:true}}));
  await page.route('**/api/places', r => r.fulfill({json:{places:[place]}}));
  await page.route('**/api/map-config', r => r.fulfill({json:{configured:false}}));
  await page.route('**/api/chat', r => mode === 'network' ? r.abort() : r.fulfill({json:body}));
  await page.route('**/api/chat/stream', async r => {
    requestCount++;
    check(Object.keys(r.request().postDataJSON()).join(',') === 'message', 'only message sent');
    if (mode === 'network') return r.abort();
    if (mode === 'fallback') return r.fulfill({status:404,json:{}});
    let events = event('understanding',{intent:'办事'}) + event('plan',{steps:[{tool:'synthetic_lookup',label:'查询合成资料'}]}) + event('tool_start',{tool:'synthetic_lookup',label:'查询合成资料'}) + event('composing',{});
    events += event('answer_delta',{text:'合成未完成回答'});
    if (mode !== 'interrupted') events += event('final', mode === 'empty' ? {answer:'合成测试：没有找到依据，请补充问题。',result_status:'empty',places:[],citations:[]} : body);
    return r.fulfill({contentType:'text/event-stream',body:events});
  });
  const shot = async name => {await page.waitForTimeout(400);
    if (name === 'rounded-answer-1440') await page.locator('#handling-toast').waitFor({state:'hidden',timeout:12000});
    return page.screenshot({path:`output/playwright/${name}.png`,animations:'disabled'});
  };
  const loaded = () => page.locator('#send:not([disabled])').waitFor();
  const send = async text => {await page.locator('#question').fill(text);await page.locator('#send').click();await page.locator('#thread .answer, #thread .error').last().waitFor();await loaded();};
  const fits = async label => {
    const metrics = await page.evaluate(() => ({w:innerWidth,doc:document.documentElement.scrollWidth,app:document.querySelector('.app').getBoundingClientRect().toJSON(),chat:document.querySelector('.chat').getBoundingClientRect().toJSON()}));
    check(metrics.doc <= metrics.w, `${label}: page overflow`); checks.push(label);
  };
  await page.setViewportSize({width:1440,height:900}); await page.goto(url); await loaded();
  await page.evaluate(() => {localStorage.removeItem('campuspilot:handling:v1');localStorage.removeItem('campuspilot:desktop:v1');});
  await page.reload();await loaded();await fits('1440 home');await shot('rounded-home-synthetic-1440');
  await page.setViewportSize({width:1920,height:900});await fits('1920 home');
  check(await page.locator('.chat').evaluate(e=>e.getBoundingClientRect().width) === 540,'released reading column retained');
  await page.setViewportSize({width:1440,height:900});
  await page.locator('#handling-entry').click();await shot('rounded-checklist-empty-1440');
  check(await page.locator('#chat-form').isHidden(),'composer hidden in list');
  await showChat();
  await send('合成测试问题');check(await page.locator('.handling-add').count()===1,'saveable answer');
  check(await page.evaluate(()=>document.body.dataset.workspace!=='map'),'answer does not enter map');await page.locator('#thread').evaluate(e=>e.scrollTop=0);await shot('rounded-answer-1440');
  await page.locator('.citations').filter({hasText:'引用来源'}).locator('summary').first().click();
  await page.locator('.citations').filter({hasText:'引用来源'}).locator('details summary').click();
  await shot('rounded-evidence-1440');
  await page.locator('.handling-add').click();
  check((await page.locator('.handling-add').innerText())==='查看清单','added state');
  await page.locator('#handling-entry').click();await shot('rounded-checklist-list-1440');
  await page.locator('.handling-row').click();await page.locator('.handling-items input').first().check();
  await shot('rounded-checklist-detail-1440');
  const saved = await page.evaluate(k=>localStorage.getItem(k),key);
  check(JSON.parse(saved).tasks[0].checked.length===1,'checked persisted');
  await page.reload();await loaded();await page.locator('#handling-entry').click();await page.locator('.handling-row').click();
  check(await page.locator('.handling-items input').first().isChecked(),'released schema survives reload');
  await page.locator('.handling-primary').click();await page.locator('#handling-toast button').click();
  check(await page.locator('.handling-items input').first().isChecked(),'undo restores progress');
  await page.locator('.handling-place-actions button').first().click();
  check((await page.locator('#place-card').innerText()).includes(place.name),'checklist to map');await shot('rounded-map-1440');await page.locator('#return-reading').click();
  await page.locator('#desktop-settings').click();await page.locator('#reading-size').selectOption('large');await page.locator('#reduce-motion').check();
  check(await page.evaluate(()=>getComputedStyle(document.querySelector('.handling-items li')).fontSize)==='18px','reading preference applies');
  await shot('rounded-settings-1440');await page.keyboard.press('Escape');
  check(await page.locator('#reading-settings').isHidden(),'settings Escape');
  await page.locator('#new-chat').click();await loaded();await page.locator('#handling-entry').click();
  check(await page.locator('.handling-row').count()===1,'new conversation keeps saved tasks');
  await page.setViewportSize({width:1280,height:900});await fits('1280 list');await shot('rounded-checklist-list-1280');
  await page.locator('.handling-row').click();await fits('1280 detail');await shot('rounded-checklist-detail-1280');
  await showChat();await shot('rounded-home-1280');
  await page.locator('#desktop-settings').click();await page.locator('#reading-size').selectOption('normal');await page.locator('#reduce-motion').uncheck();await page.keyboard.press('Escape');
  mode='interrupted';await send('合成中断测试');
  check((await page.locator('#thread').innerText()).includes('尚未核对引用'),'partial answer preserved');
  await shot('rounded-interrupted-1280');
  await page.locator('.error button').click();check(await page.locator('#question').inputValue()==='合成中断测试','retry restores question');
  check(await page.locator('#send').isEnabled(),'send recovered after interruption');
  mode='network';await send('合成断网测试');check((await page.locator('.error').last().innerText()).includes('网络连接失败'),'fallback network failure recovered');
  mode='empty';await send('合成无依据测试');await shot('rounded-no-evidence-1280');
  mode='fallback';await send('合成非流式回退测试');check(await page.locator('.answer').count()>=2,'fallback response rendered');
  // Existing saved v1 data is reused at every width, not reconstructed by desktop code.
  for (const width of [1100,390,320]) {
    await page.setViewportSize({width,height:width<500?844:900});
    await page.locator('#handling-entry').click();await fits(`${width} list`);await page.locator('.handling-row').click();
    await fits(`${width} detail`);await shot(`rounded-regression-detail-${width}`);
    check(await page.locator('#desktop-settings').isHidden(),'desktop chrome hidden on narrow viewport');
    check(await page.evaluate(()=>getComputedStyle(document.querySelector('.handling-items li')).fontSize)==='14px','mobile typography unchanged');
    await page.keyboard.press('Escape');await page.keyboard.press('Escape');
    await shot(`rounded-regression-chat-${width}`);
  }
  check(errors.length===0,`page errors: ${errors.join(';')}`);
  return {checks,requestCount,pageErrors:errors.length,savedVersion:JSON.parse(saved).version,passed:true};
}
