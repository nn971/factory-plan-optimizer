import type {
  SolveResultDto,
  SparseCappedArrayDto,
  SparseClusteringResultDto,
  SparseClusteringStatusDto,
} from '../api/dtos';

export type SparseStatusSummary = {
  label: string;
  tone: 'success' | 'warning' | 'error' | 'info';
  description: string;
};

export function getSparseClustering(result: SolveResultDto): SparseClusteringResultDto | null {
  return result.sparse_clustering ?? null;
}

export function describeSparseClusteringStatus(status: SparseClusteringStatusDto): SparseStatusSummary {
  switch (status) {
    case 'success':
      return { label: 'Ready', tone: 'success', description: 'Sparse clustering finished and can be used to explain the solved plan.' };
    case 'skipped':
      return { label: 'Skipped', tone: 'info', description: 'Sparse clustering did not run for this solve.' };
    case 'model_too_large':
      return { label: 'Model too large', tone: 'warning', description: 'The solved graph exceeded the current sparse clustering guardrail.' };
    case 'timeout':
      return { label: 'Timed out', tone: 'warning', description: 'Sparse clustering stopped before it could complete.' };
    case 'failed':
      return { label: 'Failed', tone: 'error', description: 'Sparse clustering failed, but the main solve result is still available.' };
  }
}

export function cappedArraySummary<T extends Record<string, unknown>>(
  capped: SparseCappedArrayDto<T> | null | undefined,
  label: string,
): string {
  if (!capped) return `No ${label}.`;
  const shown = capped.items.length;
  if (capped.truncated) return `Showing ${shown} of ${capped.total_count} ${label}.`;
  return `Showing all ${capped.total_count} ${label}.`;
}

export function truncatedCappedArrayLabels(result: SparseClusteringResultDto): string[] {
  return cappedArrayEntries(result)
    .filter(([, capped]) => capped?.truncated)
    .map(([name]) => componentLabel(name));
}

export function sparseWarnings(result: SparseClusteringResultDto): string[] {
  const truncations = truncatedCappedArrayLabels(result).map((label) => `${label} are capped in the detail view.`);
  return [...result.warnings, ...truncations];
}

export function componentLabel(name: string): string {
  const special: Record<string, string> = {
    active_recipe_count: 'active recipes',
    active_item_count: 'active items',
    boundary_flow_amount: 'flow estimate',
    boundary_port_types: 'net ports',
    boundary_port_type_count: 'net ports',
    candidate_edge_count: 'candidate edges',
    candidate_estimated_flow: 'candidate estimated flow',
    cluster_summaries: 'cluster summaries',
    edge_count: 'kept graph edges',
    external_boundary_port_type_count: 'external diagnostic rows',
    flow_cost: 'flow cost (absolute net)',
    hub_item_top_k: 'hub item top-k',
    hub_summaries: 'hub summaries',
    max_runtime_seconds: 'max runtime seconds',
    max_refinement_passes: 'max refinement passes',
    min_recipe_rate: 'minimum recipe rate',
    net_input_port_count: 'net input ports',
    net_output_port_count: 'net output ports',
    net_port_count: 'net ports',
    port_aware_objective: 'port-aware objective',
    port_cost: 'port cost',
    port_cost_weight: 'port cost weight',
    port_epsilon: 'port epsilon',
    refinement_passes: 'refinement passes',
    recipe_assignments: 'recipe assignments',
    result_caps: 'result caps',
    skipped_hub_edge_count: 'skipped hub edges',
    size_imbalance: 'size imbalance',
    size_penalty: 'size penalty',
    size_penalty_weight: 'size penalty weight',
    surplus_unmet: 'surplus and unmet rows',
  };
  return special[name] ?? name.replace(/_/g, ' ');
}

export function clusterLabel(clusterId: number | string | null | undefined): string {
  if (clusterId == null || clusterId === '') return 'unknown cluster';
  return `cluster ${String(clusterId)}`;
}

export function displayId(value: unknown): string {
  if (typeof value === 'string' && value.trim()) return value;
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return 'unknown';
}

export function formatSparseValue(value: unknown): string {
  if (typeof value === 'number') return formatNumber(value);
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.length ? value.map(displayId).join(', ') : 'none';
  if (value && typeof value === 'object') return JSON.stringify(value);
  return 'n/a';
}

export function skippedHubEdgeCount(result: SparseClusteringResultDto): number {
  const fromStats = result.graph_statistics?.skipped_hub_edge_count;
  if (typeof fromStats === 'number') return fromStats;
  return result.hub_summaries?.items.reduce((total, row) => total + row.skipped_count, 0) ?? 0;
}

function cappedArrayEntries(result: SparseClusteringResultDto): Array<[string, SparseCappedArrayDto<Record<string, unknown>> | null | undefined]> {
  return [
    ['cluster_summaries', result.cluster_summaries],
    ['recipe_assignments', result.recipe_assignments],
    ['boundary_flows', result.boundary_flows],
    ['boundary_port_types', result.boundary_port_types],
    ['external_boundary_port_types', result.external_boundary_port_types],
    ['surplus_unmet', result.surplus_unmet_summary],
    ['hub_summaries', result.hub_summaries],
  ];
}

function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  if (Math.abs(value) >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (Number.isInteger(value)) return String(value);
  return value.toLocaleString(undefined, { maximumSignificantDigits: 6 });
}
