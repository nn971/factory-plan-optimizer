import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { rawInputSearchResults } from '../domain/rawInputCatalog';
import { RawInputReviewPanel, RawInputSearchResultsList } from './RawInputReviewPanel';

describe('RawInputReviewPanel', () => {
  it('renders raw input rows with edit and remove controls', () => {
    const html = renderToStaticMarkup(
      <RawInputReviewPanel
        problem={{ items: [{ id: 'mystery-thing', kind: 'unknown' }], raw_input_candidates: [] }}
        externalInputs={[{ item_id: 'mystery-thing', kind: 'unknown', enabled: true, cost: '0', capacity: '1000000', defaultApproved: true }]}
        onChange={() => undefined}
      />,
    );

    expect(html).toContain('Search or add raw input');
    expect(html).toContain('Mystery Thing');
    expect(html).toContain('unknown');
    expect(html).toContain('Default suggestion');
    expect(html).toContain('Remove');
    expect(html).toContain('Cost');
    expect(html).toContain('Capacity');
  });

  it('keeps disabled rows visible', () => {
    const html = renderToStaticMarkup(
      <RawInputReviewPanel
        problem={{ items: [{ id: 'iron-ore', kind: 'item' }], raw_input_candidates: [] }}
        externalInputs={[{ item_id: 'iron-ore', kind: 'item', enabled: false, cost: 'bad', capacity: '', defaultApproved: false }]}
        onChange={() => undefined}
      />,
    );

    expect(html).toContain('Iron Ore');
    expect(html).not.toContain('Show disabled');
  });

  it('renders dropdown results for suggested, addable, and existing focus states', () => {
    const problem = {
      items: [
        { id: 'water', kind: 'fluid' as const },
        { id: 'iron-plate', kind: 'item' as const },
        { id: 'mystery-thing', kind: 'unknown' as const },
      ],
      raw_input_candidates: [{ item_id: 'water', kind: 'fluid' as const, enabled: true, cost: 0, capacity: 1000000, source: 'inferred_fluid' as const }],
    };
    const existingRows = [{ item_id: 'iron-plate', kind: 'item' as const, enabled: true, cost: '0', capacity: '1000000', defaultApproved: false }];
    const html = renderToStaticMarkup(
      <RawInputSearchResultsList
        results={[
          ...rawInputSearchResults(problem, existingRows, 'water'),
          ...rawInputSearchResults(problem, existingRows, 'iron-plate'),
          ...rawInputSearchResults(problem, existingRows, 'mystery'),
        ]}
        activeIndex={0}
        onSelect={() => undefined}
      />,
    );

    expect(html).toContain('Water');
    expect(html).toContain('Suggested');
    expect(html).toContain('Suggested fluid');
    expect(html).toContain('Add');
    expect(html).toContain('Iron Plate');
    expect(html).toContain('Focus');
    expect(html).toContain('mystery-thing');
    expect(html).toContain('unknown');
    expect(html).toContain('aria-selected="true"');
  });
});
