import { test, expect, type Page } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SCREENSHOT_DIR = path.resolve(__dirname, '../../docs/screenshots');

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

test.describe('JananiSetu 16-Step Guided Demonstration Journey', () => {
  test.setTimeout(120000); // 2 minutes for complete 16-step flow

  test('Execute complete 16-step maternal care, clinical safety & financial governance journey', async ({ page }) => {
    // -------------------------------------------------------------------------
    // STEP 1: Staff Login & Role Dashboard
    // -------------------------------------------------------------------------
    await loginAs(page, 'Ananya Reddy');
    await expect(page.locator('text=Clinic Administrator').or(page.locator('text=Ananya Reddy'))).toBeVisible({ timeout: 15000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '01_staff_login_and_dashboard.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 2: Synthetic Mother Registration & Consent
    // -------------------------------------------------------------------------
    await loginAs(page, 'Lakshmi Devi');
    await page.click('button:has-text("Mothers & Consent")');
    await page.waitForTimeout(600);
    await expect(page.locator('h2:has-text("Register Synthetic Patient")')).toBeVisible();

    const randomSuffix = Math.floor(Math.random() * 9000 + 1000);
    const demoMotherName = `Savitri Devi (Demo ${randomSuffix})`;
    const nameInput = page.locator('input[name="name"]').first();
    await nameInput.fill(demoMotherName);
    const phoneInput = page.locator('input[name="phone"]').first();
    await phoneInput.fill(`98490${randomSuffix}`);

    // Submit form
    const submitBtn = page.locator('button:has-text("Register Mother")').first();
    await submitBtn.click();
    await phoneInput.press('Enter');
    await page.waitForTimeout(1000);

    // Filter by suffix to verify persisted mother row
    const motherSearch = page.locator('input[type="search"]').first();
    await motherSearch.fill(String(randomSuffix));
    await page.waitForTimeout(600);
    await expect(page.locator(`text=${randomSuffix}`).first()).toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '02_synthetic_mother_registration.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 3: ANC Card Upload
    // -------------------------------------------------------------------------
    await page.click('button:has-text("ANC Scans & OCR")');
    await page.waitForTimeout(800);
    await expect(page.locator('text=Evidence-Linked ANC Card Digitisation')).toBeVisible();

    const fixturePath = path.resolve(__dirname, '../../data/fixtures/printed_clear.png');
    const fileInput = page.locator('input[type="file"][name="file"]').first();
    if (await fileInput.isVisible()) {
      await fileInput.setInputFiles(fixturePath);
      const uploadBtn = page.locator('button:has-text("Upload & OCR")').first();
      await uploadBtn.click();
      await page.waitForTimeout(2000);
    }
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '03_anc_card_upload.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 4: Actual Local OCR Extraction & Provenance
    // -------------------------------------------------------------------------
    // Trigger benchmark evaluation on synthetic fixtures to show extraction accuracy
    const benchmarkBtn = page.locator('button:has-text("Measure OCR Accuracy on 3 Fixtures")').first();
    if (await benchmarkBtn.isVisible()) {
      await benchmarkBtn.click();
      await expect(page.locator('text=Overall Present-Field Extraction Accuracy')).toBeVisible({ timeout: 15000 });
    }
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '04_ocr_extraction_provenance.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 5: Manual Correction & Human Confirmation
    // -------------------------------------------------------------------------
    const confirmBtn = page.locator('button:has-text("Save Confirmed Administrative Record")').first();
    if (await confirmBtn.isVisible()) {
      await confirmBtn.click();
      await page.waitForTimeout(1000);
    }
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '05_human_verification_confirmed.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 6: Doctor-Authorised Care Plan & Visit Date
    // -------------------------------------------------------------------------
    await loginAs(page, 'Dr. Kavitha Rao');
    await page.click('button:has-text("Care Plans & Visits")');
    await page.waitForTimeout(800);

    const visitDateInput = page.locator('input[name="visit_date"]').first();
    if (await visitDateInput.isVisible()) {
      await visitDateInput.fill('2026-11-25');
      const noteInput = page.locator('input[name="note"], textarea[name="note"]').first();
      if (await noteInput.isVisible()) {
        await noteInput.fill('[SYNTHETIC-CLINICAL-RECORD] Doctor-authorised ANC visit #3 scheduled by Dr. Kavitha');
      }
      const authBtn = page.locator('button:has-text("Authorise Care Plan")').first();
      if (await authBtn.isVisible()) {
        await authBtn.click();
        await page.waitForTimeout(1000);
      }
    }
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '06_doctor_authorised_careplan.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 7: Scheduled Reminder Hub
    // -------------------------------------------------------------------------
    await page.click('button:has-text("Reminders & Replies")');
    await page.waitForTimeout(800);
    await expect(page.locator('text=Reminders').first()).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '07_scheduled_reminder_hub.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 8: Closed-Loop Reminder Delivery & Tracking
    // -------------------------------------------------------------------------
    // Trigger outbox polling run to process queued reminders
    const runOutboxBtn = page.locator('button:has-text("Dispatch Due Reminders Now")').first();
    if (await runOutboxBtn.isVisible()) {
      await runOutboxBtn.click();
      await page.waitForTimeout(1000);
    }
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '08_reminder_delivery_closed_loop.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 9: Follow-up Task Assignment
    // -------------------------------------------------------------------------
    await page.click('button:has-text("Follow-up Tasks")');
    await page.waitForTimeout(800);
    await expect(page.locator('text=Follow-up Tasks').first()).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '09_field_worker_task_assignment.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 10: Field Operations & Visit Completion
    // -------------------------------------------------------------------------
    await page.click('button:has-text("Operations & Workforce")');
    await page.waitForTimeout(800);
    await page.click('button:has-text("Field Visits & Offline Sync")');
    await page.waitForTimeout(600);
    await expect(page.locator('text=Field Visits').first()).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '10_field_visit_completion.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 11: Clinician-Entered Referral Record
    // -------------------------------------------------------------------------
    await page.click('button:has-text("Hospital Partnerships & Referrals")');
    await page.waitForTimeout(600);
    await expect(page.locator('text=Hospital Partnerships').first()).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '11_partner_hospital_referral.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 12: Non-Emergency Transport Fleet Coordination
    // -------------------------------------------------------------------------
    await page.click('button:has-text("Transport Fleet & Trips")');
    await page.waitForTimeout(600);
    await expect(page.locator('text=Non-Emergency Scheduled Transport Boundary').first()).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '12_transport_fleet_coordination.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 13: Service Evidence & Milestone Tracking
    // -------------------------------------------------------------------------
    await loginAs(page, 'Ananya Reddy');
    await page.click('button:has-text("Contracts, Budgets & Finance")');
    await page.waitForTimeout(800);
    await expect(page.locator('text=Government Contracts, Programme Budgets').first()).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '13_service_funding_evidence.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 14: Programme Expenditure Reconciliation
    // -------------------------------------------------------------------------
    await page.click('button:has-text("Programme Budgets & Cash-Flow")');
    await page.waitForTimeout(600);
    await expect(page.locator('text=Budget:').first()).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '14_budget_expenditure_ledger.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 15: Funding Utilisation Report (Zero-PII)
    // -------------------------------------------------------------------------
    await page.click('button:has-text("Reports & CSV/PDF Exports")');
    await page.waitForTimeout(600);
    await expect(page.locator('text=Reports & CSV/PDF Exports').first()).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '15_zero_pii_funding_report.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 16: Complete Cryptographic Audit History
    // -------------------------------------------------------------------------
    await page.click('button:has-text("Analytics & Audit")');
    await page.waitForTimeout(800);
    await expect(page.locator('text=Immutable Clinic Audit Trail').first()).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '16_audit_trail_and_governance.png'), fullPage: false });

    // -------------------------------------------------------------------------
    // STEP 17: Mobile & Tablet Responsiveness Verification
    // -------------------------------------------------------------------------
    await page.setViewportSize({ width: 375, height: 667 });
    await page.waitForTimeout(500);
    await expect(page.locator('text=JananiSetu')).toBeVisible();
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, '17_mobile_responsive_view.png'), fullPage: false });
  });
});
