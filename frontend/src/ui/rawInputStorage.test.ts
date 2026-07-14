import { describe, expect, it } from 'vitest';

import { reconcileSavedExternalInputs } from './App';

describe('reconcileSavedExternalInputs', () => {
  it('preserves saved additions/removals as authoritative and filters stale catalog ids', () => {
    const reconciled = reconcileSavedExternalInputs(
      { items: [{ id: 'water', kind: 'fluid' }, { id: 'coal', kind: 'item' }] },
      [
        { item_id: 'water', kind: 'item', enabled: false, cost: '3', capacity: '4', defaultApproved: false },
        { item_id: 'stale', kind: 'item', enabled: true, cost: '1', capacity: '2', defaultApproved: false },
      ],
    );

    expect(reconciled).toEqual([
      { item_id: 'water', kind: 'fluid', enabled: false, cost: '3', capacity: '4', defaultApproved: false },
    ]);
  });

  it('repairs unsafe saved numeric strings', () => {
    expect(reconcileSavedExternalInputs(
      { items: [{ id: 'water', kind: 'fluid' }] },
      [{ item_id: 'water', kind: 'fluid', enabled: true, cost: 'bad', capacity: '', defaultApproved: false }],
    )[0]).toMatchObject({ cost: '0', capacity: '1000000' });
  });

  it('dedupes saved rows by item_id while preserving the first saved selection', () => {
    expect(reconcileSavedExternalInputs(
      { items: [{ id: 'water', kind: 'fluid' }] },
      [
        { item_id: 'water', kind: 'fluid', enabled: false, cost: '1', capacity: '2', defaultApproved: false },
        { item_id: 'water', kind: 'fluid', enabled: true, cost: '3', capacity: '4', defaultApproved: true },
      ],
    )).toEqual([{ item_id: 'water', kind: 'fluid', enabled: false, cost: '1', capacity: '2', defaultApproved: false }]);
  });
});
