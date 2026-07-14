import { describe, expect, it } from 'vitest';

import type { ExplorerResponseDto, SolveResultDto } from '../api/dtos';
import {
  buildActiveFlowGraph,
  buildDisplayFlowGraph,
  buildFlowSelectionDetailIndex,
  buildFlowSelectionDetails,
  buildOptimizerOverlay,
} from './solveResultFlow';

describe('buildActiveFlowGraph', () => {
  it('calculates recipe input and output edges from active rates', () => {
    const graph = buildActiveFlowGraph(result({ recipe_rates: { 'make-gear': 2 } }), explorer());

    expect(edgeSummary(graph.edges)).toEqual([
      ['edge:input:iron-plate:make-gear', 'item:iron-plate', 'recipe:make-gear', 4],
      ['edge:output:make-gear:gear', 'recipe:make-gear', 'item:gear', 2],
    ]);
  });

  it('builds partial ID-only graph without explorer recipe metadata', () => {
    const graph = buildActiveFlowGraph(
      result({
        recipe_rates: { 'make-gear': 2 },
        external_supplies: { 'iron-ore': 3 },
        unmet_demand: { gear: 1 },
        surplus: { plate: 4 },
      }),
      null,
    );

    expect(graph.nodes.map((node) => node.id)).toEqual([
      'diagnostic:external:iron-ore',
      'diagnostic:surplus:plate',
      'diagnostic:unmet:gear',
      'item:gear',
      'item:iron-ore',
      'item:plate',
      'recipe:make-gear',
    ]);
    expect(graph.edges.map((edge) => edge.kind)).toEqual(['external-supply', 'surplus', 'unmet-demand']);
    expect(graph.edges.some((edge) => edge.kind === 'recipe-input' || edge.kind === 'recipe-output')).toBe(false);
    expect(graph.warnings).toContainEqual(expect.objectContaining({ kind: 'recipe-topology-unavailable' }));
  });

  it('creates external supply diagnostics and edges', () => {
    const graph = buildActiveFlowGraph(result({ external_supplies: { 'iron-ore': 3 } }), explorer());

    expect(graph.nodes.map((node) => node.id)).toContain('diagnostic:external:iron-ore');
    expect(graph.diagnostics).toContainEqual({
      id: 'diagnostic:external:iron-ore',
      kind: 'external',
      itemId: 'iron-ore',
      quantity: 3,
      message: '3 iron-ore supplied externally.',
    });
    expect(graph.edges).toContainEqual({
      id: 'edge:external:iron-ore',
      source: 'diagnostic:external:iron-ore',
      target: 'item:iron-ore',
      kind: 'external-supply',
      itemId: 'iron-ore',
      quantity: 3,
    });
  });

  it('creates unmet demand diagnostics and edges', () => {
    const graph = buildActiveFlowGraph(result({ unmet_demand: { gear: 1.5 } }), explorer());

    expect(graph.nodes.map((node) => node.id)).toContain('diagnostic:unmet:gear');
    expect(graph.edges).toContainEqual({
      id: 'edge:unmet:gear',
      source: 'item:gear',
      target: 'diagnostic:unmet:gear',
      kind: 'unmet-demand',
      itemId: 'gear',
      quantity: 1.5,
    });
  });

  it('creates surplus diagnostics and edges', () => {
    const graph = buildActiveFlowGraph(result({ surplus: { gear: 7 } }), explorer());

    expect(graph.nodes.map((node) => node.id)).toContain('diagnostic:surplus:gear');
    expect(graph.edges).toContainEqual({
      id: 'edge:surplus:gear',
      source: 'item:gear',
      target: 'diagnostic:surplus:gear',
      kind: 'surplus',
      itemId: 'gear',
      quantity: 7,
    });
  });

  it('reports missing recipe metadata for active recipes', () => {
    const graph = buildActiveFlowGraph(result({ recipe_rates: { unknown: 4 } }), explorer());

    expect(graph.nodes.map((node) => node.id)).toContain('diagnostic:missing-recipe:unknown');
    expect(graph.diagnostics).toContainEqual({
      id: 'diagnostic:missing-recipe:unknown',
      kind: 'missing-recipe',
      recipeId: 'unknown',
      message: 'Active recipe unknown is missing from explorer recipe metadata.',
    });
    expect(graph.warnings).toContainEqual({
      kind: 'missing-recipe-metadata',
      recipeId: 'unknown',
      value: 4,
      message: 'Active recipe unknown is missing from explorer recipe metadata.',
    });
    expect(graph.edges).toEqual([]);
  });

  it('sorts nodes and edges deterministically', () => {
    const graph = buildActiveFlowGraph(
      result({
        recipe_rates: { 'make-copper': 1, 'make-gear': 1 },
        surplus: { gear: 1, copper: 1 },
      }),
      explorer(),
    );

    expect(graph.nodes.map((node) => node.id)).toEqual([...graph.nodes.map((node) => node.id)].sort());
    expect(graph.edges.map((edge) => edge.id)).toEqual([...graph.edges.map((edge) => edge.id)].sort());
  });

  it('ignores zero, near-zero, and nonpositive recipe rates for flow edges', () => {
    const graph = buildActiveFlowGraph(
      result({ recipe_rates: { zero: 0, near: 1e-10, negative: -1e-10, 'make-gear': 1 } }),
      explorer(),
    );

    expect(graph.edges.map((edge) => edge.recipeId).filter(Boolean)).toEqual(['make-gear', 'make-gear']);
    expect(graph.nodes.map((node) => node.id)).not.toContain('diagnostic:missing-recipe:zero');
    expect(graph.nodes.map((node) => node.id)).not.toContain('diagnostic:missing-recipe:near');
  });

  it('turns negative unexpected values into warnings instead of edges', () => {
    const graph = buildActiveFlowGraph(
      result({ recipe_rates: { bad: -2 }, external_supplies: { ore: -3 }, unmet_demand: { gear: -4 } }),
      explorer(),
    );

    expect(graph.edges).toEqual([]);
    expect(graph.nodes).toEqual([]);
    expect(graph.warnings).toEqual([
      expect.objectContaining({ kind: 'negative-diagnostic-value', itemId: 'gear', field: 'unmet_demand', value: -4 }),
      expect.objectContaining({ kind: 'negative-diagnostic-value', itemId: 'ore', field: 'external_supplies', value: -3 }),
      expect.objectContaining({ kind: 'negative-recipe-rate', recipeId: 'bad', value: -2 }),
    ]);
  });

  it('turns negative recipe input and output amounts into warnings without edges for bad amounts', () => {
    const graph = buildActiveFlowGraph(
      result({ recipe_rates: { 'bad-io': 2 } }),
      {
        ...explorer(),
        recipes: [
          recipe(
            'bad-io',
            [
              { item_id: 'bad-input', amount: -3 },
              { item_id: 'good-input', amount: 4 },
            ],
            [
              { item_id: 'bad-output', amount: -5 },
              { item_id: 'good-output', amount: 6 },
            ],
          ),
        ],
      },
    );

    expect(edgeSummary(graph.edges)).toEqual([
      ['edge:input:good-input:bad-io', 'item:good-input', 'recipe:bad-io', 8],
      ['edge:output:bad-io:good-output', 'recipe:bad-io', 'item:good-output', 12],
    ]);
    expect(graph.edges.map((edge) => edge.itemId)).not.toContain('bad-input');
    expect(graph.edges.map((edge) => edge.itemId)).not.toContain('bad-output');
    expect(graph.warnings).toEqual([
      expect.objectContaining({
        kind: 'negative-recipe-io-amount',
        recipeId: 'bad-io',
        itemId: 'bad-input',
        field: 'inputs',
        value: -3,
      }),
      expect.objectContaining({
        kind: 'negative-recipe-io-amount',
        recipeId: 'bad-io',
        itemId: 'bad-output',
        field: 'outputs',
        value: -5,
      }),
    ]);
  });

  it('does not cluster small graphs', () => {
    const graph = buildActiveFlowGraph(result({ recipe_rates: { 'make-gear': 1 } }), explorer());
    const display = buildDisplayFlowGraph(graph, new Set(), 'heuristic');

    expect(display.clusters).toEqual([]);
    expect(display.nodes.map((node) => node.id)).toEqual(graph.nodes.map((node) => node.id));
  });

  it('collapses deterministic dense components and preserves diagnostic badge quantities', () => {
    const graph = buildActiveFlowGraph(
      result({
        recipe_rates: denseRates(7),
        unmet_demand: { item7: 2 },
        surplus: { item6: 3 },
      }),
      denseExplorer(7),
    );
    const display = buildDisplayFlowGraph(graph, new Set(), 'heuristic');

    expect(display.clusters).toHaveLength(1);
    expect(display.clusters[0]).toMatchObject({
      id: 'cluster:1:diagnostic:surplus:item6',
      nodeCount: 17,
      unmetDemandCount: 1,
      unmetDemandQuantity: 2,
      surplusCount: 1,
      surplusQuantity: 3,
    });
    expect(display.nodes.map((node) => node.id)).toEqual(['cluster:1:diagnostic:surplus:item6']);
    expect(display.edges).toEqual([]);
  });

  it('raw mode does not collapse dense graphs', () => {
    const graph = buildActiveFlowGraph(result({ recipe_rates: denseRates(7), surplus: { item6: 3 } }), denseExplorer(7));
    const display = buildDisplayFlowGraph(graph, new Set(), 'raw');

    expect(display.clusters).toHaveLength(0);
    expect(display.nodes.map((node) => node.id)).toEqual(graph.nodes.map((node) => node.id));
    expect(display.edges.map((edge) => edge.id)).toEqual(graph.edges.map((edge) => edge.id));
  });

  it('expands clusters when requested', () => {
    const graph = buildActiveFlowGraph(result({ recipe_rates: denseRates(7) }), denseExplorer(7));
    const collapsed = buildDisplayFlowGraph(graph, new Set(), 'heuristic');
    const expanded = buildDisplayFlowGraph(graph, new Set([collapsed.clusters[0].id]), 'heuristic');

    expect(expanded.nodes.map((node) => node.id)).toEqual(graph.nodes.map((node) => node.id));
    expect(expanded.edges.map((edge) => edge.source)).toEqual(graph.edges.map((edge) => edge.source));
  });

  it('returns deterministic cluster ids and ordering across repeated calls', () => {
    const graph = buildActiveFlowGraph(result({ recipe_rates: denseRates(7), surplus: { item7: 1 } }), denseExplorer(7));
    const first = buildDisplayFlowGraph(graph, new Set(), 'heuristic');
    const second = buildDisplayFlowGraph(graph, new Set(), 'heuristic');

    expect(second.clusters).toEqual(first.clusters);
    expect(second.nodes.map((node) => node.id)).toEqual(first.nodes.map((node) => node.id));
  });

  it('summarizes selected item and recipe details with exact quantities', () => {
    const solveResult = result({ recipe_rates: { 'make-gear': 2 }, external_supplies: { 'iron-plate': 4 } });
    const graph = buildActiveFlowGraph(solveResult, explorer());

    expect(buildFlowSelectionDetails(graph, 'item:iron-plate', solveResult)).toMatchObject({
      id: 'item:iron-plate',
      kind: 'item',
      rows: expect.arrayContaining([
        expect.objectContaining({ label: 'Incoming external-supply', quantity: 4 }),
        expect.objectContaining({ label: 'Outgoing recipe-input', quantity: 4 }),
      ]),
    });
    expect(buildFlowSelectionDetails(graph, 'recipe:make-gear', solveResult)).toMatchObject({
      id: 'recipe:make-gear',
      kind: 'recipe',
      rows: expect.arrayContaining([expect.objectContaining({ label: 'Recipe rate', id: 'make-gear', quantity: 2 })]),
    });
  });

  it('summarizes selected diagnostic and cluster details', () => {
    const solveResult = result({ recipe_rates: denseRates(7), unmet_demand: { item7: 2 }, surplus: { item6: 3 } });
    const graph = buildActiveFlowGraph(solveResult, denseExplorer(7));
    const clusterId = buildDisplayFlowGraph(graph, new Set(), 'heuristic').clusters[0].id;

    expect(buildFlowSelectionDetails(graph, 'diagnostic:unmet:item7', solveResult)).toMatchObject({
      id: 'diagnostic:unmet:item7',
      kind: 'diagnostic',
      rows: expect.arrayContaining([expect.objectContaining({ label: 'Quantity', quantity: 2 })]),
    });
    expect(buildFlowSelectionDetails(graph, clusterId, solveResult)).toMatchObject({
      id: clusterId,
      kind: 'cluster',
      rows: expect.arrayContaining([
        expect.objectContaining({ label: 'Unmet demand quantity', quantity: 2 }),
        expect.objectContaining({ label: 'Surplus quantity', quantity: 3 }),
      ]),
    });
  });

  it('builds selection detail index from provided display clusters', () => {
    const solveResult = result({ recipe_rates: denseRates(7), unmet_demand: { item7: 2 } });
    const graph = buildActiveFlowGraph(solveResult, denseExplorer(7));
    const display = buildDisplayFlowGraph(graph, new Set(), 'heuristic');
    const index = buildFlowSelectionDetailIndex(graph, solveResult, display.clusters);

    expect(index.detailById.get('recipe:chain-0')).toMatchObject({ kind: 'recipe' });
    expect(index.detailById.get(display.clusters[0].id)).toMatchObject({
      kind: 'cluster',
      rows: expect.arrayContaining([expect.objectContaining({ label: 'Unmet demand quantity', quantity: 2 })]),
    });
    expect(buildFlowSelectionDetailIndex(graph, solveResult, []).detailById.has(display.clusters[0].id)).toBe(false);
  });

  it('builds complete sparse overlay labels for active recipes', () => {
    const solveResult = result({
      recipe_rates: { 'make-gear': 2, 'make-copper': 1 },
      sparse_clustering: sparseAssignments([
        ['make-gear', 1],
        ['make-copper', 2],
      ]),
    });
    const graph = buildActiveFlowGraph(solveResult, explorer());

    const overlay = buildOptimizerOverlay(graph, solveResult);

    expect(overlay).toMatchObject({
      available: true,
      source: 'sparse',
      label: 'Sparse clustering',
    });
    expect(overlay.available ? [...overlay.recipeToCluster.entries()] : []).toEqual([
      ['make-copper', '2'],
      ['make-gear', '1'],
    ]);
  });

  it('warns instead of rendering partial sparse overlay when assignments are capped or missing active recipes', () => {
    const truncatedResult = result({
      recipe_rates: { 'make-gear': 2 },
      sparse_clustering: sparseAssignments([['make-gear', 1]], true),
    });
    const truncatedGraph = buildActiveFlowGraph(truncatedResult, explorer());

    expect(buildOptimizerOverlay(truncatedGraph, truncatedResult)).toEqual({
      available: false,
      reason: 'Sparse cluster assignments were capped, so cluster overlay is unavailable.',
    });

    const missingResult = result({
      recipe_rates: { 'make-gear': 2, 'make-copper': 1 },
      sparse_clustering: sparseAssignments([['make-gear', 1]]),
    });
    const missingGraph = buildActiveFlowGraph(missingResult, explorer());

    expect(buildOptimizerOverlay(missingGraph, missingResult)).toEqual({
      available: false,
      reason: 'Sparse cluster assignments do not cover every active recipe node.',
    });
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

function explorer(): ExplorerResponseDto {
  return {
    package_id: 'test',
    overview: { item_count: 4, fluid_count: 0, recipe_count: 2, item_categories: [], recipe_categories: [] },
    milestones: [],
    items: [],
    recipes: [
      recipe('make-gear', [{ item_id: 'iron-plate', amount: 2 }], [{ item_id: 'gear', amount: 1 }]),
      recipe('make-copper', [{ item_id: 'copper-ore', amount: 1 }], [{ item_id: 'copper', amount: 1 }]),
    ],
  };
}

function recipe(
  id: string,
  inputs: Array<{ item_id: string; amount: number }>,
  outputs: Array<{ item_id: string; amount: number }>,
) {
  return {
    id,
    category: 'crafting',
    unlock_condition: { type: 'start-unlocked' as const, id: null },
    energy_required: 1,
    production_cost: 0,
    source_prototype_type: 'recipe' as const,
    source_prototype_name: id,
    inputs: inputs.map((input) => io(input.item_id, input.amount)),
    outputs: outputs.map((output) => io(output.item_id, output.amount)),
  };
}

function io(itemId: string, amount: number) {
  return {
    item_id: itemId,
    kind: 'item' as const,
    category: 'item',
    amount,
    terms: [],
  };
}

function edgeSummary(edges: ReturnType<typeof buildActiveFlowGraph>['edges']) {
  return edges.map((edge) => [edge.id, edge.source, edge.target, edge.quantity]);
}

function denseRates(count: number) {
  return Object.fromEntries(Array.from({ length: count }, (_, index) => [`chain-${index}`, 1]));
}

function denseExplorer(count: number): ExplorerResponseDto {
  return {
    ...explorer(),
    recipes: Array.from({ length: count }, (_, index) =>
      recipe(`chain-${index}`, [{ item_id: `item${index}`, amount: 1 }], [{ item_id: `item${index + 1}`, amount: 1 }]),
    ),
  };
}

function sparseAssignments(assignments: Array<[string, string | number]>, truncated = false): SolveResultDto['sparse_clustering'] {
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
    recipe_assignments: {
      items: assignments.map(([recipe_id, cluster_id]) => ({ recipe_id, cluster_id })),
      total_count: assignments.length,
      truncated,
    },
  };
}
