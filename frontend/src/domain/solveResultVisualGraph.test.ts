import { describe, expect, it } from 'vitest';

import type { SolveResultDto, SparseClusteringResultDto } from '../api/dtos';
import type { ActiveFlowGraph } from './solveResultFlow';
import { buildSolveResultVisualGraph, visualId } from './solveResultVisualGraph';

describe('buildSolveResultVisualGraph', () => {
  it('builds a complete sparse overview with escaped deterministic ids and details', () => {
    const visual = build(sparse({
      cluster_summaries: cap([
        { cluster_id: 'A/1', recipe_count: 1, recipe_ids: ['r1'], net_input_port_count: 1 },
        { cluster_id: 'B:2', recipe_count: 1, recipe_ids: ['r2'], net_output_port_count: 1 },
      ]),
      recipe_assignments: cap([{ recipe_id: 'r1', cluster_id: 'A/1' }, { recipe_id: 'r2', cluster_id: 'B:2' }]),
      boundary_port_types: cap([{ cluster_id: 'A/1', item_id: 'iron plate', direction: 'output', net_amount: 3 }, { cluster_id: 'B:2', item_id: 'iron plate', direction: 'input', net_amount: -3 }]),
    }));

    expect(visual.mode).toBe('sparse-overview');
    expect(visual.nodes.map((node) => node.id)).toEqual(['cluster:A%2F1', 'cluster:B%3A2', 'item-pool:iron%20plate']);
    expect(visual.edges).toContainEqual(expect.objectContaining({
      id: 'cluster-net-port:A%2F1:iron%20plate:output',
      visualKind: 'cluster-net-port',
      clusterId: 'A/1',
      direction: 'output',
      itemId: 'iron plate',
      quantity: 3,
    }));
    expect(visual.detailById.get('cluster:A%2F1')?.rows).toContainEqual({ label: 'Cluster', id: 'A/1' });
    expectEdgesHavePresentEndpoints(visual);
  });

  it('falls back when required sparse arrays are capped', () => {
    const visual = build(sparse({ cluster_summaries: cap([{ cluster_id: 'a', recipe_count: 1, recipe_ids: ['r1'] }], true) }));
    expect(rawCodes(visual)).toContain('sparse-required-truncated');
  });

  it('allows optional capped arrays with notices', () => {
    const visual = build(sparse({ hub_summaries: cap([], true) }));
    expect(visual.mode).toBe('sparse-overview');
    expect(visual.notices.map((notice) => notice.code)).toEqual(['optional-hub-summaries-capped']);
    expectEdgesHavePresentEndpoints(visual);
  });

  it('falls back for missing sparse data and failed sparse status', () => {
    expect(rawCodes(build(null))).toContain('sparse-missing');
    expect(rawCodes(build(sparse({ status: 'failed' })))).toContain('sparse-non-success');
  });

  it('uses explorer-null id-only raw fallback and preserves diagnostic raw edges', () => {
    const visual = build(sparse(), false, graphWithDiagnostics());
    expect(visual.mode).toBe('raw');
    expect(visual.notices.map((notice) => notice.code)).toContain('explorer-metadata-missing');
    expect(visual.edges.map((edge) => edge.id)).toEqual(['edge:external:ore', 'edge:unmet:gear', 'edge:surplus:junk']);
  });

  it('returns an empty raw graph for successful sparse data with no active recipes', () => {
    const visual = build(sparse(), true, { nodes: [], edges: [], diagnostics: [], warnings: [] }, { recipe_rates: {} });
    expect(visual).toMatchObject({ mode: 'raw', nodes: [], edges: [], notices: [] });
  });

  it('preserves raw diagnostics when there are no positive recipe rates', () => {
    const visual = build(sparse(), true, graphWithDiagnostics(), { recipe_rates: {} });
    expect(visual.mode).toBe('raw');
    expect(visual.edges.map((edge) => edge.id)).toEqual(['edge:external:ore', 'edge:unmet:gear', 'edge:surplus:junk']);
  });

  it('uses result recipe rates to require assignments for active missing-recipe diagnostics', () => {
    const graph: ActiveFlowGraph = { nodes: [{ id: 'diagnostic:missing-recipe:r3', kind: 'diagnostic', diagnosticKind: 'missing-recipe', label: 'missing', recipeId: 'r3' }], edges: [], diagnostics: [], warnings: [] };
    expect(rawCodes(build(sparse(), true, graph, { recipe_rates: { r3: 1 } }))).toContain('missing-active-recipe-assignment');
  });

  it('preserves external, unmet, surplus, and missing-recipe diagnostics in sparse overview', () => {
    const graph = graphWithDiagnostics();
    graph.nodes.push({ id: 'diagnostic:missing-recipe:r-missing', kind: 'diagnostic', diagnosticKind: 'missing-recipe', label: 'Missing', recipeId: 'r-missing' });
    const visual = build(sparse(), true, graph);
    expect(visual.mode).toBe('sparse-overview');
    expect(visual.nodes.map((node) => node.id)).toEqual([
      'cluster:a', 'cluster:b', 'item-pool:x', 'diagnostic:external:ore', 'diagnostic:missing-recipe:r-missing', 'diagnostic:surplus:junk', 'diagnostic:unmet:gear',
    ]);
    expect(visual.detailById.get('diagnostic:external:ore')?.summary).toBeDefined();
    expect(visual.detailById.get('diagnostic:missing-recipe:r-missing')?.summary).toBeDefined();
    expect(visual.edges.map((edge) => edge.id)).toEqual(['cluster-net-port:a:x:output', 'cluster-net-port:b:x:input']);
    expectEdgesHavePresentEndpoints(visual);
  });

  it.each([
    ['duplicate-recipe-assignment', sparse({ recipe_assignments: cap([{ recipe_id: 'r1', cluster_id: 'a' }, { recipe_id: 'r1', cluster_id: 'a' }, { recipe_id: 'r2', cluster_id: 'b' }]) })],
    ['unknown-assignment-cluster', sparse({ recipe_assignments: cap([{ recipe_id: 'r1', cluster_id: 'missing' }, { recipe_id: 'r2', cluster_id: 'b' }]) })],
    ['unknown-boundary-cluster', sparse({ boundary_port_types: cap([{ cluster_id: 'missing', item_id: 'x', direction: 'input', net_amount: -1 }]) })],
    ['missing-active-recipe-assignment', sparse({ recipe_assignments: cap([{ recipe_id: 'r1', cluster_id: 'a' }]) })],
    ['duplicate-cluster-summary', sparse({ cluster_summaries: cap([{ cluster_id: 'a', recipe_count: 1, recipe_ids: ['r1'] }, { cluster_id: 'a', recipe_count: 1, recipe_ids: ['r2'] }]) })],
    ['cluster-summary-assignment-mismatch', sparse({ cluster_summaries: cap([{ cluster_id: 'a', recipe_count: 2, recipe_ids: ['r1'] }, { cluster_id: 'b', recipe_count: 1, recipe_ids: ['r2'] }]) })],
  ])('falls back for invalid sparse data: %s', (code, sparseResult) => {
    expect(rawCodes(build(sparseResult))).toContain(code);
  });

  it.each([
    ['cluster_summaries'],
    ['boundary_port_types'],
  ] as const)('falls back when required sparse array is missing: %s', (field) => {
    expect(rawCodes(build(sparse({ [field]: null })))).toContain('sparse-required-missing');
  });

  it.each([
    ['cluster_summaries', cap([{ cluster_id: 'a', recipe_count: 1, recipe_ids: ['r1'] }], false, 2)],
    ['boundary_port_types', cap([{ cluster_id: 'a', item_id: 'x', direction: 'output', net_amount: 1 }], false, 2)],
  ] as const)('falls back for required array count mismatch: %s', (field, value) => {
    expect(rawCodes(build(sparse({ [field]: value })))).toContain('sparse-required-count-mismatch');
  });

  it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY])('falls back for invalid output net quantity %s', (net_amount) => {
    expect(rawCodes(build(sparse({ boundary_port_types: cap([{ cluster_id: 'a', item_id: 'x', direction: 'output', net_amount }]) })))).toContain('invalid-boundary-quantity');
  });

  it('renders net ports through item pools and keeps directions separate', () => {
    const visual = build(sparse({ boundary_port_types: cap([
      { cluster_id: 'a', item_id: 'x', direction: 'output', net_amount: 3 },
      { cluster_id: 'b', item_id: 'x', direction: 'input', net_amount: -4 },
    ]) }));
    expect(visual.edges.map((edge) => [edge.id, edge.quantity])).toEqual([
      ['cluster-net-port:a:x:output', 3],
      ['cluster-net-port:b:x:input', 4],
    ]);
    expectEdgesHavePresentEndpoints(visual);
  });

  it('sorts nodes and edges deterministically', () => {
    const visual = build(sparse({
      cluster_summaries: cap([{ cluster_id: 'b', recipe_count: 1, recipe_ids: ['r2'] }, { cluster_id: 'a', recipe_count: 1, recipe_ids: ['r1'] }]),
      recipe_assignments: cap([{ recipe_id: 'r2', cluster_id: 'b' }, { recipe_id: 'r1', cluster_id: 'a' }]),
      boundary_port_types: cap([{ cluster_id: 'b', item_id: 'z', direction: 'output', net_amount: 1 }, { cluster_id: 'a', item_id: 'a', direction: 'input', net_amount: -1 }]),
    }));
    expect(visual.nodes.map((node) => node.id)).toEqual(['cluster:a', 'cluster:b', 'item-pool:a', 'item-pool:z']);
    expect(visual.edges.map((edge) => edge.id)).toEqual(['cluster-net-port:b:z:output', 'cluster-net-port:a:a:input']);
    expectEdgesHavePresentEndpoints(visual);
  });
});

