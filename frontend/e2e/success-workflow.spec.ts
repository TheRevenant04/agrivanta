import { test, expect, type APIRequestContext } from '@playwright/test';

const API_BASE = process.env.E2E_API_BASE || 'http://localhost:8000';

const EMAIL = `e2e-${Date.now()}@agrivanta.test`;
const PASSWORD = 'e2e-password-12345';

test.describe('success workflow', () => {
  test.beforeAll(async ({ request }) => {
    await setupFarm(request);
  });

  test('walks the full path and ends with an evidence-backed AI answer', async ({
    page,
  }) => {
    // 1. Sign in through the UI.
    await page.goto('/login');
    await page.fill('#login-email', EMAIL);
    await page.fill('#login-password', PASSWORD);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL('/dashboard');

    // 2. Ask the AI analyst a question.
    await page.goto('/chat');
    await page.fill('#chat-question', 'What is my inventory position?');
    await page.click('button:has-text("Send question")');

    // 3. The answer arrives with visible evidence.
    await expect(
      page.locator('article:has-text("AI analyst") [role="alert"]'),
    ).not.toBeVisible();
    await expect(page.locator('[aria-label="Evidence"]')).toBeVisible();
    await expect(page.locator('h3:has-text("Figures")')).toBeVisible();
    await expect(
      page.locator('h3:has-text("Reporting periods")'),
    ).toBeVisible();
    await expect(page.locator('h3:has-text("Crop cycles")')).toBeVisible();
    await expect(
      page.locator('h3:has-text("Calculation basis")'),
    ).toBeVisible();
  });
});

async function setupFarm(request: APIRequestContext): Promise<void> {
  const authHeaders = (token: string) => ({ Authorization: `Token ${token}` });

  // Register a new user (auto-creates a farm).
  const register = await request.post(`${API_BASE}/api/auth/register`, {
    data: { email: EMAIL, password: PASSWORD, name: 'E2E Farmer' },
  });
  expect(register.status()).toBe(201);
  const registerBody = await register.json();
  const token = registerBody.token as string;
  const headers = authHeaders(token);

  // Create a unit of measure.
  const unitResp = await request.post(`${API_BASE}/api/units`, {
    headers,
    data: { name: 'kg', baseMeasure: 'mass' },
  });
  expect(unitResp.status()).toBe(201);
  const unitBody = await unitResp.json();
  const unitId = unitBody.id as string;

  // Create a crop.
  const cropResp = await request.post(`${API_BASE}/api/crops`, {
    headers,
    data: { name: 'Wheat' },
  });
  expect(cropResp.status()).toBe(201);
  const cropBody = await cropResp.json();
  const cropId = cropBody.id as string;

  // Create a variety for the crop.
  const varietyResp = await request.post(`${API_BASE}/api/varieties`, {
    headers,
    data: { cropId, name: 'Spring Wheat' },
  });
  expect(varietyResp.status()).toBe(201);
  const varietyBody = await varietyResp.json();
  const varietyId = varietyBody.id as string;

  // Create a field.
  const fieldResp = await request.post(`${API_BASE}/api/fields`, {
    headers,
    data: { name: 'North Field', area: 10, notes: 'E2E test field' },
  });
  expect(fieldResp.status()).toBe(201);
  const fieldBody = await fieldResp.json();
  const fieldId = fieldBody.id as string;

  // Create an inventory item.
  const itemResp = await request.post(`${API_BASE}/api/inventory-items`, {
    headers,
    data: { name: 'Fertilizer', unitId },
  });
  expect(itemResp.status()).toBe(201);
  const itemBody = await itemResp.json();
  const itemId = itemBody.id as string;

  // Post a stock movement so inventory_position returns data.
  const movementResp = await request.post(`${API_BASE}/api/stock-movements`, {
    headers,
    data: {
      itemId,
      type: 'purchase',
      quantity: 100,
      date: '2026-01-01',
    },
  });
  expect(movementResp.status()).toBe(201);

  // Create a crop cycle.
  const cycleResp = await request.post(`${API_BASE}/api/crop-cycles`, {
    headers,
    data: {
      fieldId,
      cropId,
      varietyId,
      startDate: '2026-03-01',
      cycleType: 'annual',
    },
  });
  expect(cycleResp.status()).toBe(201);
  const cycleBody = await cycleResp.json();
  const cycleId = cycleBody.id as string;

  // Close the crop cycle.
  const closeResp = await request.post(
    `${API_BASE}/api/crop-cycles/${cycleId}/close`,
    { headers },
  );
  expect(closeResp.status()).toBe(200);
}
