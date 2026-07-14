import type { ExplorerRecipeDto, ExplorerResponseDto, SolveResultDto } from '../api/dtos';
import { EPSILON } from './solveOutcome';

export type FlowNodeKind = 'item' | 'recipe' | 'diagnostic';
export type DiagnosticKind = 'external' | 'unmet' | 'surplus' | 'missing-recipe';
export type FlowEdgeKind = 'recipe-input' | 'recipe-output' | 'external-supply' | 'unmet-demand' | 'surplus';
export type FlowWarningKind =
  | 'negative-recipe-rate'
  | 'negative-diagnostic-value'
  | 'missing-recipe-metadata'
  | 'negative-recipe-io-amount'
  | 'recipe-topology-unavailable';

export type FlowNode = {
  id: string;
  kind: FlowNodeKind;
  label: string;
  itemId?: string;
  recipeId?: string;
  diagnosticKind?: DiagnosticKind;
  quantity?: number;
};

export type FlowEdge = {
  id: string;
  source: string;
  target: string;
  kind: FlowEdgeKind;
  quantity: number;
  itemId?: string;
  recipeId?: string;
};

export type FlowDiagnostic = {
  id: string;
  kind: DiagnosticKind;
  message: string;
  itemId?: string;
  recipeId?: string;
  quantity?: number;
};

export type FlowWarning = {
  kind: FlowWarningKind;
  message: string;
  itemId?: string;
  recipeId?: string;
  field?: string;
  value?: number;
};

export type ActiveFlowGraph = {
  nodes: FlowNode[];
  edges: FlowEdge[];
  diagnostics: FlowDiagnostic[];
  warnings: FlowWarning[];
};

export type FlowCluster = {
  id: string;
  label: string;
  nodeIds: string[];
  edgeIds: string[];
  nodeCount: number;
  edgeCount: number;
  unmetDemandCount: number;
  unmetDemandQuantity: number;
  surplusCount: number;
  surplusQuantity: number;
  warningCount: number;
  missingRecipeCount: number;
};

export type DisplayFlowNode = FlowNode | {
  id: string;
  kind: 'cluster';
  label: string;
  cluster: FlowCluster;
};

export type DisplayFlowEdge = FlowEdge & { collapsed?: boolean };

export type DisplayFlowGraph = {
  nodes: DisplayFlowNode[];
  edges: DisplayFlowEdge[];
  clusters: FlowCluster[];
};

export type FlowGraphMode = 'raw' | 'heuristic' | 'optimizer-overlay';

export type OptimizerOverlaySource = 'sparse';

export type OptimizerOverlay =
  | {
      available: true;
      source: OptimizerOverlaySource;
      label: string;
      recipeToCluster: Map<string, string>;
    }
  | {
      available: false;
      reason: string;
    };

export type FlowDetailRow = {
  label: string;
  id?: string;
  quantity?: number;
};

export type FlowSelectionDetails = {
  id: string;
  kind: FlowNodeKind | 'cluster';
  label: string;
  summary: string;
  rows: FlowDetailRow[];
};

export type FlowSelectionDetailIndex = {
  detailById: Map<string, FlowSelectionDetails>;
};

const MIN_CLUSTER_NODE_COUNT = 7;
const MIN_GRAPH_NODE_COUNT_FOR_CLUSTERING = 13;

