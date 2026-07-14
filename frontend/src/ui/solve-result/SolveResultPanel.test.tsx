import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { SolveJobDto, SolveResultDto, SparseClusteringResultDto } from '../../api/dtos';
import { SolveResultPanel } from './SolveResultPanel';

describe('SolveResultPanel sparse boundary review wiring', () => {
  it('renders partial ID-only graph when explorer metadata is unavailable', () => {
    const html = renderToStaticMarkup(
      <SolveResultPanel
        job={job({ recipe_rates: { 'make-gear': 1 }, external_supplies: { 'iron-ore': 2 } })}
        explorer={null}
        explorerLoading={false}
        explorerStale={false}
        onLoadExplorer={() => undefined}
        currentPackageId="package-a"
      />,
    );

    expect(html).toContain('Recipe data not loaded');
    expect(html).toContain('Active flow graph');
    expect(html).toContain('Full recipe IO topology is unavailable without explorer recipe metadata');
  });

  it('uses sparse boundary review instead of legacy diagnostics when sparse clustering succeeds', () => {
    const html = renderToStaticMarkup(
      <SolveResultPanel
        job={job({ sparse_clustering: sparseResult(), cluster_diagnostics: legacyDiagnostics() })}
        explorer={null}
        explorerLoading={false}
        explorerStale={false}
        onLoadExplorer={() => undefined}
        currentPackageId="package-a"
      />,
    );

    expect(html).toContain('Sparse cluster review');
    expect(html).toContain('Net port review');
    expect(html).not.toContain('Solver cluster diagnostics');
  });

  it('keeps legacy diagnostics as fallback without successful sparse clustering', () => {
    const html = renderToStaticMarkup(
      <SolveResultPanel
        job={job({ sparse_clustering: null, cluster_diagnostics: legacyDiagnostics() })}
        explorer={null}
        explorerLoading={false}
        explorerStale={false}
        onLoadExplorer={() => undefined}
        currentPackageId="package-a"
      />,
    );

    expect(html).toContain('Solver cluster diagnostics');
    expect(html).toContain('Boundary item review');
  });
});

function job(resultPatch: Partial<SolveResultDto>): SolveJobDto {
  return {
    job_id: 'job-1',
    status: 'succeeded',
    result: {
      solver_status: 'optimal',
      objective_value: 10,
      objective_components: {},
      recipe_rates: {},
      external_supplies: {},
      unmet_demand: {},
      surplus: {},
      balance_residuals: {},
      ...resultPatch,
    },
    error: null,
  };
}

function sparseResult(): SparseClusteringResultDto {
  return {
    status: 'success',
    message: 'sparse clustering completed',
    mode: 'fast',
    graph_type: 'recipe-to-recipe',
    optimization_effect: 'none',
    engine: 'port-aware',
    cluster_count: 1,
    target_cluster_count: 1,
    effective_config: {},
    warnings: [],
    quality: {},
    boundary_port_type_count: 1,
    net_port_count: 1,
    port_aware_objective: { port_cost: 1000, size_penalty: 0, flow_cost: 0, total_score: 1000, net_port_count: 1, refinement_passes: 1 },
    external_boundary_port_type_count: 0,
    graph_statistics: {},
    cluster_summaries: { items: [{ cluster_id: 1, recipe_count: 1, recipe_ids: ['make-gear'], net_input_port_count: 0, net_output_port_count: 1, net_port_count: 1 }], total_count: 1, truncated: false },
    boundary_port_types: { items: [{ cluster_id: 1, item_id: 'gear', direction: 'output', net_amount: 1 }], total_count: 1, truncated: false },
    external_boundary_port_types: { items: [], total_count: 0, truncated: false },
  };
}

function legacyDiagnostics(): SolveResultDto['cluster_diagnostics'] {
  return {
    mode: 'diagnostic_only',
    active_epsilon: 0.000001,
    cost_defaults: {
      flow_cost_per_quantity: 1,
      port_cost_per_boundary_type: 100,
      recipe_size_penalty: 1,
      boundary_type_size_penalty: 1,
      target_active_recipes: [1, 2],
      target_boundary_item_types: [1, 2],
    },
    diagnostic_components: {},
    base_objective_value: 10,
    diagnostic_total: 2,
    combined_diagnostic_objective_value: 12,
    clusters: [
      {
        id: 'legacy-1',
        label: 'Legacy cluster',
        category: 'legacy',
        recipe_ids: ['legacy-recipe'],
        active_recipe_count: 1,
        boundary_item_type_count: 1,
        boundary_items: [],
        diagnostic_components: { port_cost: 1 },
      },
    ],
  };
}
