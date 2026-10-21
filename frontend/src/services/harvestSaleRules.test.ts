import { describe, expect, it } from 'vitest';
import { createFarmSetupMock } from './farmSetupMock';
import {
  computeHarvestedTotal,
  formatAmount,
  isIsoCalendarDate,
} from './harvestSaleRules';
import type { Harvest } from './types';

const UNITS = [
  { id: 'unit-kg', name: 'Kilogram', baseMeasure: 'mass' as const },
  { id: 'unit-g', name: 'Gram', baseMeasure: 'mass' as const },
  { id: 'unit-tonne', name: 'Tonne', baseMeasure: 'mass' as const },
];

const CONVERSIONS = [
  { id: 'conv-1', fromUnitId: 'unit-g', toUnitId: 'unit-kg', factor: 0.001 },
];

function setup() {
  return createFarmSetupMock({
    seed: { units: UNITS, conversions: CONVERSIONS },
    requireAuth: () => undefined,
  });
}

function harvest(
  id: string,
  quantity: number,
  unitId: string,
  cycleId = 'cycle-1',
): Harvest {
  return { id, cycleId, quantity, unitId, date: '2026-03-01' };
}

describe('harvested total', () => {
  it('is zero with no unit when the cycle has no harvests', async () => {
    await expect(
      computeHarvestedTotal([], setup().conversions.convert),
    ).resolves.toEqual({ total: 0, unitId: null });
  });

  it('sums harvests recorded in the same unit', async () => {
    await expect(
      computeHarvestedTotal(
        [
          harvest('harvest-1', 50, 'unit-kg'),
          harvest('harvest-2', 50, 'unit-kg'),
        ],
        setup().conversions.convert,
      ),
    ).resolves.toEqual({ total: 100, unitId: 'unit-kg' });
  });

  it("converts harvests into the first harvest's unit before summing", async () => {
    await expect(
      computeHarvestedTotal(
        [
          harvest('harvest-1', 50, 'unit-kg'),
          harvest('harvest-2', 50000, 'unit-g'),
        ],
        setup().conversions.convert,
      ),
    ).resolves.toEqual({ total: 100, unitId: 'unit-kg' });
  });

  it('rejects with the conversion rule error naming the units', async () => {
    await expect(
      computeHarvestedTotal(
        [
          harvest('harvest-1', 50, 'unit-kg'),
          harvest('harvest-2', 20, 'unit-tonne'),
        ],
        setup().conversions.convert,
      ),
    ).rejects.toMatchObject({
      status: 404,
      message: expect.stringContaining('"Kilogram"'),
    });
  });
});

describe('harvest and sale rule helpers', () => {
  it('recognises ISO calendar dates and rejects impossible ones', () => {
    expect(isIsoCalendarDate('2026-03-01')).toBe(true);
    expect(isIsoCalendarDate('2026-02-30')).toBe(false);
    expect(isIsoCalendarDate('01/03/2026')).toBe(false);
  });

  it('formats amounts without floating point noise', () => {
    expect(formatAmount(0.1 + 0.2)).toBe('0.3');
    expect(formatAmount(35)).toBe('35');
  });
});