export function buildActiveFlowGraph(result: SolveResultDto, explorer: ExplorerResponseDto | null): ActiveFlowGraph {
  if (!explorer) return buildPartialIdOnlyFlowGraph(result);

  const recipes = new Map(explorer.recipes.map((recipe) => [recipe.id, recipe]));
  const nodes = new Map<string, FlowNode>();
  const edges = new Map<string, FlowEdge>();
  const diagnostics = new Map<string, FlowDiagnostic>();
  const warnings: FlowWarning[] = [];

  for (const [recipeId, rate] of Object.entries(result.recipe_rates)) {
    if (rate < -EPSILON) {
      warnings.push({
        kind: 'negative-recipe-rate',
        recipeId,
        value: rate,
        message: `Recipe ${recipeId} has an unexpected negative rate ${rate}.`,
      });
    }
    if (rate <= EPSILON) continue;

    const recipe = recipes.get(recipeId);
    if (!recipe) {
      const id = missingRecipeDiagnosticId(recipeId);
      nodes.set(id, {
        id,
        kind: 'diagnostic',
        diagnosticKind: 'missing-recipe',
        recipeId,
        label: `Missing recipe metadata: ${recipeId}`,
      });
      diagnostics.set(id, {
        id,
        kind: 'missing-recipe',
        recipeId,
        message: `Active recipe ${recipeId} is missing from explorer recipe metadata.`,
      });
      warnings.push({
        kind: 'missing-recipe-metadata',
        recipeId,
        value: rate,
        message: `Active recipe ${recipeId} is missing from explorer recipe metadata.`,
      });
      continue;
    }

    addRecipeNode(nodes, recipeId);
    addRecipeEdges(nodes, edges, recipe, rate, warnings);
  }

  addDiagnosticMap(nodes, edges, diagnostics, warnings, result.external_supplies, 'external_supplies', 'external');
  addDiagnosticMap(nodes, edges, diagnostics, warnings, result.unmet_demand, 'unmet_demand', 'unmet');
  addDiagnosticMap(nodes, edges, diagnostics, warnings, result.surplus, 'surplus', 'surplus');

  return {
    nodes: [...nodes.values()].sort(byId),
    edges: [...edges.values()].sort(byIdThenEndpoints),
    diagnostics: [...diagnostics.values()].sort(byId),
    warnings: warnings.sort(byWarning),
  };
}

function buildPartialIdOnlyFlowGraph(result: SolveResultDto): ActiveFlowGraph {
  const nodes = new Map<string, FlowNode>();
  const edges = new Map<string, FlowEdge>();
  const diagnostics = new Map<string, FlowDiagnostic>();
  const warnings: FlowWarning[] = [
    {
      kind: 'recipe-topology-unavailable',
      message: 'Full recipe IO topology is unavailable without explorer recipe metadata. Showing active recipe and diagnostic IDs only.',
    },
  ];

  for (const [recipeId, rate] of Object.entries(result.recipe_rates)) {
    if (rate < -EPSILON) {
      warnings.push({
        kind: 'negative-recipe-rate',
        recipeId,
        value: rate,
        message: `Recipe ${recipeId} has an unexpected negative rate ${rate}.`,
      });
    }
    if (rate > EPSILON) addRecipeNode(nodes, recipeId);
  }

  addDiagnosticMap(nodes, edges, diagnostics, warnings, result.external_supplies, 'external_supplies', 'external');
  addDiagnosticMap(nodes, edges, diagnostics, warnings, result.unmet_demand, 'unmet_demand', 'unmet');
  addDiagnosticMap(nodes, edges, diagnostics, warnings, result.surplus, 'surplus', 'surplus');

  return {
    nodes: [...nodes.values()].sort(byId),
    edges: [...edges.values()].sort(byIdThenEndpoints),
    diagnostics: [...diagnostics.values()].sort(byId),
    warnings: warnings.sort(byWarning),
  };
}

export function buildDisplayFlowGraph(
  graph: ActiveFlowGraph,
  expandedClusterIds: ReadonlySet<string>,
  mode: Exclude<FlowGraphMode, 'optimizer-overlay'> = 'raw',
): DisplayFlowGraph {
  if (mode === 'raw') return { nodes: graph.nodes, edges: graph.edges, clusters: [] };

  const clusters = buildFlowClusters(graph);
  if (clusters.length === 0) return { nodes: graph.nodes, edges: graph.edges, clusters };

  const clusterByNode = new Map<string, FlowCluster>();
  for (const cluster of clusters) {
    for (const nodeId of cluster.nodeIds) clusterByNode.set(nodeId, cluster);
  }

  const visibleNodes = new Map<string, DisplayFlowNode>();
  for (const node of graph.nodes) {
    const cluster = clusterByNode.get(node.id);
    if (!cluster || expandedClusterIds.has(cluster.id)) {
      visibleNodes.set(node.id, node);
    } else {
      visibleNodes.set(cluster.id, { id: cluster.id, kind: 'cluster', label: cluster.label, cluster });
    }
  }

  const visibleEdges = new Map<string, DisplayFlowEdge>();
  for (const edge of graph.edges) {
    const sourceCluster = clusterByNode.get(edge.source);
    const targetCluster = clusterByNode.get(edge.target);
    const sourceCollapsed = sourceCluster && !expandedClusterIds.has(sourceCluster.id);
    const targetCollapsed = targetCluster && !expandedClusterIds.has(targetCluster.id);
    const source = sourceCollapsed ? sourceCluster.id : edge.source;
    const target = targetCollapsed ? targetCluster.id : edge.target;
    if (source === target) continue;
    visibleEdges.set(`${edge.id}:${source}:${target}`, { ...edge, id: `${edge.id}:${source}:${target}`, source, target, collapsed: Boolean(sourceCollapsed || targetCollapsed) });
  }

  return {
    nodes: [...visibleNodes.values()].sort(byId),
    edges: [...visibleEdges.values()].sort(byIdThenEndpoints),
    clusters,
  };
}

