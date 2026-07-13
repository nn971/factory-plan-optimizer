import { describe, expect, it } from 'vitest';

import type { OptimizedClusteringResultDto, SolveResultDto } from '../api/dtos';
import {
  describeOptimizedClusteringStatus,
  externalBoundaryLabel,
  getOptimizedClustering,
  hasOptimizedClusterCostAlias,
} from './optimizedClustering';

describe('optimized clustering helpers', () => {
  it('treats optimized clustering as nullable', () => {
    expect(getOptimizedClustering(result({ optimized_clustering: null }))).toBeNull();
    expect(getOptimizedClustering(result())).toBeNull();
  });

  it('describes every API status clearly', () => {
    const statuses = [
      'optimal',
      'feasible_non_optimal',
      'timeout_no_incumbent',
      'infeasible',
      'solver_unavailable',
      'model_too_large',
      'no_active_recipes',
      'disabled',
    ] as const;

    expect(statuses.map((status) => describeOptimizedClusteringStatus(status).label)).toEqual([
      'Optimal',
      'Feasible, not optimal',
      'Timed out',
      'Infeasible',
      'Solver unavailable',
      'Model too large',
      'No active recipes',
      'Disabled',
    ]);
  });

  it('uses cluster_size_penalty without depending on cluster_cost', () => {
    expect(hasOptimizedClusterCostAlias(optimizedResult())).toBe(false);
    expect(hasOptimizedClusterCostAlias({
      ...optimizedResult(),
      objective_components: { cluster_cost: 1 },
    })).toBe(true);
  });

  it('labels aggregate external balance conservatively', () => {
    expect(externalBoundaryLabel({
      cluster_id: 'cluster-1',
      item_id: 'iron-ore',
      direction: 'in',
      boundary_label: 'aggregate_external_balance',
      quantity: 3,
    })).toBe('aggregate external balance');
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

function optimizedResult(patch: Partial<OptimizedClusteringResultDto> = {}): OptimizedClusteringResultDto {
  return {
    status: 'optimal',
    mode: 'continuous_split',
    effective_parameters: { preset: 'balanced', preset_is_provisional: false },
    objective_value: null,
    objective_components: { flow_cost: 1, port_cost: 2, cluster_size_penalty: 3, duplication_cost: 0 },
    cost_breakdown: { inter_cluster_flow_cost: 1, cluster_size_penalty: 3 },
    clusters: [],
    allocations: [],
    flows: [],
    external_flows: [],
    reconciliation: {},
    ...patch,
  };
}
