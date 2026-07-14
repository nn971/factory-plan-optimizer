import { describe, expect, it } from 'vitest';

import type { ProblemDto } from '../api/dtos';
import { dropdownClosedState, dropdownKeyTransition, rawInputSearchResults, selectionAction } from './rawInputCatalog';

describe('rawInputSearchResults', () => {
  it('shows startup suggestions for empty query', () => {
    expect(rawInputSearchResults(problem(), [], '').map((entry) => entry.item_id)).toEqual(['water', 'iron-ore']);
  });

  it('ranks startup suggestions before exact, prefix, and substring matches', () => {
    const results = rawInputSearchResults(problem(), [], 'iron').map((entry) => entry.item_id);
    expect(results.slice(0, 4)).toEqual(['iron-ore', 'iron', 'iron-plate', 'copper-iron-mix']);
  });

  it('caps results at 50', () => {
    const big = { ...problem(), raw_input_candidates: [], items: Array.from({ length: 75 }, (_, index) => ({ id: `thing-${index}`, kind: 'item' as const })) };
    expect(rawInputSearchResults(big, [], 'thing')).toHaveLength(50);
  });

  it('dedupes and flags existing rows by item_id', () => {
    const [result] = rawInputSearchResults(problem(), [{ item_id: 'water', kind: 'fluid', enabled: true, cost: '5', capacity: '6', defaultApproved: false }], 'water');
    expect(result.isExisting).toBe(true);
    expect(selectionAction(result)).toEqual({ type: 'focus', item_id: 'water' });
  });

  it('returns add selection actions for non-existing catalog entries', () => {
    const [result] = rawInputSearchResults(problem(), [], 'mystery');
    expect(selectionAction(result)).toEqual({ type: 'add', item_id: 'mystery-thing', kind: 'unknown', source: undefined, default_approved: false });
  });

  it('preserves existing non-suggestion row metadata when catalog was added first', () => {
    const [result] = rawInputSearchResults(problem(), [{ item_id: 'iron-plate', kind: 'item', enabled: true, cost: '1', capacity: '2', source: 'default_input', defaultApproved: true }], 'iron-plate');
    expect(result).toMatchObject({ isExisting: true, source: 'default_input', defaultApproved: true });
  });

  it('includes unknown kind entries', () => {
    const [entry] = rawInputSearchResults(problem(), [], 'mystery');
    expect(entry.kind).toBe('unknown');
  });

  it('matches friendly labels case-insensitively', () => {
    expect(rawInputSearchResults(problem(), [], 'Iron Plate').map((entry) => entry.item_id)).toContain('iron-plate');
  });
});

describe('dropdownKeyTransition', () => {
  it('opens and advances with arrow keys', () => {
    expect(dropdownKeyTransition({ open: false, activeIndex: -1 }, 'ArrowDown', 2)).toMatchObject({ open: true, activeIndex: 0, select: false });
    expect(dropdownKeyTransition({ open: true, activeIndex: 0 }, 'ArrowUp', 2)).toMatchObject({ open: true, activeIndex: 1, select: false });
  });

  it('wraps keyboard navigation and handles empty result sets', () => {
    expect(dropdownKeyTransition({ open: true, activeIndex: 1 }, 'ArrowDown', 2)).toMatchObject({ open: true, activeIndex: 0, select: false });
    expect(dropdownKeyTransition({ open: true, activeIndex: -1 }, 'ArrowUp', 2)).toMatchObject({ open: true, activeIndex: 1, select: false });
    expect(dropdownKeyTransition({ open: true, activeIndex: -1 }, 'ArrowDown', 0)).toMatchObject({ open: true, activeIndex: -1, select: false });
    expect(dropdownKeyTransition({ open: true, activeIndex: -1 }, 'Enter', 0)).toMatchObject({ select: false });
  });

  it('selects active result on enter and closes on escape', () => {
    expect(dropdownKeyTransition({ open: true, activeIndex: 0 }, 'Enter', 1).select).toBe(true);
    expect(dropdownKeyTransition({ open: true, activeIndex: 0 }, 'Escape', 1)).toMatchObject({ open: false, activeIndex: -1, select: false });
  });

  it('supports close/reset state after enter selection is handled', () => {
    const transition = dropdownKeyTransition({ open: true, activeIndex: 0 }, 'Enter', 1);
    expect(transition.select).toBe(true);
    expect(dropdownClosedState()).toEqual({ open: false, activeIndex: -1 });
  });
});

function problem(): Pick<ProblemDto, 'items' | 'raw_input_candidates'> {
  return {
    items: [
      { id: 'iron', kind: 'item' },
      { id: 'iron-plate', kind: 'item' },
      { id: 'copper-iron-mix', kind: 'item' },
      { id: 'iron-ore', kind: 'item' },
      { id: 'water', kind: 'fluid' },
      { id: 'mystery-thing', kind: 'unknown' },
    ],
    raw_input_candidates: [
      { item_id: 'water', kind: 'fluid', enabled: false, cost: 9, capacity: 1, source: 'inferred_fluid' },
      { item_id: 'iron-ore', kind: 'item', enabled: false, cost: 9, capacity: 1, source: 'inferred_unproduced' },
    ],
  };
}