export function buildOptimizerOverlay(graph: ActiveFlowGraph, result: SolveResultDto): OptimizerOverlay {
  const activeRecipeIds = graph.nodes
    .filter((node) => node.kind === 'recipe' && node.recipeId)
    .map((node) => node.recipeId as string)
    .sort();
  if (activeRecipeIds.length === 0) {
    return { available: false, reason: 'No active recipe nodes are available for cluster overlay.' };
  }

  const sparse = sparseOverlay(result, activeRecipeIds);
  if (sparse.available || result.sparse_clustering?.status === 'success') return sparse;
  return { available: false, reason: 'Sparse cluster assignments are not available for this solve.' };
}

function sparseOverlay(result: SolveResultDto, activeRecipeIds: string[]): OptimizerOverlay {
  const sparse = result.sparse_clustering;
  if (sparse?.status !== 'success') return { available: false, reason: 'Sparse cluster assignments are not available for this solve.' };
  const assignments = sparse.recipe_assignments;
  if (!assignments) return { available: false, reason: 'Sparse cluster assignments are missing, so cluster overlay is unavailable.' };
  if (assignments.truncated) return { available: false, reason: 'Sparse cluster assignments were capped, so cluster overlay is unavailable.' };

  const clusterByRecipe = new Map<string, Set<string>>();
  for (const assignment of assignments.items) {
    const set = clusterByRecipe.get(assignment.recipe_id) ?? new Set<string>();
    set.add(String(assignment.cluster_id));
    clusterByRecipe.set(assignment.recipe_id, set);
  }

  const recipeToCluster = new Map<string, string>();
  for (const recipeId of activeRecipeIds) {
    const clusters = clusterByRecipe.get(recipeId);
    if (!clusters || clusters.size === 0) {
      return { available: false, reason: 'Sparse cluster assignments do not cover every active recipe node.' };
    }
    if (clusters.size > 1) {
      return { available: false, reason: 'Sparse cluster assignments are ambiguous for at least one active recipe.' };
    }
    recipeToCluster.set(recipeId, [...clusters][0]);
  }

  return { available: true, source: 'sparse', label: 'Sparse clustering', recipeToCluster };
}

export function buildFlowClusters(graph: ActiveFlowGraph): FlowCluster[] {
  if (graph.nodes.length < MIN_GRAPH_NODE_COUNT_FOR_CLUSTERING) return [];
  const adjacency = new Map(graph.nodes.map((node) => [node.id, new Set<string>()]));
  for (const edge of graph.edges) {
    adjacency.get(edge.source)?.add(edge.target);
    adjacency.get(edge.target)?.add(edge.source);
  }
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  const warningNodeIds = new Set(graph.warnings.flatMap((warning) => [warning.itemId ? itemNodeId(warning.itemId) : '', warning.recipeId ? recipeNodeId(warning.recipeId) : '']).filter(Boolean));
  const visited = new Set<string>();
  const clusters: FlowCluster[] = [];
  for (const start of [...adjacency.keys()].sort()) {
    if (visited.has(start)) continue;
    const component = collectComponent(start, adjacency, visited);
    if (component.length < MIN_CLUSTER_NODE_COUNT) continue;
    const componentSet = new Set(component);
    const containedEdges = graph.edges.filter((edge) => componentSet.has(edge.source) && componentSet.has(edge.target)).map((edge) => edge.id).sort();
    const diagnostics = component.map((id) => nodeById.get(id)).filter((node): node is FlowNode => Boolean(node?.kind === 'diagnostic'));
    const id = `cluster:${clusters.length + 1}:${component[0]}`;
    clusters.push({
      id,
      label: `Cluster ${clusters.length + 1}`,
      nodeIds: component,
      edgeIds: containedEdges,
      nodeCount: component.length,
      edgeCount: containedEdges.length,
      unmetDemandCount: diagnostics.filter((node) => node.diagnosticKind === 'unmet').length,
      unmetDemandQuantity: sumDiagnosticQuantity(diagnostics, 'unmet'),
      surplusCount: diagnostics.filter((node) => node.diagnosticKind === 'surplus').length,
      surplusQuantity: sumDiagnosticQuantity(diagnostics, 'surplus'),
      warningCount: component.filter((id) => warningNodeIds.has(id)).length,
      missingRecipeCount: diagnostics.filter((node) => node.diagnosticKind === 'missing-recipe').length,
    });
  }
  return clusters.sort(byId);
}

