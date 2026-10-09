// Additional local browser checks. Business responses and failure injections are SYNTHETIC.
async (page) => {
  if (page.url() === 'about:blank') await page.goto('http://127.0.0.1:8767/');
  const check = (condition, message) => {if (!condition) throw new Error(message);};
  let calls = 0;
  let releaseLoader;
  const loaderGate = new Promise((resolve) => {releaseLoader = resolve;});
  await page.route('**/loader.js', async (r) => {await loaderGate; await r.continue();});
  await page.route('**/api/session', async (r) => r.fulfill({json: {configured: true}}));
  await page.route('**/api/chat', async (r) => {
    calls++;
    const data = await page.evaluate(() => ({place: places.find((p) => p.place_id === 'cdut:place:east-library'), service: catalogue.services.find((s) => s.service_id === 'cdut:service:campus-card-replacement')}));
    const body = r.request().postDataJSON();
    check(Object.keys(body).join(',') === 'message', 'coordinates must not enter chat');
    await r.fulfill({json: calls === 1 ? {result_status: 'success', answer: 'SYNTHETIC answer', teachers: [{teacher_id: 'synthetic:faculty', name: 'SYNTHETIC Faculty', department: 'SYNTHETIC', office: 'SYNTHETIC ROOM', place_id: data.place.place_id, notes: [], profile_url: 'https://example.com'}], services: [], places: [data.place]} : {result_status: 'success', answer: 'SYNTHETIC service answer', teachers: [], services: [data.service], places: []}});
  });
  await page.reload();
  await page.waitForFunction(() => places.length === 20);
  await page.getByRole('textbox', {name: '搜索校园地点、教师或询问办事问题'}).fill('珙桐');
  await page.getByRole('button', {name: '开始查询'}).click();
  await page.getByRole('button', {name: '查看路线', exact: true}).click();
  await page.getByLabel('校园地点起点', {exact: true}).selectOption('cdut:place:east-library');
  await page.getByText('正在等待地图…', {exact: true}).waitFor();
  releaseLoader();
  await page.getByText('参考路线 · 步行至建筑', {exact: true}).waitFor({timeout: 30000});
  await page.unroute('**/loader.js');
  await page.getByRole('button', {name: '查看全部地点', exact: true}).click();
  await page.locator('[data-search-mode="assistant"]').click();
  await page.getByRole('textbox', {name: '搜索校园地点、教师或询问办事问题'}).fill('SYNTHETIC find faculty');
  await page.getByRole('button', {name: '开始查询'}).click();
  await page.locator('#journey-card').getByText('SYNTHETIC ROOM', {exact: true}).waitFor();
  await page.getByRole('button', {name: '返回对话', exact: true}).click();
  await page.locator('#assistant').waitFor({state: 'visible'});
  check(calls === 1, 'return must not re-send');
  check(await page.locator('#messages .message').count() === 2, 'chat history retained');
  await page.getByRole('textbox', {name: '你的办事问题'}).fill('SYNTHETIC replacement');
  await page.getByRole('button', {name: '发送', exact: false}).click();
  await page.locator('#journey-card').getByRole('button', {name: '完整办理步骤'}).waitFor();
  check(await page.locator('#journey-card').getByText('地图位置暂未收录。').isVisible(), 'service without destination');
  check(await page.locator('#journey-card').getByText('SYNTHETIC ROOM').count() === 0, 'old teacher context cleared');
  // A synthetic upstream error leaves the destination and retry control intact.
  await page.getByRole('button', {name: '查看全部地点', exact: true}).click();
  await page.locator('[data-search-mode="places"]').click();
  await page.getByRole('textbox', {name: '搜索校园地点、教师或询问办事问题'}).fill('珙桐');
  await page.getByRole('button', {name: '开始查询'}).click();
  const frame = page.frames().find((f) => f.url().endsWith('/map-view'));
  await frame.evaluate(() => {window.savedWalking = AMap.Walking; AMap.Walking = function() {this.search = (_a, _b, callback) => callback('no_data', 'SYNTHETIC');};});
  await page.getByRole('button', {name: '查看路线', exact: true}).click();
  await page.getByLabel('校园地点起点', {exact: true}).selectOption('cdut:place:east-library');
  await page.getByText('暂未取得步行路线，请更换起点或重试。', {exact: true}).waitFor();
  check(await frame.evaluate(() => map.getAllOverlays('polyline').length === 0), 'failure must not draw a substitute');
  await frame.evaluate(() => {AMap.Walking = window.savedWalking; delete window.savedWalking;});
  await page.getByRole('button', {name: '重试路线', exact: true}).click();
  await page.getByText('参考路线 · 步行至建筑', {exact: true}).waitFor({timeout: 25000});
  await page.unroute('**/api/session');
  await page.unroute('**/api/chat');
  await page.evaluate(() => {window.journeyFailureReport = {passed: true, scenarios: ['map delayed readiness', 'chat auto collapse', 'chat no location payload', 'history retained without resend', 'service without coordinates', 'no stale teacher', 'no route', 'retry real route']};});
}
