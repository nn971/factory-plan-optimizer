import type { SolveResultDto, SparseCappedArrayDto, SparseClusteringResultDto } from '../api/dtos';
import type { ActiveFlowGraph, FlowEdge, FlowNode, FlowSelectionDetails } from './solveResultFlow';
import { buildFlowSelectionDetailIndex } from './solveResultFlow';
import { EPSILON } from './solveOutcome';

export type VisualGraphMode = 'raw' | 'sparse-overview';
export type VisualNoticeSeverity = 'info' | 'warning';

export type VisualGraphNotice = {
  severity: VisualNoticeSeverity;
  code: string;
  message: string;
};

export type VisualGraphNode =
  | (FlowNode & { visualKind: 'raw' })
  | { id: string; visualKind: 'item-pool'; label: string; itemId: string }
  | {
      id: string;
      visualKind: 'cluster';
      label: string;
      clusterId: string;
      recipeCount: number;
      recipeIds: string[];
      netInputPortCount?: number;
      netOutputPortCount?: number;
      netPortCount?: number;
    };

export type VisualGraphEdge =
  | (FlowEdge & { visualKind: 'raw' })
  | {
      id: string;
      visualKind: 'cluster-net-port';
      source: string;
      target: string;
      itemId: string;
      clusterId: string;
      direction: 'input' | 'output';
      quantity: number;
    };

export type VisualGraph = {
  mode: VisualGraphMode;
  nodes: VisualGraphNode[];
  edges: VisualGraphEdge[];
  notices: VisualGraphNotice[];
  detailById: Map<string, FlowSelectionDetails>;
};

export type BuildVisualGraphOptions = {
  explorerMetadataAvailable: boolean;
};

export function visualId(prefix: string, ...segments: Array<string | number>): string {
  return [prefix, ...segments.map((segment) => encodeURIComponent(String(segment)))].join(':');
}

export function buildSolveResultVisualGraph(
  graph: ActiveFlowGraph,
  result: SolveResultDto,
  options: BuildVisualGraphOptions,
): VisualGraph {
  if (!options.explorerMetadataAvailable) {
    return rawVisualGraph(graph, result, [{ severity: 'warning', code: 'explorer-metadata-missing', message: 'Explorer metadata is unavailable; showing id-only raw graph.' }]);
  }

  const activeRecipeIds = activeRecipes(result);
  if (activeRecipeIds.length === 0) return rawVisualGraph(graph, result, []);

  const sparse = validateSparse(result.sparse_clustering, activeRecipeIds);
  if (!sparse.ok) return rawVisualGraph(graph, result, [{ severity: 'warning', code: sparse.code, message: sparse.message }]);

  const optionalNotices = optionalSparseNotices(result.sparse_clustering!);
  const diagnosticNodeIds = new Set(graph.nodes.filter((node) => node.kind === 'diagnostic').map((node) => node.id));
  const rawDiagnosticNodes = graph.nodes
    .filter((node) => diagnosticNodeIds.has(node.id))
    .map((node) => ({ ...node, visualKind: 'raw' as const }));
  const itemNodes = [...sparse.itemIds].map((itemId) => ({ id: visualId('item-pool', itemId), visualKind: 'item-pool' as const, label: itemId, itemId }));
  const nodes = [...sparse.clusters.map((cluster) => ({
    id: visualId('cluster', cluster.clusterId),
    visualKind: 'cluster' as const,
    label: cluster.label,
    clusterId: cluster.clusterId,
    recipeCount: cluster.recipeCount,
    recipeIds: cluster.recipeIds,
    netInputPortCount: cluster.netInputPortCount,
    netOutputPortCount: cluster.netOutputPortCount,
    netPortCount: cluster.netPortCount,
  })), ...itemNodes, ...rawDiagnosticNodes].sort(compareVisualNodes);

  const edges = sparse.netPorts.map((port) => ({
    id: visualId('cluster-net-port', port.clusterId, port.itemId, port.direction),
    visualKind: 'cluster-net-port' as const,
    source: port.direction === 'output' ? visualId('cluster', port.clusterId) : visualId('item-pool', port.itemId),
    target: port.direction === 'output' ? visualId('item-pool', port.itemId) : visualId('cluster', port.clusterId),
    ...port,
  })).sort(compareVisualEdges);

  const detailById = new Map<string, FlowSelectionDetails>();
  for (const node of nodes) {
    if (node.visualKind === 'raw') continue;
    if (node.visualKind === 'item-pool') {
      detailById.set(node.id, { id: node.id, kind: 'item', label: node.itemId, summary: 'Item pool connecting authoritative cluster net ports.', rows: [{ label: 'Item', id: node.itemId }] });
      continue;
    }
    detailById.set(node.id, { id: node.id, kind: 'cluster', label: node.label, summary: `${node.recipeCount} active recipes.`, rows: [
      { label: 'Cluster', id: node.clusterId },
      { label: 'Recipes', quantity: node.recipeCount },
      { label: 'Net input ports', quantity: node.netInputPortCount },
      { label: 'Net output ports', quantity: node.netOutputPortCount },
      { label: 'Net ports', quantity: node.netPortCount },
    ].filter((row) => row.id !== undefined || row.quantity !== undefined) });
  }
  for (const edge of edges) {
    detailById.set(edge.id, { id: edge.id, kind: 'cluster', label: `${edge.itemId}: cluster ${edge.clusterId} ${edge.direction}`, summary: `Authoritative cluster net ${edge.direction}.`, rows: [
      { label: 'Cluster', id: edge.clusterId },
      { label: 'Item', id: edge.itemId },
      { label: 'Direction', id: edge.direction },
      { label: 'Quantity', quantity: edge.quantity },
    ] });
  }
  const rawDetails = buildFlowSelectionDetailIndex(graph, result, []).detailById;
  for (const node of rawDiagnosticNodes) {
    const detail = rawDetails.get(node.id);
    if (detail) detailById.set(node.id, detail);
  }

  return { mode: 'sparse-overview', nodes, edges, notices: optionalNotices, detailById };
}

