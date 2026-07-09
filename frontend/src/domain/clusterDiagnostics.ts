import type { ClusterBoundaryItemDto, ClusterDiagnosticsDto, ClusterDto, SolveResultDto } from '../api/dtos';

export type ClusterDiagnosticsSummary = {
  diagnostics: ClusterDiagnosticsDto;
  clusterCount: number;
  boundaryItemRowCount: number;
  zeroNetRowCount: number;
  activeRecipeCount: number;
  boundaryItemTypeCount: number;
};

export function getClusterDiagnostics(result: SolveResultDto): ClusterDiagnosticsDto | null {
  return result.cluster_diagnostics ?? null;
}

export function summarizeClusterDiagnostics(result: SolveResultDto): ClusterDiagnosticsSummary | null {
  const diagnostics = getClusterDiagnostics(result);
  if (!diagnostics) return null;
  const clusters = diagnostics.clusters;
  const boundaryItems = clusters.flatMap((cluster) => cluster.boundary_items);
  return {
    diagnostics,
    clusterCount: clusters.length,
    boundaryItemRowCount: boundaryItems.length,
    zeroNetRowCount: boundaryItems.filter((item) => item.is_zero_net).length,
    activeRecipeCount: clusters.reduce((total, cluster) => total + cluster.active_recipe_count, 0),
    boundaryItemTypeCount: clusters.reduce((total, cluster) => total + cluster.boundary_item_type_count, 0),
  };
}

export function sortedDiagnosticClusters(diagnostics: ClusterDiagnosticsDto): ClusterDto[] {
  return [...diagnostics.clusters].sort(
    (left, right) =>
      diagnosticCost(right) - diagnosticCost(left) ||
      right.boundary_item_type_count - left.boundary_item_type_count ||
      left.label.localeCompare(right.label) ||
      left.id.localeCompare(right.id),
  );
}

export function sortedBoundaryItems(cluster: ClusterDto): ClusterBoundaryItemDto[] {
  return [...cluster.boundary_items].sort(
    (left, right) =>
      Number(left.is_zero_net) - Number(right.is_zero_net) ||
      left.direction.localeCompare(right.direction) ||
      Math.abs(right.quantity) - Math.abs(left.quantity) ||
      left.item_id.localeCompare(right.item_id),
  );
}

export function diagnosticCost(cluster: ClusterDto): number {
  return Object.values(cluster.diagnostic_components).reduce((total, value) => total + value, 0);
}

export function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  if (Math.abs(value) >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (Number.isInteger(value)) return String(value);
  return value.toLocaleString(undefined, { maximumSignificantDigits: 6 });
}
