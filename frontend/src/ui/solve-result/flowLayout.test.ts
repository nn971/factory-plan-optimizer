import { describe, expect, it } from 'vitest';

import type { VisualGraph } from '../../domain/solveResultVisualGraph';
import { layoutVisualGraph, type FlowLayoutEngine } from './flowLayout';

describe('layoutVisualGraph', () => {
  it('lays out a small sparse overview with stable ids and endpoints', async () => {
    const graph = sparseGraph();
    const result = await layoutVisualGraph(graph, { engine: deterministicEngine() });

    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error(result.message);
    expect(result.graph.graph).toBe(graph);
    expect(result.graph.nodes.map((node) => [node.id, node.x, node.y, node.width, node.height])).toEqual([
      ['cluster:a', 0, 0, 220, 96],
      ['cluster:b', 100, 50, 220, 96],
      ['item-pool:x', 200, 100, 180, 72],
    ]);
    expect(result.graph.edges.map((edge) => [edge.id, edge.source, edge.target])).toEqual([
      ['cluster-net-port:a:x:output', 'cluster:a', 'item-pool:x'],
    ]);
  });

  it('lays out a raw graph with raw dimensions', async () => {
    const graph = rawGraph();
    const result = await layoutVisualGraph(graph, { engine: deterministicEngine() });

    expect(result.ok).toBe(true);
    if (!result.ok) throw new Error(result.message);
    expect(result.graph.nodes.map((node) => [node.id, node.width, node.height])).toEqual([
      ['item:x', 160, 72],
      ['recipe:r1', 160, 72],
    ]);
    expect(result.graph.edges[0]).toMatchObject({ id: 'edge:raw', source: 'recipe:r1', target: 'item:x' });
  });

  it('returns dangling-edge failure before invoking ELK', async () => {
    let invoked = false;
    const result = await layoutVisualGraph(
      { ...sparseGraph(), edges: [{ ...sparseGraph().edges[0], target: 'missing' }] },
      { engine: { async layout() { invoked = true; throw new Error('should not run'); } } },
    );

    expect(result).toMatchObject({ ok: false, code: 'dangling-edge', graph: expect.any(Object) });
    expect(invoked).toBe(false);
  });

  it('returns empty positioned graph for empty input', async () => {
    const graph: VisualGraph = { mode: 'raw', nodes: [], edges: [], notices: [], detailById: new Map() };
    const result = await layoutVisualGraph(graph, { engine: deterministicEngine() });

    expect(result).toEqual({ ok: true, graph: { graph, nodes: [], edges: [] } });
  });

  it('returns explicit failure and preserves input graph when ELK fails', async () => {
    const graph = sparseGraph();
    const result = await layoutVisualGraph(graph, { engine: { async layout() { throw new Error('layout boom'); } } });

    expect(result).toEqual({ ok: false, code: 'elk-layout-failed', message: 'layout boom', graph });
  });
});

function deterministicEngine(): FlowLayoutEngine {
  return {
    async layout(graph) {
      return {
        ...graph,
        children: graph.children.map((node, index) => ({ ...node, x: index * 100, y: index * 50 })),
      };
    },
  };
}

function sparseGraph(): VisualGraph {
  return {
    mode: 'sparse-overview',
    nodes: [
      { id: 'cluster:a', visualKind: 'cluster', label: 'Cluster a', clusterId: 'a', recipeCount: 1, recipeIds: ['r1'] },
      { id: 'cluster:b', visualKind: 'cluster', label: 'Cluster b', clusterId: 'b', recipeCount: 1, recipeIds: ['r2'] },
      { id: 'item-pool:x', visualKind: 'item-pool', label: 'x', itemId: 'x' },
    ],
    edges: [{ id: 'cluster-net-port:a:x:output', visualKind: 'cluster-net-port', source: 'cluster:a', target: 'item-pool:x', clusterId: 'a', itemId: 'x', direction: 'output', quantity: 2 }],
    notices: [],
    detailById: new Map(),
  };
}

function rawGraph(): VisualGraph {
  return {
    mode: 'raw',
    nodes: [
      { id: 'item:x', visualKind: 'raw', kind: 'item', label: 'x', itemId: 'x' },
      { id: 'recipe:r1', visualKind: 'raw', kind: 'recipe', label: 'r1', recipeId: 'r1' },
    ],
    edges: [{ id: 'edge:raw', visualKind: 'raw', source: 'recipe:r1', target: 'item:x', kind: 'recipe-output', quantity: 1, itemId: 'x', recipeId: 'r1' }],
    notices: [],
    detailById: new Map(),
  };
}
