import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadLiveCustomers } from '../services/adapters/liveCustomerLoader';

const requiredColumns = [
  'customerID',
  'gender',
  'SeniorCitizen',
  'Partner',
  'Dependents',
  'tenure',
  'PhoneService',
  'MultipleLines',
  'InternetService',
  'OnlineSecurity',
  'OnlineBackup',
  'DeviceProtection',
  'TechSupport',
  'StreamingTV',
  'StreamingMovies',
  'Contract',
  'PaperlessBilling',
  'PaymentMethod',
  'MonthlyCharges',
  'TotalCharges',
];

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('loadLiveCustomers', () => {
  it('loads a CSV row with the exact backend feature shape', async () => {
    const csv = [
      requiredColumns.join(','),
      'C-1,Female,0,Yes,No,1,Yes,No,DSL,Yes,No,No,Yes,No,No,Month-to-month,Yes,Electronic check,29.85,29.85',
    ].join('\n');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: async () => csv,
    }));

    const customers = await loadLiveCustomers();

    expect(customers).toHaveLength(1);
    expect(Object.keys(customers[0]).sort()).toEqual([...requiredColumns].sort());
    expect(customers[0]).toMatchObject({
      customerID: 'C-1',
      SeniorCitizen: 0,
      tenure: 1,
      MonthlyCharges: 29.85,
      TotalCharges: 29.85,
    });
  });

  it('preserves a blank TotalCharges value as null for a new customer', async () => {
    const csv = [
      requiredColumns.join(','),
      'C-NEW,Female,0,Yes,No,0,Yes,No,DSL,Yes,No,No,Yes,No,No,Month-to-month,Yes,Electronic check,29.85,',
    ].join('\n');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: async () => csv,
    }));

    await expect(loadLiveCustomers()).resolves.toMatchObject([
      { customerID: 'C-NEW', tenure: 0, TotalCharges: null },
    ]);
  });

  it('rejects an HTML fallback page instead of creating invalid customer requests', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      text: async () => '<!doctype html><html><body>TriChurn</body></html>',
    }));

    await expect(loadLiveCustomers()).rejects.toThrow(
      /not a valid customer CSV; missing required columns/,
    );
  });
});
