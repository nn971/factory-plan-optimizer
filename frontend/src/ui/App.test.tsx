import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { DEFAULT_OPTIMIZED_CLUSTERING } from '../domain/problemState';
import { OptimizedClusteringControls } from './App';

describe('OptimizedClusteringControls', () => {
  it('renders enable, preset, and advanced controls without flattening the main form', () => {
    const html = renderToStaticMarkup(
      <OptimizedClusteringControls
        settings={{ ...DEFAULT_OPTIMIZED_CLUSTERING, enabled: true }}
        disabled={false}
        onChange={() => undefined}
      />,
    );

    expect(html).toContain('Enable optimized clustering');
    expect(html).toContain('Balanced');
    expect(html).toContain('Fewer ports');
    expect(html).toContain('Even size');
    expect(html).toContain('Advanced optimized clustering settings');
    expect(html).toContain('Reporting epsilon');
    expect(html).toContain('Size penalty weight');
    expect(html).toContain('Max size behavior');
    expect(html).toContain('Hard cap');
    expect(html).toContain('Allow all recipes to split across clusters');
    expect(html).toContain('Splittable recipe IDs');
  });
});