describe('visualId', () => {
  it('url-encodes segments', () => {
    expect(visualId('cluster-net-port', 'a/b', 'iron plate', 'output')).toBe('cluster-net-port:a%2Fb:iron%20plate:output');
  });
});

function build(sparseClustering: SparseClusteringResultDto | null, explorerMetadataAvailable = true, graph = activeGraph(), resultOverrides: Partial<SolveResultDto> = {}) {
  return buildSolveResultVisualGraph(graph, result(sparseClustering, resultOverrides), { explorerMetadataAvailable });
}

function rawCodes(visual: ReturnType<typeof buildSolveResultVisualGraph>) {
  expect(visual.mode).toBe('raw');
  return visual.notices.map((notice) => notice.code);
}

function expectEdgesHavePresentEndpoints(visual: ReturnType<typeof buildSolveResultVisualGraph>) {
  const nodeIds = new Set(visual.nodes.map((node) => node.id));
  for (const edge of visual.edges) {
    expect(nodeIds.has(edge.source), `${edge.id} source ${edge.source}`).toBe(true);
    expect(nodeIds.has(edge.target), `${edge.id} target ${edge.target}`).toBe(true);
  }
}

function activeGraph(): ActiveFlowGraph {
  return {
    nodes: [{ id: 'recipe:r1', kind: 'recipe', label: 'r1', recipeId: 'r1' }, { id: 'recipe:r2', kind: 'recipe', label: 'r2', recipeId: 'r2' }],
    edges: [{ id: 'edge:raw', source: 'recipe:r1', target: 'recipe:r2', kind: 'recipe-output', quantity: 1, itemId: 'x' }],
    diagnostics: [],
    warnings: [],
  };
}

