import { describe, expect, expectTypeOf, it } from 'vitest';

import * as generatedSdk from './generated/sdk.gen';
import type { ListVarietiesData } from './generated/types.gen';
import type { CropCycle } from './types';

describe('generated OpenAPI contract', () => {
  it('keeps the variety crop filter a string', () => {
    expectTypeOf<ListVarietiesData['query']>().toEqualTypeOf<
      | {
          crop?: string;
        }
      | undefined
    >();
  });

  it('preserves nullable crop-cycle variety references', () => {
    expectTypeOf<CropCycle['varietyId']>().toEqualTypeOf<string | null>();
  });

  it('leaves the streaming chat operation to its streaming transport', () => {
    expect('askChat' in generatedSdk).toBe(false);
  });
});
