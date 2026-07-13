import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { OptimizedClusteringResultDto } from '../../api/dtos';
import { OptimizedClusteringPanel } from './OptimizedClusteringPanel';

describe('OptimizedClusteringPanel', () => {
  it('renders nullable missing result as not requested', () => {
    expect(renderToStaticMarkup(<OptimizedClusteringPanel result={null} />)).toContain('Not requested');
  });

  it('shows nullable objective and non-success statuses', () => {
    const html = renderToStaticMarkup(<OptimizedClusteringPanel result={result({ status: 'timeout_no_incumbent', objective_value: null })} />);

    expect(html).toContain('Timed out');
    expect(html).toContain('n/a');
  });

  it('renders cluster_size_penalty and aggregate external label wording', () => {
    const html = renderToStaticMarkup(<OptimizedClusteringPanel result={result()} />);

    expect(html).toContain('cluster size penalty');
    expect(html).toContain('aggregate external balance');
    expect(html).not.toContain('raw supply');
    expect(html).not.toContain('final demand routing');
  });

  it('surfaces provisional preset and effective parameters', () => {
    const html = renderToStaticMarkup(<OptimizedClusteringPanel result={result({ effective_parameters: { preset: 'even_size', preset_is_provisional: true, time_limit_seconds: 20 } })} />);

    expect(html).toContain('Preset is provisional');
    expect(html).toContain('time limit seconds');
    expect(html).toContain('20');
  });
});

function result(patch: Partial<OptimizedClusteringResultDto> = {}): OptimizedClusteringResultDto {
  return {
    status: 'optimal',
    mode: 'continuous_split',
    effective_parameters: { preset: 'balanced', preset_is_provisional: false, time_limit_seconds: 60 },
    objective_value: 42,
    objective_components: { flow_cost: 1, port_cost: 2, cluster_size_penalty: 3, duplication_cost: 0 },
    cost_breakdown: {
      inter_cluster_flow_cost: 1,
      external_flow_cost: 0,
      inter_cluster_port_cost: 2,
      external_port_cost: 0,
      cluster_size_penalty: 3,
      duplication_cost: 0,
    },
    clusters: [{ cluster_id: 'cluster-1', used: true, size: 6, under_min: 0, over_max: 0 }],
    allocations: [{ recipe_id: 'make-gear', cluster_id: 'cluster-1', rate: 2, fraction: 1 }],
    flows: [{ from_cluster_id: 'cluster-1', to_cluster_id: 'cluster-2', item_id: 'gear', quantity: 2 }],
    external_flows: [{ cluster_id: 'cluster-1', item_id: 'iron-ore', direction: 'in', boundary_label: 'aggregate_external_balance', quantity: 4 }],
    reconciliation: { objective_matches_breakdown: true },
    ...patch,
  };
}
