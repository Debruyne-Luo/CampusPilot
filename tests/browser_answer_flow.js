// Explicit SYNTHETIC fixtures. Local UI regression; no model or map provider calls.
async page => {
  const url = page.url();
  if (!url.startsWith('http://127.0.0.1:')) throw new Error('Local server required');
  const results = [];
  for (const width of [1440, 390, 320]) {
    const context = await page.context().browser().newContext({viewport:{width,height:900}});
    const check = await context.newPage(), errors = [];
    check.on('pageerror', e => errors.push(e.message));
    check.setDefaultTimeout(10000);
    let requests = 0, fail = false;
    const answer = '**先做：**SYNTHETIC 先冻结合成卡，再选择自助或人工渠道。\n\n**注意：**余额大于20元是余额要求，不是工本费；费用及材料仍待核实。';
    const body = {answer,result_status:'limited',checklist:null,
      services:[{service_id:'synthetic:answer-flow',name:'SYNTHETIC 合成补办',information_level:'procedure',
        required_materials:['SYNTHETIC 合成证件'],required_inputs:null,
        steps:[{mode:'online',instruction:'SYNTHETIC 详细操作 A',condition:'SYNTHETIC 适用条件',place_ids:[]}],
        fees:['SYNTHETIC 费用待核实'],limits:['SYNTHETIC 仅限合成对象'],notes:['SYNTHETIC 来源年份待核实'],
        source_links:[{title:'SYNTHETIC 来源',url:'https://example.org/synthetic'}]}],
      decisions:[{plugin:'Jev',reason:'SECRET_DECISION',status:'success'}],places:[],
      citations:[{id:'synthetic:source',title:'SYNTHETIC 引用',url:'https://example.org/synthetic'}]};
    const event = (name, data) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
    try {
      await check.route('**/api/session', route => route.fulfill({json:{images_enabled:false}}));
      await check.route('**/api/session/reset', route => route.fulfill({json:{ok:true}}));
      await check.route('**/api/places', route => route.fulfill({json:{places:[]}}));
      await check.route('**/api/map-config', route => route.fulfill({json:{enabled:false}}));
      await check.route('**/api/chat/stream', route => {
        requests++;
        return route.fulfill({contentType:'text/event-stream',body:
          event('understanding',{intent:'办事'}) +
          event('tool_start',{tool:'search_service',label:'查找办事事项'}) +
          (fail ? '' : event('tool_end',{tool:'search_service',label:'查找办事事项',status:'success'}) +
            event('composing',{}) + event('answer_delta',{text:answer}) + event('final',body))});
      });
      await check.goto(url);
      await check.locator('#send:not([disabled])').waitFor();
      await check.locator('#question').fill('SYNTHETIC 首次办理问题');
      await check.locator('#send').click();
      await check.locator('.answer').waitFor();
      await check.locator('#send:not([disabled])').waitFor();
      const reading = await check.locator('.answer').evaluate(el => {
        const r = el.getBoundingClientRect(), viewport = el.parentElement.getBoundingClientRect();
        return {top:r.top - viewport.top,visible:r.top < viewport.bottom && r.bottom > viewport.top};
      });
      if (!reading.visible || reading.top < -1) throw new Error(`Answer heading scrolled away: ${JSON.stringify({width,reading})}`);
      const presentation = await check.locator('#thread').evaluate(thread => ({
        processLast:thread.lastElementChild.matches('.plan-host'),
        processClosed:!thread.querySelector('.plan').open,
        detailsClosed:!thread.querySelector('.procedure-details').open,
        paragraphs:thread.querySelectorAll('.answer-paragraph').length,
        labels:[...thread.querySelectorAll('.conclusion strong')].map(x=>x.textContent),
        secret:/Jev|SECRET_DECISION|执行记录|查看材料与步骤/.test(thread.textContent),
        body:thread.querySelector('.conclusion').textContent,
      }));
      if (!presentation.processLast || !presentation.processClosed || !presentation.detailsClosed ||
          presentation.paragraphs !== 2 || presentation.labels.length !== 2 || presentation.secret ||
          !presentation.body.includes('不是工本费')) throw new Error(JSON.stringify(presentation));
      const add = check.getByRole('button',{name:'＋ 加入办理清单',exact:true});
      await add.scrollIntoViewIfNeeded();
      const geometry = await add.evaluate(el => {
        const r=el.getBoundingClientRect(), parent=el.parentElement;
        return {width:r.width,height:r.height,left:r.left,right:r.right,overflow:parent.scrollWidth>parent.clientWidth+1};
      });
      if (geometry.left<0 || geometry.right>width || geometry.height<44 || geometry.overflow) throw new Error(JSON.stringify({width,geometry}));
      await check.locator('.answer').scrollIntoViewIfNeeded();
      await check.screenshot({path:`output/playwright/answer-experience-${width}.png`});
      await check.locator('.procedure-details>summary').click();
      await check.locator('.procedure-details[open]').waitFor();
      const details = await check.locator('.procedure-details').textContent();
      for (const text of ['合成证件','详细操作 A','适用条件','费用待核实','来源年份待核实','部分准备要求待核实']) {
        if (!details.includes(text)) throw new Error(`Missing ${text}`);
      }
      if (requests!==1) throw new Error('Expanding details made another model request');
      await add.click();
      await check.getByRole('button',{name:'已加入 · 查看清单',exact:true}).waitFor();
      await check.getByRole('button',{name:'已加入 · 查看清单',exact:true}).click();
      await check.getByRole('checkbox',{name:'SYNTHETIC 合成证件',exact:true}).check();
      await check.reload();
      await check.locator('#send:not([disabled])').waitFor();
      await check.locator('#handling-entry').click();
      await check.locator('.handling-row').click();
      if (!await check.getByRole('checkbox',{name:'SYNTHETIC 合成证件',exact:true}).isChecked()) throw new Error('Progress lost');
      await check.getByRole('button',{name:'‹ 返回清单',exact:true}).click();
      await check.getByRole('button',{name:'‹ 返回对话',exact:true}).click();
      fail = true;
      await check.locator('#question').fill('SYNTHETIC 断流'); await check.locator('#send').click();
      await check.locator('.error').waitFor();
      const failed = await check.locator('#thread').evaluate(thread => ({
        processLast:thread.lastElementChild.matches('.plan-host'),closed:!thread.querySelector('.plan').open,
        running:thread.querySelectorAll('.step.running').length,
      }));
      if (!failed.processLast || !failed.closed || failed.running) throw new Error(JSON.stringify(failed));
      if (errors.length) throw new Error(errors.join('\n'));
      results.push({width,presentation,reading,geometry,firstAnswerSave:true,progressRetained:true,interruptedStream:failed,pageErrors:0});
    } finally {await context.close();}
  }
  return results;
}
