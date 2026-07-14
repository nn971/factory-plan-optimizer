import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { SparseClusteringResultDto } from '../../api/dtos';
import { SparseClusteringPanel } from './SparseClusteringPanel';

describe('SparseClusteringPanel', () => {
  it('renders nullable missing result as not requested', () => {
    expect(renderToStaticMarkup(<SparseClusteringPanel result={null} />)).toContain('Not requested');
  });

  it('renders summary-first success metrics and careful external amount copy', () => {
    const html = renderToStaticMarkup(<SparseClusteringPanel result={result()} />);

    expect(html).toContain('Recipe graph overview');
    expect(html).toContain('Net ports');
    expect(html).toContain('Port-aware objective');
    expect(html).toContain('Refinement passes');
    expect(html).toContain('Skipped hub edges');
    expect(html).toContain('Source/demand amount');
    expect(html).toContain('diagnostics only');
    expect(html).toContain('+4 output');
  });

  it('renders non-success status without detail tables', () => {
    const html = renderToStaticMarkup(<SparseClusteringPanel result={result({ status: 'failed', message: 'sparse clustering failed' })} />);

    expect(html).toContain('Failed');
    expect(html).toContain('sparse clustering failed');
    expect(html).toContain('No sparse cluster detail tables');
  });

  it('surfaces truncation warnings calmly', () => {
    const html = renderToStaticMarkup(<SparseClusteringPanel result={result({
      mode: 'balanced',
      boundary_port_types: { items: [], total_count: 8, truncated: true },
    })} />);

    expect(html).toContain('net ports are capped');
  });
});

function result(patch: Partial<SparseClusteringResultDto> = {}): SparseClusteringResultDto {
  return {
    status: 'success',
    message: 'sparse clustering completed',
    mode: 'fast',
    graph_type: 'recipe-to-recipe',
    optimization_effect: 'none',
    engine: 'deterministic-fast',
    cluster_count: 2,
    target_cluster_count: 3,
    effective_config: { max_runtime_seconds: 5, hub_item_top_k: 100 },
    warnings: [],
    quality: { boundary_port_type_count: 4, size_imbalance: 1 },
    boundary_port_type_count: 4,
    net_port_count: 4,
    port_aware_objective: { port_cost: 4000, size_penalty: 1, flow_cost: 0, total_score: 4001, net_port_count: 4, refinement_passes: 2 },
    external_boundary_port_type_count: 1,
    graph_statistics: { active_recipe_count: 6, active_item_count: 4, skipped_hub_edge_count: 2 },
    cluster_summaries: { items: [{ cluster_id: 1, recipe_count: 3, net_input_port_count: 1, net_output_port_count: 1, net_port_count: 2, recipe_ids: ['make-gear', 'make-plate'] }], total_count: 1, truncated: false },
    boundary_port_types: { items: [{ cluster_id: 1, item_id: 'gear', direction: 'output', net_amount: 4 }], total_count: 1, truncated: false },
    external_boundary_port_types: { items: [{ cluster_id: 1, item_id: 'iron-ore', direction: 'input', source_or_demand_amount: 10 }], total_count: 1, truncated: false },
    surplus_unmet_summary: { items: [], total_count: 0, truncated: false },
    hub_summaries: { items: [{ item_id: 'water', kept_count: 100, skipped_count: 2, skipped_estimated_flow: 5 }], total_count: 1, truncated: false },
    ...patch,
  };
}