export function buildFlowSelectionDetails(
  graph: ActiveFlowGraph,
  selectedId: string | null,
  result?: SolveResultDto,
): FlowSelectionDetails | null {
  if (!selectedId) return null;
  return buildFlowSelectionDetailIndex(graph, result).detailById.get(selectedId) ?? null;
}

export function buildFlowSelectionDetailIndex(
  graph: ActiveFlowGraph,
  result?: SolveResultDto,
  clusters: FlowCluster[] = buildFlowClusters(graph),
): FlowSelectionDetailIndex {
  const detailById = new Map<string, FlowSelectionDetails>();
  const diagnosticsById = new Map(graph.diagnostics.map((diagnostic) => [diagnostic.id, diagnostic]));
  const edgesByNode = new Map<string, FlowEdge[]>();
  for (const edge of graph.edges) {
    appendEdge(edgesByNode, edge.source, edge);
    appendEdge(edgesByNode, edge.target, edge);
  }

  for (const cluster of clusters) detailById.set(cluster.id, clusterDetails(cluster));
  for (const node of graph.nodes) {
    detailById.set(node.id, nodeDetails(node, edgesByNode.get(node.id) ?? [], diagnosticsById, result));
  }
  return { detailById };
}

function clusterDetails(cluster: FlowCluster): FlowSelectionDetails {
  return {
    id: cluster.id,
    kind: 'cluster',
    label: cluster.label,
    summary: `${cluster.nodeCount} nodes and ${cluster.edgeCount} internal edges.`,
    rows: [
      { label: 'Contained nodes', quantity: cluster.nodeCount },
      { label: 'Contained edges', quantity: cluster.edgeCount },
      { label: 'Unmet demand diagnostics', quantity: cluster.unmetDemandCount },
      { label: 'Unmet demand quantity', quantity: cluster.unmetDemandQuantity },
      { label: 'Surplus diagnostics', quantity: cluster.surplusCount },
      { label: 'Surplus quantity', quantity: cluster.surplusQuantity },
      { label: 'Warnings touching cluster nodes', quantity: cluster.warningCount },
      { label: 'Missing recipe diagnostics', quantity: cluster.missingRecipeCount },
    ],
  };
}