function rawVisualGraph(graph: ActiveFlowGraph, result: SolveResultDto, notices: VisualGraphNotice[]): VisualGraph {
  return {
    mode: 'raw',
    nodes: graph.nodes.map((node) => ({ ...node, visualKind: 'raw' as const })).sort(compareVisualNodes),
    edges: graph.edges.map((edge) => ({ ...edge, visualKind: 'raw' as const })).sort(compareVisualEdges),
    notices,
    detailById: buildFlowSelectionDetailIndex(graph, result, []).detailById,
  };
}

type SparseOk = { ok: true; clusters: ValidCluster[]; netPorts: NetPortEdge[]; itemIds: Set<string> };
type SparseBad = { ok: false; code: string; message: string };
type ValidCluster = { clusterId: string; label: string; recipeCount: number; recipeIds: string[]; netInputPortCount?: number; netOutputPortCount?: number; netPortCount?: number };
type NetPortEdge = { clusterId: string; itemId: string; direction: 'input' | 'output'; quantity: number };

function validateSparse(sparse: SparseClusteringResultDto | null | undefined, activeRecipeIds: string[]): SparseOk | SparseBad {
  if (!sparse) return bad('sparse-missing', 'Sparse clustering is unavailable; showing raw graph.');
  if (sparse.status !== 'success') return bad('sparse-non-success', `Sparse clustering status is ${sparse.status}; showing raw graph.`);
  const required = requiredArray(sparse.cluster_summaries, 'cluster summaries') ?? requiredArray(sparse.boundary_port_types, 'boundary port types');
  if (required) return required;

  const clusterIds = new Set<string>();
  const clusters = sparse.cluster_summaries!.items.map((cluster) => {
    const clusterId = String(cluster.cluster_id);
    if (clusterIds.has(clusterId)) return null;
    clusterIds.add(clusterId);
    return { clusterId, label: `Cluster ${clusterId}`, recipeCount: cluster.recipe_count, recipeIds: [...cluster.recipe_ids].sort(), netInputPortCount: cluster.net_input_port_count, netOutputPortCount: cluster.net_output_port_count, netPortCount: cluster.net_port_count };
  });
  if (clusters.some((cluster) => cluster === null)) return bad('duplicate-cluster-summary', 'Sparse cluster summaries contain duplicate cluster ids; showing raw graph.');
  const validClusters = (clusters as ValidCluster[]).sort((a, b) => a.clusterId.localeCompare(b.clusterId));

  if (sparse.recipe_assignments && !sparse.recipe_assignments.truncated && sparse.recipe_assignments.items.length === sparse.recipe_assignments.total_count) {
    const seenRecipes = new Set<string>();
    const assignedByCluster = new Map<string, string[]>();
    for (const assignment of sparse.recipe_assignments.items) {
    if (seenRecipes.has(assignment.recipe_id)) return bad('duplicate-recipe-assignment', `Recipe ${assignment.recipe_id} has duplicate sparse cluster assignments; showing raw graph.`);
    seenRecipes.add(assignment.recipe_id);
    if (!clusterIds.has(String(assignment.cluster_id))) return bad('unknown-assignment-cluster', `Recipe ${assignment.recipe_id} is assigned to unknown cluster ${String(assignment.cluster_id)}; showing raw graph.`);
    const clusterId = String(assignment.cluster_id);
    assignedByCluster.set(clusterId, [...(assignedByCluster.get(clusterId) ?? []), assignment.recipe_id].sort());
  }
    for (const recipeId of activeRecipeIds) if (!seenRecipes.has(recipeId)) return bad('missing-active-recipe-assignment', `Active recipe ${recipeId} is missing a sparse cluster assignment; showing raw graph.`);
    for (const cluster of validClusters) {
    const assigned = assignedByCluster.get(cluster.clusterId) ?? [];
    if (cluster.recipeCount !== assigned.length || cluster.recipeIds.length !== assigned.length || cluster.recipeIds.some((recipeId, index) => recipeId !== assigned[index])) {
      return bad('cluster-summary-assignment-mismatch', `Sparse cluster summary ${cluster.clusterId} does not match recipe assignments; showing raw graph.`);
    }
    }
  }

  const itemIds = new Set<string>();
  const netPorts: NetPortEdge[] = [];
  for (const port of sparse.boundary_port_types!.items) {
    const clusterId = String(port.cluster_id);
    if (!clusterIds.has(clusterId)) return bad('unknown-boundary-cluster', `Boundary port references unknown cluster ${clusterId}; showing raw graph.`);
    if (port.direction !== 'input' && port.direction !== 'output') return bad('invalid-boundary-direction', `Boundary port for ${port.item_id} has invalid direction; showing raw graph.`);
    const net = port.net_amount;
    if (!Number.isFinite(net) || (port.direction === 'output' && net! <= EPSILON) || (port.direction === 'input' && net! >= -EPSILON)) return bad('invalid-boundary-quantity', `Boundary port for ${port.item_id} has invalid net amount; showing raw graph.`);
    itemIds.add(port.item_id);
    netPorts.push({ clusterId, itemId: port.item_id, direction: port.direction, quantity: Math.abs(net!) });
  }
  return { ok: true, clusters: validClusters, netPorts: netPorts.sort((a, b) => a.itemId.localeCompare(b.itemId) || a.clusterId.localeCompare(b.clusterId) || a.direction.localeCompare(b.direction)), itemIds };
}

