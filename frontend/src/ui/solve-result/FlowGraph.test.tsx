import { renderToStaticMarkup } from 'react-dom/server';
import { ReactFlow } from '@xyflow/react';
import { describe, expect, it } from 'vitest';

import type { ExplorerResponseDto, SolveResultDto } from '../../api/dtos';
import { buildActiveFlowGraph } from '../../domain/solveResultFlow';
import { FlowGraph, normalizeMode, selectedVisualIdExists, toReactFlowEdges } from './FlowGraph';

describe('FlowGraph React Flow shell', () => {
  it('smoke-renders the React Flow component on the server test path', () => {
    const html = renderToStaticMarkup(<ReactFlow nodes={[]} edges={[]} />);

    expect(html).toContain('react-flow');
  });

  it('defaults to sparse overview when sparse data is complete', () => {
    const solveResult = result({ recipe_rates: { r1: 1, r2: 1 }, sparse_clustering: sparseComplete() });
    const graph = buildActiveFlowGraph(solveResult, explorer());

    const html = renderToStaticMarkup(<FlowGraph graph={graph} result={solveResult} />);

    expect(html).toContain('Solved item and recipe flow');
    expect(html).toContain('Graph mode');
    expect(html).toContain('Raw LP flow');
    expect(html).toContain('Optimizer overlay');
    expect(html).not.toContain('Heuristic grouping');
    expect(html).toContain('Overlay source');
    expect(html).toContain('Sparse clustering');
    expect(html).toContain('react-flow-shell');
    expect(html).toContain('Laying out graph');
  });

  it('defaults to raw mode when sparse data is unavailable', () => {
    const solveResult = result({ recipe_rates: { r1: 1 } });
    const graph = buildActiveFlowGraph(solveResult, explorer());

    const html = renderToStaticMarkup(<FlowGraph graph={graph} result={solveResult} />);

    expect(html).not.toContain('Overlay source');
    expect(html).not.toContain('Overlay unavailable');
    expect(html).not.toContain('Heuristic grouping');
    expect(html).toContain('Raw LP flow');
  });

  it('preserves warnings and id-only fallback messaging when explorer metadata is missing', () => {
    const solveResult = result({ recipe_rates: { r1: 1 }, sparse_clustering: sparseComplete() });
    const graph = buildActiveFlowGraph(solveResult, null);

    const html = renderToStaticMarkup(<FlowGraph graph={graph} result={solveResult} initialMode="optimizer-overlay" />);

    expect(html).toContain('Overlay unavailable');
    expect(html).toContain('Explorer metadata is unavailable');
    expect(html).toContain('Displaying raw projection instead.');
    expect(occurrences(html, 'Explorer metadata is unavailable')).toBe(1);
    expect(html).toContain('Graph diagnostics to review');
    expect(html).toContain('Full recipe IO topology is unavailable');
  });

  it('does not duplicate sparse-missing fallback notices in optimizer overlay mode', () => {
    const solveResult = result({ recipe_rates: { r1: 1 } });
    const graph = buildActiveFlowGraph(solveResult, explorer());

    const html = renderToStaticMarkup(<FlowGraph graph={graph} result={solveResult} initialMode="optimizer-overlay" />);

    expect(html).toContain('Overlay unavailable');
    expect(occurrences(html, 'Sparse clustering is unavailable')).toBe(1);
    expect(html).toContain('Displaying raw projection instead.');
  });

  it('styles optional sparse notices as info, not success', () => {
    const solveResult = result({
      recipe_rates: { r1: 1, r2: 1 },
      sparse_clustering: { ...sparseComplete()!, hub_summaries: { items: [], total_count: 1, truncated: true } },
    });
    const graph = buildActiveFlowGraph(solveResult, explorer());

    const html = renderToStaticMarkup(<FlowGraph graph={graph} result={solveResult} />);

    expect(html).toContain('flow-overlay-note info');
    expect(html).toContain('optional-hub-summaries-capped');
    expect(html).not.toContain('optional-hub-summaries-capped</strong><span class="success"');
  });

  it('preserves diagnostic spotlight and details panel empty state', () => {
    const solveResult = result({ unmet_demand: { gear: 2 }, surplus: { junk: 3 } });
    const graph = buildActiveFlowGraph(solveResult, explorer());

    const html = renderToStaticMarkup(<FlowGraph graph={graph} result={solveResult} initialMode="raw" />);

    expect(html).toContain('Unmet demand');
    expect(html).toContain('Surplus');
    expect(html).toContain('Click an item, recipe, diagnostic, or cluster node');
  });

  it('normalizes explicit heuristic initial mode to raw', () => {
    const solveResult = result({ recipe_rates: { r1: 1, r2: 1 }, sparse_clustering: sparseComplete() });
    const graph = buildActiveFlowGraph(solveResult, explorer());

    const html = renderToStaticMarkup(<FlowGraph graph={graph} result={solveResult} initialMode="heuristic" />);

    expect(html).not.toContain('Overlay source');
    expect(html).not.toContain('Heuristic grouping');
    expect(normalizeMode('heuristic')).toBe('raw');
  });

  it('keeps visual edge ids selectable for detail lookup', () => {
    expect(selectedVisualIdExists({
      mode: 'sparse-overview',
      nodes: [{ id: 'cluster:a', visualKind: 'cluster', label: 'A', clusterId: 'a', recipeCount: 1, recipeIds: ['r1'] }, { id: 'item-pool:x', visualKind: 'item-pool', label: 'x', itemId: 'x' }],
      edges: [{ id: 'cluster-net-port:a:x:output', visualKind: 'cluster-net-port', source: 'cluster:a', target: 'item-pool:x', clusterId: 'a', itemId: 'x', direction: 'output', quantity: 1 }],
      notices: [],
      detailById: new Map(),
    }, 'cluster-net-port:a:x:output')).toBe(true);
  });

  it('marks selected React Flow edges', () => {
    const edges = toReactFlowEdges({
      graph: { mode: 'sparse-overview', nodes: [], edges: [], notices: [], detailById: new Map() },
      nodes: [],
      edges: [{ id: 'cluster-net-port:a:x:output', visualKind: 'cluster-net-port', source: 'cluster:a', target: 'item-pool:x', clusterId: 'a', itemId: 'x', direction: 'output', quantity: 1 }],
    }, 'cluster-net-port:a:x:output');

    expect(edges[0]).toMatchObject({ selected: true });
    expect(edges[0].className).toContain('selected');
  });
});

