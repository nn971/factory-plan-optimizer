import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { SolveResultDto } from '../../api/dtos';
import type { DisplayFlowNode } from '../../domain/solveResultFlow';
import { buildActiveFlowGraph } from '../../domain/solveResultFlow';
import { FlowGraph, layoutFlowGraphNodes } from './FlowGraph';

describe('FlowGraph graph modes', () => {
  it('renders sparse overlay cluster badges only when the mapping is complete', () => {
    const solveResult = result({
      recipe_rates: { 'make-gear': 1 },
      sparse_clustering: sparseAssignments([['make-gear', 4]]),
    });
    const graph = buildActiveFlowGraph(solveResult, null);

    const html = renderToStaticMarkup(<FlowGraph graph={graph} result={solveResult} initialMode="optimizer-overlay" />);

    expect(html).toContain('Overlay source');
    expect(html).toContain('Sparse clustering');
    expect(html).toContain('C 4');
  });

  it('warns and skips partial overlay when sparse assignments are truncated', () => {
    const solveResult = result({
      recipe_rates: { 'make-gear': 1 },
      sparse_clustering: sparseAssignments([['make-gear', 4]], true),
    });
    const graph = buildActiveFlowGraph(solveResult, null);

    const html = renderToStaticMarkup(<FlowGraph graph={graph} result={solveResult} initialMode="optimizer-overlay" />);

    expect(html).toContain('Overlay unavailable');
    expect(html).toContain('Sparse cluster assignments were capped');
    expect(html).not.toContain('C 4');
  });

  it('uses a compact one-column layout for partial recipe-only graphs', () => {
    const layout = layoutFlowGraphNodes([{ id: 'recipe:make-gear', kind: 'recipe', recipeId: 'make-gear', label: 'make-gear' }]);

    expect(layout.width).toBe(560);
    expect(layout.nodes[0]).toMatchObject({ x: 280, y: 64, column: 0 });
    expect(layout.height).toBe(142);
  });

  it('adapts width and vertical rhythm to graph density', () => {
    const sparseLayout = layoutFlowGraphNodes([
      { id: 'diagnostic:external:ore', kind: 'diagnostic', diagnosticKind: 'external', itemId: 'ore', label: 'External supply: ore' },
      { id: 'item:ore', kind: 'item', itemId: 'ore', label: 'ore' },
      { id: 'recipe:plate', kind: 'recipe', recipeId: 'plate', label: 'plate' },
      { id: 'diagnostic:surplus:plate', kind: 'diagnostic', diagnosticKind: 'surplus', itemId: 'plate', label: 'Surplus: plate' },
    ]);
    const denseNodes: DisplayFlowNode[] = Array.from({ length: 26 }, (_, index) => ({
      id: `item:${index}`,
      kind: 'item',
      itemId: `item-${index}`,
      label: `item-${index}`,
    }));
    const denseLayout = layoutFlowGraphNodes(denseNodes);

    expect(sparseLayout.width).toBeLessThan(920);
    expect(sparseLayout.nodes.map((node) => node.column)).toEqual([0, 1, 2, 3]);
    expect(denseLayout.width).toBe(560);
    expect(denseLayout.height).toBeLessThan(64 + 25 * 66 + 78);
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

function sparseAssignments(assignments: Array<[string, string | number]>, truncated = false): SolveResultDto['sparse_clustering'] {
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