function graphWithDiagnostics(): ActiveFlowGraph {
  return {
    nodes: [
      { id: 'diagnostic:external:ore', kind: 'diagnostic', diagnosticKind: 'external', label: 'External', itemId: 'ore', quantity: 1 },
      { id: 'diagnostic:surplus:junk', kind: 'diagnostic', diagnosticKind: 'surplus', label: 'Surplus', itemId: 'junk', quantity: 2 },
      { id: 'diagnostic:unmet:gear', kind: 'diagnostic', diagnosticKind: 'unmet', label: 'Unmet', itemId: 'gear', quantity: 3 },
    ],
    edges: [
      { id: 'edge:external:ore', source: 'diagnostic:external:ore', target: 'item:ore', kind: 'external-supply', itemId: 'ore', quantity: 1 },
      { id: 'edge:surplus:junk', source: 'item:junk', target: 'diagnostic:surplus:junk', kind: 'surplus', itemId: 'junk', quantity: 2 },
      { id: 'edge:unmet:gear', source: 'item:gear', target: 'diagnostic:unmet:gear', kind: 'unmet-demand', itemId: 'gear', quantity: 3 },
    ],
    diagnostics: [],
    warnings: [],
  };
}

function result(sparse_clustering: SparseClusteringResultDto | null, overrides: Partial<SolveResultDto> = {}): SolveResultDto {
  return { solver_status: 'optimal', objective_value: 1, objective_components: {}, recipe_rates: { r1: 1, r2: 1 }, external_supplies: {}, unmet_demand: {}, surplus: {}, balance_residuals: {}, sparse_clustering, ...overrides };
}

function sparse(overrides: Partial<SparseClusteringResultDto> = {}): SparseClusteringResultDto {
  return {
    status: 'success', message: '', mode: 'fast', graph_type: 'recipe-to-recipe', optimization_effect: 'none', engine: null, cluster_count: 2, target_cluster_count: 2, effective_config: {}, warnings: [], quality: null, boundary_port_type_count: null, external_boundary_port_type_count: null, graph_statistics: null,
    cluster_summaries: cap([{ cluster_id: 'a', recipe_count: 1, recipe_ids: ['r1'] }, { cluster_id: 'b', recipe_count: 1, recipe_ids: ['r2'] }]),
    recipe_assignments: cap([{ recipe_id: 'r1', cluster_id: 'a' }, { recipe_id: 'r2', cluster_id: 'b' }]),
    boundary_port_types: cap([{ cluster_id: 'a', item_id: 'x', direction: 'output', net_amount: 1 }, { cluster_id: 'b', item_id: 'x', direction: 'input', net_amount: -1 }]),
    ...overrides,
  };
}

function cap<T extends Record<string, unknown>>(items: T[], truncated = false, totalCount = truncated ? items.length + 1 : items.length) {
  return { items, total_count: totalCount, truncated };
}
