import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { SparseClusteringResultDto } from '../../api/dtos';
import { SparseBoundaryItemReviewPanel } from './SparseBoundaryItemReviewPanel';

describe('SparseBoundaryItemReviewPanel', () => {
  it('renders nothing when sparse clustering is missing or not successful', () => {
    expect(renderToStaticMarkup(<SparseBoundaryItemReviewPanel result={null} />)).toBe('');
    expect(renderToStaticMarkup(<SparseBoundaryItemReviewPanel result={sparseResult({ status: 'failed' })} />)).toBe('');
  });

  it('shows objective metric cards and sorted sparse cluster overview', () => {
    const html = renderToStaticMarkup(<SparseBoundaryItemReviewPanel result={sparseResult()} />);

    expect(html).toContain('Net port review');
    expect(html).toContain('Port cost');
    expect(html).toContain('Size penalty');
    expect(html).toContain('Flow cost');
    expect(html).toContain('Refinement passes');
    expect(html.indexOf('cluster 2')).toBeLessThan(html.indexOf('cluster 1'));
  });

  it('shows selected cluster net-port rows without fake costs', () => {
    const html = renderToStaticMarkup(<SparseBoundaryItemReviewPanel result={sparseResult()} />);

    expect(html).toContain('Net port item');
    expect(html).toContain('Net amount');
    expect(html).toContain('+4');
    expect(html).not.toContain('Flow cost</th>');
    expect(html).not.toContain('Port cost</th>');
  });

  it('labels external rows as diagnostics only', () => {
    const html = renderToStaticMarkup(<SparseBoundaryItemReviewPanel result={sparseResult()} />);

    expect(html).toContain('External source/demand diagnostics');
    expect(html).toContain('Diagnostics only');
    expect(html).toContain('not objective net ports');
    expect(html).toContain('not exact routed flow');
  });
});

function sparseResult(patch: Partial<SparseClusteringResultDto> = {}): SparseClusteringResultDto {
  return {
    status: 'success',
    message: 'sparse clustering completed',
    mode: 'balanced',
    graph_type: 'recipe-to-recipe',
    optimization_effect: 'none',
    engine: 'port-aware',
    cluster_count: 2,
    target_cluster_count: 2,
    effective_config: {},
    warnings: [],
    quality: {},
    boundary_port_type_count: 5,
    net_port_count: 5,
    port_aware_objective: { port_cost: 5000, size_penalty: 3, flow_cost: 0.5, total_score: 5003.5, net_port_count: 5, refinement_passes: 4 },
    external_boundary_port_type_count: 1,
    graph_statistics: {},
    cluster_summaries: {
      items: [
        { cluster_id: 1, recipe_count: 10, recipe_ids: ['make-plate'], net_input_port_count: 1, net_output_port_count: 1, net_port_count: 2 },
        { cluster_id: 2, recipe_count: 4, recipe_ids: ['make-gear', 'make-science'], net_input_port_count: 2, net_output_port_count: 1, net_port_count: 3 },
      ],
      total_count: 2,
      truncated: false,
    },
    boundary_port_types: {
      items: [
        { cluster_id: 2, item_id: 'gear', direction: 'output', net_amount: 4 },
        { cluster_id: 2, item_id: 'iron-plate', direction: 'input', net_amount: -8 },
        { cluster_id: 1, item_id: 'iron-ore', direction: 'input', net_amount: -10 },
      ],
      total_count: 3,
      truncated: false,
    },
    external_boundary_port_types: {
      items: [{ cluster_id: 2, item_id: 'science-pack', direction: 'output', source_or_demand_amount: 1 }],
      total_count: 1,
      truncated: false,
    },
    ...patch,
  };
}
