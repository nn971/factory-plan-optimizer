import ELK from 'elkjs/lib/elk.bundled.js';

import type { VisualGraph, VisualGraphEdge, VisualGraphNode } from '../../domain/solveResultVisualGraph';

export type PositionedVisualNode = VisualGraphNode & {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type PositionedVisualEdge = VisualGraphEdge;

export type PositionedVisualGraph = {
  graph: VisualGraph;
  nodes: PositionedVisualNode[];
  edges: PositionedVisualEdge[];
};

export type FlowLayoutFailureCode = 'dangling-edge' | 'elk-layout-failed';

export type FlowLayoutResult =
  | { ok: true; graph: PositionedVisualGraph }
  | { ok: false; code: FlowLayoutFailureCode; message: string; graph: VisualGraph };

export type FlowLayoutEngine = {
  layout(graph: ElkInputGraph): Promise<ElkOutputGraph>;
};

export type FlowLayoutOptions = {
  engine?: FlowLayoutEngine;
};

type ElkInputGraph = {
  id: string;
  layoutOptions: Record<string, string>;
  children: Array<{ id: string; width: number; height: number }>;
  edges: Array<{ id: string; sources: string[]; targets: string[] }>;
};

type ElkOutputGraph = ElkInputGraph & {
  children?: Array<{ id: string; x?: number; y?: number; width?: number; height?: number }>;
};

const CLUSTER_DIMENSIONS = { width: 220, height: 96 };
const ITEM_POOL_DIMENSIONS = { width: 180, height: 72 };
const RAW_DIMENSIONS = { width: 160, height: 72 };

export async function layoutVisualGraph(graph: VisualGraph, options: FlowLayoutOptions = {}): Promise<FlowLayoutResult> {
  const dangling = findDanglingEdge(graph);
  if (dangling) {
    return {
      ok: false,
      code: 'dangling-edge',
      message: `Visual edge ${dangling.id} references missing endpoint ${dangling.missingEndpoint}.`,
      graph,
    };
  }

  if (graph.nodes.length === 0) return { ok: true, graph: { graph, nodes: [], edges: [] } };

  const dimensions = new Map(graph.nodes.map((node) => [node.id, nodeDimensions(node)]));
  const elkGraph: ElkInputGraph = {
    id: 'visual-graph',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'RIGHT',
      'elk.spacing.nodeNode': '48',
      'elk.layered.spacing.nodeNodeBetweenLayers': '72',
      'elk.spacing.edgeNode': '24',
      'elk.spacing.edgeEdge': '16',
    },
    children: graph.nodes.map((node) => ({ id: node.id, ...dimensions.get(node.id)! })),
    edges: graph.edges.map((edge) => ({ id: edge.id, sources: [edge.source], targets: [edge.target] })),
  };

  try {
    const engine = options.engine ?? (new ELK() as unknown as FlowLayoutEngine);
    const laidOut = await engine.layout(elkGraph);
    const positionById = new Map<string, { id: string; x?: number; y?: number; width?: number; height?: number }>((laidOut.children ?? []).map((node) => [node.id, node]));
    const nodes = graph.nodes.map((node) => {
      const fallback = dimensions.get(node.id)!;
      const positioned = positionById.get(node.id);
      return {
        ...node,
        x: positioned?.x ?? 0,
        y: positioned?.y ?? 0,
        width: positioned?.width ?? fallback.width,
        height: positioned?.height ?? fallback.height,
      };
    });
    return { ok: true, graph: { graph, nodes, edges: graph.edges } };
  } catch (error) {
    return {
      ok: false,
      code: 'elk-layout-failed',
      message: error instanceof Error ? error.message : 'ELK layout failed.',
      graph,
    };
  }
}

function findDanglingEdge(graph: VisualGraph): { id: string; missingEndpoint: string } | null {
  const nodeIds = new Set(graph.nodes.map((node) => node.id));
  for (const edge of graph.edges) {
    if (!nodeIds.has(edge.source)) return { id: edge.id, missingEndpoint: edge.source };
    if (!nodeIds.has(edge.target)) return { id: edge.id, missingEndpoint: edge.target };
  }
  return null;
}

function nodeDimensions(node: VisualGraphNode): { width: number; height: number } {
  if (node.visualKind === 'item-pool') return ITEM_POOL_DIMENSIONS;
  return node.visualKind === 'cluster' ? CLUSTER_DIMENSIONS : RAW_DIMENSIONS;
}
