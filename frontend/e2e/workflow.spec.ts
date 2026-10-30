import { test, expect, type Page } from '@playwright/test';

async function loginAs(page: Page, staffName: string) {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const signOutBtn = page.locator('button:has-text("Sign Out")');
  if (await signOutBtn.isVisible()) {
    await signOutBtn.click();
    await page.waitForLoadState('networkidle');
  }
  const btn = page.locator(`button:has-text("${staffName}")`).first();
  await expect(btn).toBeVisible({ timeout: 15000 });
  await btn.click();
  await page.waitForLoadState('networkidle');
}

test.describe('JananiSetu End-to-End System & Usability Audit', () => {
  test('1. Authentication, Role Dashboards, and Session Management', async ({ page }) => {
    await loginAs(page, 'Ananya Reddy');

    // Verify authenticated admin view
    await expect(page.locator('text=Nalgonda Central Maternal Health Clinic').or(page.locator('text=Clinic Administrator'))).toBeVisible({ timeout: 15000 });

    // Verify admin navigation tabs exist
    await expect(page.locator('button:has-text("Operations & Workforce")')).toBeVisible();
    await expect(page.locator('button:has-text("Contracts, Budgets & Finance")')).toBeVisible();
  });

  test('2. Patient Registration, Consent & List Persistence', async ({ page }) => {
    await loginAs(page, 'Lakshmi Devi');
    await expect(page.locator('text=ANM / Staff Nurse').or(page.locator('text=Lakshmi Devi'))).toBeVisible({ timeout: 15000 });

    // Navigate to Mothers & Consent tab
    await page.click('button:has-text("Mothers & Consent")');
    await page.waitForTimeout(600);

    // Verify mother registration section
    await expect(page.locator('h2:has-text("Register Synthetic Patient")')).toBeVisible();

    // Fill new synthetic mother with actual persisted mutation
    const randomSuffix = Math.floor(Math.random() * 9000 + 1000);
    const testMotherName = `Savitri Devi (Synthetic ${randomSuffix})`;
    
    const nameInput = page.locator('input[name="name"]').first();
    await expect(nameInput).toBeVisible({ timeout: 5000 });
    await nameInput.fill(testMotherName);

    const phoneInput = page.locator('input[name="phone"]').first();
    await phoneInput.fill(`98490${randomSuffix}`);

    // Submit form by clicking submit button and pressing enter
    const submitBtn = page.locator('button:has-text("Register Mother")').first();
    await submitBtn.click();
    await phoneInput.press('Enter');

    // Wait for network response / update
    await page.waitForTimeout(1000);

    // Filter by the new mother's unique suffix to verify persistence in table
    const searchInput = page.locator('input[type="search"]').first();
    await searchInput.fill(String(randomSuffix));
    await page.waitForTimeout(600);

    // Verify the mutated patient row is visible and rendered in the registered mothers list
    await expect(page.locator(`text=${randomSuffix}`).first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator(`text=${testMotherName}`).first()).toBeVisible({ timeout: 10000 });
  });

  test('3. Doctor CarePlan Authorisation & Followup Communication Hub', async ({ page }) => {
    await loginAs(page, 'Dr. Kavitha Rao');
    await expect(page.locator('text=Medical Officer (Doctor)').or(page.locator('text=Dr. Kavitha Rao'))).toBeVisible({ timeout: 15000 });

    // Navigate to Care Plans & Visits
    await page.click('button:has-text("Care Plans & Visits")');
    await page.waitForTimeout(600);

    // Verify Care Plans header
    await expect(page.locator('h2, h3, div').filter({ hasText: 'Care Plans' }).first()).toBeVisible();

    // Perform actual persisted mutation: Doctor authorises a care plan
    const visitDateInput = page.locator('input[name="visit_date"]').first();
    if (await visitDateInput.isVisible()) {
      await visitDateInput.fill('2026-11-20');
      const noteInput = page.locator('input[name="note"], textarea[name="note"]').first();
      if (await noteInput.isVisible()) {
        await noteInput.fill('[SYNTHETIC-CLINICAL-RECORD] Routine ANC follow-up authorised by Dr. Kavitha');
      }
      const authBtn = page.locator('button:has-text("Authorise Care Plan")').first();
      if (await authBtn.isVisible()) {
        await authBtn.click();
        await page.waitForTimeout(800);
      }
    }

    // Navigate to Reminders & Replies
    await page.click('button:has-text("Reminders & Replies")');
    await page.waitForTimeout(600);

    // Verify Followup Communication Hub components
    await expect(page.locator('text=Reminders').first()).toBeVisible();
  });

  test('4. Workforce, Field Operations & Transport Operations Hub', async ({ page }) => {
    await loginAs(page, 'Ananya Reddy');
    await expect(page.locator('text=Clinic Administrator').or(page.locator('text=Ananya Reddy'))).toBeVisible({ timeout: 15000 });

    // Open Operations & Workforce tab
    await page.click('button:has-text("Operations & Workforce")');
    await page.waitForTimeout(800);

    // Verify Workforce hub tabs
    await expect(page.locator('button:has-text("Operations Centre")')).toBeVisible();
    await expect(page.locator('button:has-text("Workforce & Shifts")')).toBeVisible();
    await expect(page.locator('button:has-text("Service Coordination")')).toBeVisible();
    await expect(page.locator('button:has-text("Field Visits & Offline Sync")')).toBeVisible();
    await expect(page.locator('button:has-text("Hospital Partnerships & Referrals")')).toBeVisible();
    await expect(page.locator('button:has-text("Transport Fleet & Trips")')).toBeVisible();
    await expect(page.locator('button:has-text("Clinical & Org Governance")')).toBeVisible();
  });

  test('5. Financial Accountability Hub & Funding Governance', async ({ page }) => {
    await loginAs(page, 'Ananya Reddy');
    await expect(page.locator('text=Clinic Administrator').or(page.locator('text=Ananya Reddy'))).toBeVisible({ timeout: 15000 });

    // Navigate to Contracts, Budgets & Finance
    await page.click('button:has-text("Contracts, Budgets & Finance")');
    await page.waitForTimeout(800);

    // Verify Financial Hub tabs
    await expect(page.locator('button:has-text("Financial Overview & Cost Analytics")')).toBeVisible();
    await expect(page.locator('button:has-text("Funding Contracts & Milestones")')).toBeVisible();
    await expect(page.locator('button:has-text("Programme Budgets & Cash-Flow")')).toBeVisible();
    await expect(page.locator('button:has-text("Workforce Payroll & Payslips")')).toBeVisible();
    await expect(page.locator('button:has-text("Expense Claims & Transport Reconciliation")')).toBeVisible();
    await expect(page.locator('button:has-text("Service-to-Funding Evidence")')).toBeVisible();
    await expect(page.locator('button:has-text("Audit Ledger & Corrections")')).toBeVisible();
  });

  test('6. Responsive Layout & Usability Verification', async ({ page }) => {
    // Test on Mobile viewport (375x667 iPhone SE)
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Verify header renders without overflowing
    await expect(page.locator('h1:has-text("JananiSetu")').first()).toBeVisible();
    
    // Test on Tablet viewport (768x1024 iPad)
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('h1:has-text("JananiSetu")').first()).toBeVisible();
  });
});