function nodeDetails(
  node: FlowNode,
  connectedEdges: FlowEdge[],
  diagnosticsById: Map<string, FlowDiagnostic>,
  result?: SolveResultDto,
): FlowSelectionDetails {
  if (node.kind === 'item') {
    return {
      id: node.id,
      kind: node.kind,
      label: node.label,
      summary: `Item ${node.itemId ?? node.id} has ${connectedEdges.length} connected flow edges.`,
      rows: connectedEdges.map((edge) => ({
        label: edge.target === node.id ? `Incoming ${edge.kind}` : `Outgoing ${edge.kind}`,
        id: edge.id,
        quantity: edge.quantity,
      })),
    };
  }
  if (node.kind === 'recipe') {
    const recipeId = node.recipeId ?? node.id.replace(/^recipe:/, '');
    return {
      id: node.id,
      kind: node.kind,
      label: node.label,
      summary: `Solved recipe rate ${result?.recipe_rates[recipeId] ?? 'unknown'}.`,
      rows: [
        { label: 'Recipe rate', id: recipeId, quantity: result?.recipe_rates[recipeId] },
        ...connectedEdges.map((edge) => ({ label: edge.kind, id: edge.itemId, quantity: edge.quantity })),
      ],
    };
  }
  const diagnostic = diagnosticsById.get(node.id);
  return {
    id: node.id,
    kind: node.kind,
    label: node.label,
    summary: diagnostic?.message ?? `Diagnostic ${node.diagnosticKind ?? 'unknown'}.`,
    rows: [
      { label: 'Diagnostic type', id: node.diagnosticKind },
      { label: 'Item', id: node.itemId },
      { label: 'Recipe', id: node.recipeId },
      { label: 'Quantity', quantity: node.quantity },
      ...connectedEdges.map((edge) => ({ label: `Connected ${edge.kind}`, id: edge.id, quantity: edge.quantity })),
    ].filter((row) => row.id !== undefined || row.quantity !== undefined),
  };
}

function appendEdge(edgesByNode: Map<string, FlowEdge[]>, nodeId: string, edge: FlowEdge) {
  const edges = edgesByNode.get(nodeId) ?? [];
  edges.push(edge);
  edgesByNode.set(nodeId, edges);
}

function collectComponent(start: string, adjacency: Map<string, Set<string>>, visited: Set<string>): string[] {
  const component: string[] = [];
  const queue = [start];
  visited.add(start);
  while (queue.length > 0) {
    const current = queue.shift();
    if (!current) continue;
    component.push(current);
    for (const next of [...(adjacency.get(current) ?? [])].sort()) {
      if (visited.has(next)) continue;
      visited.add(next);
      queue.push(next);
    }
  }
  return component.sort();
}

function sumDiagnosticQuantity(nodes: FlowNode[], kind: DiagnosticKind) {
  return nodes
    .filter((node) => node.diagnosticKind === kind)
    .reduce((total, node) => total + (node.quantity ?? 0), 0);
}

function addRecipeEdges(
  nodes: Map<string, FlowNode>,
  edges: Map<string, FlowEdge>,
  recipe: ExplorerRecipeDto,
  rate: number,
  warnings: FlowWarning[],
) {
  for (const input of recipe.inputs) {
    if (input.amount < -EPSILON) {
      warnings.push({
        kind: 'negative-recipe-io-amount',
        recipeId: recipe.id,
        itemId: input.item_id,
        field: 'inputs',
        value: input.amount,
        message: `Recipe ${recipe.id} input ${input.item_id} has an unexpected negative amount ${input.amount}.`,
      });
    }
    const quantity = rate * input.amount;
    if (quantity <= EPSILON) continue;
    addItemNode(nodes, input.item_id);
    const edge: FlowEdge = {
      id: `edge:input:${input.item_id}:${recipe.id}`,
      source: itemNodeId(input.item_id),
      target: recipeNodeId(recipe.id),
      kind: 'recipe-input',
      quantity,
      itemId: input.item_id,
      recipeId: recipe.id,
    };
    edges.set(edge.id, edge);
  }
  for (const output of recipe.outputs) {
    if (output.amount < -EPSILON) {
      warnings.push({
        kind: 'negative-recipe-io-amount',
        recipeId: recipe.id,
        itemId: output.item_id,
        field: 'outputs',
        value: output.amount,
        message: `Recipe ${recipe.id} output ${output.item_id} has an unexpected negative amount ${output.amount}.`,
      });
    }
    const quantity = rate * output.amount;
    if (quantity <= EPSILON) continue;
    addItemNode(nodes, output.item_id);
    const edge: FlowEdge = {
      id: `edge:output:${recipe.id}:${output.item_id}`,
      source: recipeNodeId(recipe.id),
      target: itemNodeId(output.item_id),
      kind: 'recipe-output',
      quantity,
      itemId: output.item_id,
      recipeId: recipe.id,
    };
    edges.set(edge.id, edge);
  }
}