function occurrences(text: string, needle: string) {
  return text.split(needle).length - 1;
}

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

function explorer(): ExplorerResponseDto {
  return {
    package_id: 'test',
    overview: { item_count: 2, fluid_count: 0, recipe_count: 2, item_categories: [], recipe_categories: [] },
    milestones: [],
    items: [],
    recipes: [
      recipe('r1', [], [{ item_id: 'x', amount: 1 }]),
      recipe('r2', [{ item_id: 'x', amount: 1 }], [{ item_id: 'y', amount: 1 }]),
    ],
  };
}

function recipe(id: string, inputs: Array<{ item_id: string; amount: number }>, outputs: Array<{ item_id: string; amount: number }>): ExplorerResponseDto['recipes'][number] {
  const io = (term: { item_id: string; amount: number }) => ({ item_id: term.item_id, amount: term.amount, kind: 'item' as const, category: 'item', terms: [] });
  return { id, category: 'crafting', unlock_condition: { type: 'unknown', id: null }, energy_required: 1, production_cost: 1, source_prototype_type: 'recipe', source_prototype_name: id, inputs: inputs.map(io), outputs: outputs.map(io) };
}

function sparseComplete(): SolveResultDto['sparse_clustering'] {
  return {
    status: 'success',
    message: 'sparse clustering completed',
    mode: 'fast',
    graph_type: 'recipe-to-recipe',
    optimization_effect: 'none',
    engine: 'port-aware',
    cluster_count: 2,
    target_cluster_count: 2,
    effective_config: {},
    warnings: [],
    quality: {},
    boundary_port_type_count: 0,
    net_port_count: 0,
    external_boundary_port_type_count: 0,
    graph_statistics: {},
    cluster_summaries: { items: [{ cluster_id: 'a', recipe_count: 1, recipe_ids: ['r1'] }, { cluster_id: 'b', recipe_count: 1, recipe_ids: ['r2'] }], total_count: 2, truncated: false },
    recipe_assignments: { items: [{ recipe_id: 'r1', cluster_id: 'a' }, { recipe_id: 'r2', cluster_id: 'b' }], total_count: 2, truncated: false },
    boundary_port_types: { items: [{ cluster_id: 'a', item_id: 'x', direction: 'output', net_amount: 1 }, { cluster_id: 'b', item_id: 'x', direction: 'input', net_amount: -1 }], total_count: 2, truncated: false },
  };
}
