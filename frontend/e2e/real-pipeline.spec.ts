import { test, expect } from '@playwright/test';

test('real screenshot to project detail with PaddleOCR and GitHub', async ({page}) => {
  test.skip(!process.env.REAL_NETWORK, 'Opt-in: requires installed OCR models and GitHub connectivity');
  test.setTimeout(90000);
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/');
  await page.getByLabel('管理员密码').fill('e2e-test-password-123');
  await page.getByRole('button', {name:'登录工作空间'}).click();
  await page.getByRole('button', {name:'截图导入',exact:true}).click();
  await page.locator('input[type=file]').first().setInputFiles('e2e/fixtures/sample.png');
  await expect(page.locator('.batch').first()).toContainText('已完成', {timeout:60000});
  await page.getByRole('button',{name:'我的项目',exact:true}).click();
  await page.locator('.project-card').filter({hasText:'PaddleOCR'}).getByRole('button',{name:/PaddlePaddle/}).click();
  await expect(page.getByRole('heading',{name:'PaddleOCR',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'项目时间线'})).toBeVisible();
  await expect(page.getByRole('heading',{name:/来源截图/})).toBeVisible();
  await expect(page.getByRole('link',{name:/打开 GitHub/})).toHaveAttribute('href','https://github.com/PaddlePaddle/PaddleOCR');
  await page.getByLabel('个人标签').fill('OCR, 文字识别');
  await page.getByLabel('项目笔记').fill('浏览器真实流程验证笔记');
  await page.getByRole('button',{name:'保存整理'}).click();
  await expect(page.getByRole('status')).toContainText('已保存');
  await page.screenshot({path:'../data/qa/project-detail.png',fullPage:true});
  expect(errors).toEqual([]);
});
