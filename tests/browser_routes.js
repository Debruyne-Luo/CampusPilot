// Run with playwright-cli run-code --filename tests/browser_routes.js against the local map server.
// Real provider routes use public campus points. All injected business replies are SYNTHETIC.
async (page) => {
  if (page.url() === 'about:blank') await page.goto('http://127.0.0.1:8767/classic');
  const check = (value, label) => { if (!value) throw new Error(label); };
  const search = async (q) => {
    await page.getByRole('button', {name: '找地点', exact: true}).click();
    await page.getByRole('textbox', {name: '搜索校园地点、教师或询问办事问题'}).fill(q);
    await page.getByRole('button', {name: '开始查询'}).click();
  };
  await page.setViewportSize({width: 1366, height: 900});
  await page.reload();
  await page.waitForFunction(() => mapState === 'ready');
  await search('珙桐');
  await page.getByRole('button', {name: '查看路线', exact: true}).click();
  await page.getByLabel('校园地点起点', {exact: true}).selectOption('cdut:place:east-library');
  await page.getByText('参考路线 · 步行至建筑', {exact: true}).waitFor({timeout: 25000});
  const desktop = await page.evaluate(() => ({summary: document.querySelector('.route-summary').textContent, width: innerWidth}));
  check(desktop.width === 1366, 'desktop viewport');
  const frame = page.frames().find((f) => f.url().endsWith('/map-view'));
  check(await frame.evaluate(() => map.getAllOverlays('polyline').some((line) => line.getPath().length > 2)), 'real provider geometry');
  await page.screenshot({path: 'output/playwright/route-desktop.png'});
  await page.setViewportSize({width: 390, height: 844});
  // Resize and opening step details both change the usable map area.
  await page.getByText('分步指引', {exact: true}).click();
  check(await page.locator('.route-instructions li').count() > 0, 'walking instructions');
  await page.getByText('分步指引', {exact: true}).click();
  await page.screenshot({path: 'output/playwright/route-mobile.png'});
  check(await page.evaluate(() => innerWidth === 390 && document.documentElement.scrollWidth <= 390), 'mobile overflow');
  await page.getByRole('button', {name: '更换起点', exact: true}).click();
  await page.evaluate(() => {window.realGeolocation = navigator.geolocation.getCurrentPosition; navigator.geolocation.getCurrentPosition = (_ok, fail) => fail({code: 1});});
  await page.getByRole('button', {name: '我的位置', exact: true}).click();
  await page.getByText('无法获取当前位置，请选择校园地点或地图选点。', {exact: true}).waitFor();
  await page.evaluate(() => {navigator.geolocation.getCurrentPosition = window.realGeolocation; delete window.realGeolocation;});
  await page.getByRole('button', {name: '地图选点', exact: true}).click();
  await frame.locator('#map-view').click({position: {x: 155, y: 150}});
  await page.getByText('参考路线 · 步行至建筑', {exact: true}).waitFor({timeout: 25000});
  await page.getByRole('button', {name: '退出路线', exact: true}).click();
  await frame.waitForFunction(() => map.getAllOverlays('polyline').length === 0);
  await page.getByRole('button', {name: '查看全部地点', exact: true}).click();
  await page.getByRole('button', {name: '餐厅', exact: true}).click();
  await page.locator('[data-search-mode="teachers"]').click();
  await page.getByRole('textbox', {name: '搜索校园地点、教师或询问办事问题'}).fill('王洪辉');
  await page.getByRole('button', {name: '开始查询'}).click();
  await page.locator('#journey-card').getByText('网安楼204室', {exact: true}).waitFor();
  check(await page.locator('#journey-card').getByText('地图位置暂未收录。', {exact: true}).isVisible(), 'unknown teacher location');
  check(await page.getByRole('button', {name: '查看路线', exact: true}).count() === 0, 'unknown destination cannot route');
  check(await page.locator('#place-category').inputValue() === '', 'old category cleared');
  // Two synthetic teachers in one building must still require disambiguation.
  await page.route('**/api/teachers?*', async (r) => r.fulfill({json: {teachers: [1, 2].map((n) => ({teacher_id: 'synthetic:' + n, name: 'SYNTHETIC Faculty ' + n, department: 'SYNTHETIC', office: 'SYNTHETIC ROOM', place_id: 'cdut:place:east-library', notes: [], profile_url: 'https://example.com/synthetic'}))}}));
  await page.locator('[data-search-mode="teachers"]').click();
  await page.getByRole('textbox', {name: '搜索校园地点、教师或询问办事问题'}).fill('SYNTHETIC');
  await page.getByRole('button', {name: '开始查询'}).click();
  await page.getByText('请选择你要找的结果', {exact: true}).waitFor();
  check(await page.getByRole('button', {name: '查看路线', exact: true}).count() === 0, 'shared building is not unique teacher');
  await page.getByRole('button', {name: 'SYNTHETIC Faculty 1 · SYNTHETIC · SYNTHETIC ROOM'}).click();
  await page.getByRole('button', {name: '查看路线', exact: true}).waitFor();
  await page.unroute('**/api/teachers?*');
  // Delayed and failed provider callbacks must not resurrect a route after exit.
  await frame.evaluate(() => {window.savedWalking = AMap.Walking; AMap.Walking = function() {this.search = (_a, _b, callback) => {window.delayedRoute = callback;};};});
  await page.getByRole('button', {name: '查看路线', exact: true}).click();
  await page.getByLabel('校园地点起点', {exact: true}).selectOption('cdut:place:gongtong-dining');
  await frame.waitForFunction(() => typeof window.delayedRoute === 'function');
  await page.getByRole('button', {name: '退出路线', exact: true}).click();
  await frame.evaluate(() => {window.delayedRoute('error', 'SYNTHETIC failure'); AMap.Walking = window.savedWalking; delete window.delayedRoute; delete window.savedWalking;});
  check(await page.locator('.route-box').count() === 0, 'stale provider callback ignored');
  await page.evaluate(() => {window.routeBrowserReport = {passed: true, scenarios: ['real route', 'desktop', 'mobile', 'directions', 'denied geolocation', 'map origin', 'exit cleanup', 'teacher without position', 'old category', 'shared building ambiguity', 'stale provider callback']};});
}