function addDiagnosticMap(
  nodes: Map<string, FlowNode>,
  edges: Map<string, FlowEdge>,
  diagnostics: Map<string, FlowDiagnostic>,
  warnings: FlowWarning[],
  values: Record<string, number>,
  field: string,
  kind: Exclude<DiagnosticKind, 'missing-recipe'>,
) {
  for (const [itemId, value] of Object.entries(values)) {
    if (value < -EPSILON) {
      warnings.push({
        kind: 'negative-diagnostic-value',
        itemId,
        field,
        value,
        message: `${field}.${itemId} has an unexpected negative value ${value}.`,
      });
    }
    if (value <= EPSILON) continue;
    addItemNode(nodes, itemId);
    const diagnosticId = diagnosticNodeId(kind, itemId);
    nodes.set(diagnosticId, {
      id: diagnosticId,
      kind: 'diagnostic',
      diagnosticKind: kind,
      itemId,
      quantity: value,
      label: diagnosticLabel(kind, itemId),
    });
    diagnostics.set(diagnosticId, {
      id: diagnosticId,
      kind,
      itemId,
      quantity: value,
      message: diagnosticMessage(kind, itemId, value),
    });
    const edge = diagnosticEdge(kind, itemId, value);
    edges.set(edge.id, edge);
  }
}

function diagnosticEdge(kind: Exclude<DiagnosticKind, 'missing-recipe'>, itemId: string, quantity: number): FlowEdge {
  const diagnosticId = diagnosticNodeId(kind, itemId);
  const itemIdNode = itemNodeId(itemId);
  if (kind === 'external') {
    return { id: `edge:external:${itemId}`, source: diagnosticId, target: itemIdNode, kind: 'external-supply', itemId, quantity };
  }
  if (kind === 'unmet') {
    return { id: `edge:unmet:${itemId}`, source: itemIdNode, target: diagnosticId, kind: 'unmet-demand', itemId, quantity };
  }
  return { id: `edge:surplus:${itemId}`, source: itemIdNode, target: diagnosticId, kind: 'surplus', itemId, quantity };
}

function addItemNode(nodes: Map<string, FlowNode>, itemId: string) {
  const id = itemNodeId(itemId);
  if (!nodes.has(id)) nodes.set(id, { id, kind: 'item', itemId, label: itemId });
}

function addRecipeNode(nodes: Map<string, FlowNode>, recipeId: string) {
  const id = recipeNodeId(recipeId);
  if (!nodes.has(id)) nodes.set(id, { id, kind: 'recipe', recipeId, label: recipeId });
}

function itemNodeId(itemId: string) {
  return `item:${itemId}`;
}

function recipeNodeId(recipeId: string) {
  return `recipe:${recipeId}`;
}

function diagnosticNodeId(kind: Exclude<DiagnosticKind, 'missing-recipe'>, itemId: string) {
  return `diagnostic:${kind}:${itemId}`;
}

function missingRecipeDiagnosticId(recipeId: string) {
  return `diagnostic:missing-recipe:${recipeId}`;
}

function diagnosticLabel(kind: Exclude<DiagnosticKind, 'missing-recipe'>, itemId: string) {
  if (kind === 'external') return `External supply: ${itemId}`;
  if (kind === 'unmet') return `Unmet demand: ${itemId}`;
  return `Surplus: ${itemId}`;
}

function diagnosticMessage(kind: Exclude<DiagnosticKind, 'missing-recipe'>, itemId: string, quantity: number) {
  if (kind === 'external') return `${quantity} ${itemId} supplied externally.`;
  if (kind === 'unmet') return `${quantity} ${itemId} demand was not met.`;
  return `${quantity} ${itemId} produced as surplus.`;
}

function byId<T extends { id: string }>(left: T, right: T) {
  return left.id.localeCompare(right.id);
}

function byIdThenEndpoints(left: FlowEdge, right: FlowEdge) {
  return left.id.localeCompare(right.id) || left.source.localeCompare(right.source) || left.target.localeCompare(right.target);
}

function byWarning(left: FlowWarning, right: FlowWarning) {
  return (
    left.kind.localeCompare(right.kind) ||
    (left.recipeId ?? '').localeCompare(right.recipeId ?? '') ||
    (left.itemId ?? '').localeCompare(right.itemId ?? '') ||
    (left.field ?? '').localeCompare(right.field ?? '')
  );
}
