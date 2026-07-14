import { describe, expect, it } from 'vitest';

import type { SolveResultDto, SparseClusteringResultDto } from '../api/dtos';
import {
  cappedArraySummary,
  clusterLabel,
  componentLabel,
  describeSparseClusteringStatus,
  displayId,
  getSparseClustering,
  skippedHubEdgeCount,
  truncatedCappedArrayLabels,
} from './sparseClustering';

describe('sparse clustering helpers', () => {
  it('treats sparse clustering as nullable', () => {
    expect(getSparseClustering(result({ sparse_clustering: null }))).toBeNull();
    expect(getSparseClustering(result())).toBeNull();
  });

  it('describes every status', () => {
    const statuses = ['success', 'skipped', 'model_too_large', 'timeout', 'failed'] as const;

    expect(statuses.map((status) => describeSparseClusteringStatus(status).label)).toEqual([
      'Ready',
      'Skipped',
      'Model too large',
      'Timed out',
      'Failed',
    ]);
  });

  it('summarizes capped arrays and truncation', () => {
    expect(cappedArraySummary({ items: [{ item_id: 'iron' }], total_count: 3, truncated: true }, 'ports')).toBe('Showing 1 of 3 ports.');
    expect(cappedArraySummary({ items: [], total_count: 0, truncated: false }, 'ports')).toBe('Showing all 0 ports.');

    expect(truncatedCappedArrayLabels(sparseResult({
      boundary_port_types: { items: [], total_count: 5, truncated: true },
    }))).toEqual(['net ports']);
  });

  it('labels components and safe display ids', () => {
    expect(componentLabel('source_or_demand_amount')).toBe('source or demand amount');
    expect(componentLabel('boundary_port_type_count')).toBe('net ports');
    expect(componentLabel('flow_cost')).toBe('flow cost (absolute net)');
    expect(clusterLabel(2)).toBe('cluster 2');
    expect(clusterLabel(null)).toBe('unknown cluster');
    expect(displayId('')).toBe('unknown');
  });

  it('reads skipped hub edge count from statistics first', () => {
    expect(skippedHubEdgeCount(sparseResult({ graph_statistics: { skipped_hub_edge_count: 12 } }))).toBe(12);
    expect(skippedHubEdgeCount(sparseResult({
      graph_statistics: {},
      hub_summaries: { items: [{ item_id: 'water', kept_count: 1, skipped_count: 2, skipped_estimated_flow: 3 }], total_count: 1, truncated: false },
    }))).toBe(2);
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

function sparseResult(patch: Partial<SparseClusteringResultDto> = {}): SparseClusteringResultDto {
  return {
    status: 'success',
    message: 'sparse clustering completed',
    mode: 'fast',
    graph_type: 'recipe-to-recipe',
    optimization_effect: 'none',
    engine: 'deterministic-fast',
    cluster_count: 2,
    target_cluster_count: 2,
    effective_config: {},
    warnings: [],
    quality: {},
    boundary_port_type_count: 0,
    external_boundary_port_type_count: 0,
    graph_statistics: {},
    ...patch,
  };
}
