import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { DEFAULT_SPARSE_CLUSTERING } from '../domain/problemState';
import { SparseClusteringControls } from './App';

describe('SparseClusteringControls', () => {
  it('renders approved port-aware tuning without taking over the main form', () => {
    const html = renderToStaticMarkup(
      <SparseClusteringControls
        settings={{ ...DEFAULT_SPARSE_CLUSTERING, enabled: true }}
        disabled={false}
        onChange={() => undefined}
      />,
    );

    expect(html).toContain('Enable sparse clustering');
    expect(html).toContain('Fast');
    expect(html).toContain('Balanced');
    expect(html).toContain('Advanced sparse clustering settings');
    expect(html).toContain('Port cost weight');
    expect(html).toContain('Size penalty weight');
    expect(html).toContain('Flow cost weight');
    expect(html).toContain('Min cluster size ratio');
    expect(html).toContain('Max refinement passes');
    expect(html).toContain('Port epsilon');
    expect(html).toContain('Port cost is the primary net-port pressure');
  });
});
