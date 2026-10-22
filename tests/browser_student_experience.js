// Playwright CLI run-code against the local phase2 app; no inference or external navigation.
async page => {
  const url = page.url();
  if (!url.startsWith('http://127.0.0.1:')) throw new Error('Use the local verification server');
  const context = await page.context().browser().newContext({ viewport: { width: 1440, height: 1000 } });
  const check = await context.newPage();
  check.setDefaultTimeout(10000);
  const errors = [];
  check.on('pageerror', error => errors.push(error.message));
  const submit = async text => {
    await check.locator('#question').fill(text);
    await check.getByRole('button', { name: '发送', exact: true }).click();
  };
  try {
    await check.goto(url);
    if (await check.locator('a[href="/lab"], #desktop-settings, #reading-settings').count()) throw new Error('Removed controls still present');
    await submit('校园卡补办在哪里办');
    await check.getByRole('button', { name: '＋ 加入办理清单', exact: true }).waitFor();
    if (await check.locator('.decision-records, .details-request').count()) throw new Error('Removed answer controls still present');
    if (await check.locator('.card.answer h2').innerText() !== '校园卡补办') throw new Error('Wrong task title');
    if (await check.locator('details.card[open]').count()) throw new Error('Details expanded by default');
    const questionCount = await check.locator('.msg-user').count();
    await check.locator('.procedure-details>summary').click();
    if (await check.locator('.msg-user').count() !== questionCount) throw new Error('Expanding steps sent another question');
    await check.getByRole('button', { name: '＋ 加入办理清单', exact: true }).click();
    await check.locator('#handling-entry').click();
    await check.getByRole('button', { name: /校园卡补办 已准备 0\/2/ }).click();
    await check.getByRole('checkbox', { name: '本人身份证（按设备提示进行身份验证）', exact: true }).click();
    await check.getByText('已准备 1/2', { exact: true }).waitFor();
    await Promise.all([
      check.waitForNavigation({ waitUntil: 'domcontentloaded' }),
      check.locator('#new-chat').click(),
    ]);
    await check.locator('#status').getByText('已连接', { exact: true }).waitFor();
    await check.reload();
    await check.locator('#status').getByText('已连接', { exact: true }).waitFor();
    await check.locator('#handling-entry').click();
    await check.getByRole('button', { name: /校园卡补办 已准备 1\/2/ }).waitFor();
    await check.screenshot({ path: 'output/playwright/newstudent-saved-desktop.png' });
    await check.getByRole('button', { name: '‹ 返回对话', exact: true }).click();
    await submit('网络故障报修入口在哪');
    const guide = check.getByRole('link', { name: '查看办事指南：网络故障报修', exact: true });
    await guide.waitFor();
    if ((await check.locator('.card.answer').last().innerText()).includes('适用提醒')) throw new Error('Automatic scope notice still present');
    if (!(await guide.getAttribute('href')).startsWith('https://bsdt.cdut.edu.cn/')) throw new Error('Wrong guide destination');
    await check.screenshot({ path: 'output/playwright/newstudent-entry-desktop.png' });
    await check.setViewportSize({ width: 390, height: 844 });
    const geometry = await check.locator('.card.answer').evaluate(element => ({
      height: element.clientHeight, content: element.scrollHeight,
      horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
    }));
    if (geometry.height + 1 < geometry.content || geometry.horizontalOverflow) throw new Error('Mobile answer clipped: ' + JSON.stringify(geometry));
    await check.locator('.card.answer').scrollIntoViewIfNeeded();
    await check.screenshot({ path: 'output/playwright/newstudent-entry-mobile.png' });
    await submit('东区图书馆在哪');
    await check.getByRole('heading', { name: '东区图书馆', exact: true }).waitFor();
    const last = check.locator('.card.answer').last();
    if ((await last.innerText()).includes('补卡')) throw new Error('Previous service leaked into a new topic');
    if (errors.length) throw new Error(errors.join('; '));
    return { entry: true, offlinePlace: true, firstAnswerChecklist: true, foldedStepsWithoutNewQuestion: true, savedProgressAfterResetAndReload: '1/2',
      topicSwitch: true, removedSettingsAndLabEntry: true, noAutomaticScopeNotice: true,
      mobileAnswerUnclipped: geometry, widths: [1440, 390], map: 'illustration only', pageErrors: errors.length };
  } finally { await context.close(); }
}