function requiredArray(array: SparseCappedArrayDto | null | undefined, label: string): SparseBad | null {
  if (!array) return bad('sparse-required-missing', `Sparse ${label} are missing; showing raw graph.`);
  if (array.truncated) return bad('sparse-required-truncated', `Sparse ${label} were capped; showing raw graph.`);
  if (array.items.length !== array.total_count) return bad('sparse-required-count-mismatch', `Sparse ${label} count does not match returned items; showing raw graph.`);
  return null;
}

function optionalSparseNotices(sparse: SparseClusteringResultDto): VisualGraphNotice[] {
  const notices: VisualGraphNotice[] = [];
  for (const [code, label, array] of [
    ['optional-external-boundary-port-types-capped', 'external boundary annotations', sparse.external_boundary_port_types],
    ['optional-surplus-unmet-summary-capped', 'surplus/unmet annotations', sparse.surplus_unmet_summary],
    ['optional-hub-summaries-capped', 'hub summary annotations', sparse.hub_summaries],
  ] as const) {
    if (array?.truncated) notices.push({ severity: 'info', code, message: `Sparse ${label} were capped and are omitted from visual annotations.` });
  }
  return notices;
}

function activeRecipes(result: SolveResultDto): string[] {
  return Object.entries(result.recipe_rates)
    .filter(([, rate]) => rate > EPSILON)
    .map(([recipeId]) => recipeId)
    .sort();
}

function bad(code: string, message: string): SparseBad { return { ok: false, code, message }; }

function compareVisualNodes(left: VisualGraphNode, right: VisualGraphNode) {
  return left.visualKind.localeCompare(right.visualKind) || ('clusterId' in left ? left.clusterId : '').localeCompare('clusterId' in right ? right.clusterId : '') || left.id.localeCompare(right.id);
}

function compareVisualEdges(left: VisualGraphEdge, right: VisualGraphEdge) {
  return left.visualKind.localeCompare(right.visualKind) || left.source.localeCompare(right.source) || left.target.localeCompare(right.target) || (left.itemId ?? '').localeCompare(right.itemId ?? '') || left.id.localeCompare(right.id);
}
