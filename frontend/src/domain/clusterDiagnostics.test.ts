import { describe, expect, it } from 'vitest';

import type { ClusterDiagnosticsDto, SolveResultDto } from '../api/dtos';
import { diagnosticCost, getClusterDiagnostics, sortedBoundaryItems, sortedDiagnosticClusters, summarizeClusterDiagnostics } from './clusterDiagnostics';

describe('cluster diagnostics helpers', () => {
  it('treats null and missing diagnostics as no payload', () => {
    expect(getClusterDiagnostics(result({ cluster_diagnostics: null }))).toBeNull();
    expect(getClusterDiagnostics(result())).toBeNull();
  });

  it('preserves an empty clusters payload as diagnostics that ran', () => {
    const summary = summarizeClusterDiagnostics(result({ cluster_diagnostics: diagnostics({ clusters: [] }) }));

    expect(summary).toMatchObject({ clusterCount: 0, boundaryItemRowCount: 0, activeRecipeCount: 0 });
  });

  it('summarizes and sorts clusters by diagnostic cost then boundary count', () => {
    const payload = diagnostics({
      clusters: [
        cluster('a', { flow_cost: 1 }, 2),
        cluster('b', { flow_cost: 6, port_cost: 4 }, 1),
        cluster('c', { flow_cost: 10 }, 4),
      ],
    });

    expect(summarizeClusterDiagnostics(result({ cluster_diagnostics: payload }))).toMatchObject({
      clusterCount: 3,
      boundaryItemRowCount: 6,
      zeroNetRowCount: 3,
      activeRecipeCount: 3,
      boundaryItemTypeCount: 7,
    });
    expect(sortedDiagnosticClusters(payload).map((entry) => entry.id)).toEqual(['c', 'b', 'a']);
    expect(diagnosticCost(payload.clusters[1])).toBe(10);
  });

  it('sorts nonzero boundary items before zero-net rows', () => {
    const [entry] = diagnostics({ clusters: [cluster('a', {}, 3)] }).clusters;

    expect(sortedBoundaryItems(entry).map((item) => item.item_id)).toEqual(['ore', 'plate', 'gear']);
  });
});

function result(patch: Partial<SolveResultDto> = {}): SolveResultDto {
  return {
    solver_status: 'optimal',
    objective_value: 0,
    objective_components: {},
    recipe_rates: {},
    external_supplies: {},
    unmet_demand: {},
    surplus: {},
    balance_residuals: {},
    ...patch,
  };
}

function diagnostics(patch: Partial<ClusterDiagnosticsDto> = {}): ClusterDiagnosticsDto {
  return {
    mode: 'diagnostic_only',
    active_epsilon: 1e-9,
    cost_defaults: {
      flow_cost_per_quantity: 1,
      port_cost_per_boundary_type: 10,
      recipe_size_penalty: 0.5,
      boundary_type_size_penalty: 2,
      target_active_recipes: [5, 15],
      target_boundary_item_types: [3, 8],
    },
    diagnostic_components: {},
    base_objective_value: 100,
    diagnostic_total: 12,
    combined_diagnostic_objective_value: 112,
    clusters: [],
    ...patch,
  };
}

function cluster(id: string, components: Record<string, number>, boundaryCount: number) {
  return {
    id,
    label: `Cluster ${id}`,
    category: 'crafting',
    recipe_ids: [id],
    active_recipe_count: 1,
    boundary_item_type_count: boundaryCount,
    diagnostic_components: components,
    boundary_items: [
      { item_id: 'gear', direction: 'output' as const, is_zero_net: true, quantity: 0, flow_cost: 0, port_cost: 0 },
      { item_id: 'ore', direction: 'input' as const, is_zero_net: false, quantity: 4, flow_cost: 4, port_cost: 10 },
      { item_id: 'plate', direction: 'output' as const, is_zero_net: false, quantity: 2, flow_cost: 2, port_cost: 10 },
    ].slice(0, boundaryCount),
  };
}
