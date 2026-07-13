import type {
  OptimizedClusteringExternalFlowDto,
  OptimizedClusteringResultDto,
  OptimizedClusteringStatusDto,
  SolveResultDto,
} from '../api/dtos';
import { formatNumber } from './clusterDiagnostics';

export function getOptimizedClustering(result: SolveResultDto): OptimizedClusteringResultDto | null {
  return result.optimized_clustering ?? null;
}

export function describeOptimizedClusteringStatus(status: OptimizedClusteringStatusDto): {
  label: string;
  tone: 'success' | 'warning' | 'error' | 'info';
  description: string;
} {
  switch (status) {
    case 'optimal':
      return { label: 'Optimal', tone: 'success', description: 'The cluster allocation reached an optimal solution.' };
    case 'feasible_non_optimal':
      return { label: 'Feasible, not optimal', tone: 'warning', description: 'A usable allocation was found, but the solver stopped before proving it optimal.' };
    case 'timeout_no_incumbent':
      return { label: 'Timed out', tone: 'warning', description: 'The clustering pass timed out before finding a usable allocation.' };
    case 'infeasible':
      return { label: 'Infeasible', tone: 'error', description: 'The clustering model could not satisfy its constraints for this solved plan.' };
    case 'solver_unavailable':
      return { label: 'Solver unavailable', tone: 'error', description: 'The backend could not run the clustering solver.' };
    case 'model_too_large':
      return { label: 'Model too large', tone: 'warning', description: 'The plan is too large for the current clustering model guardrail.' };
    case 'no_active_recipes':
      return { label: 'No active recipes', tone: 'info', description: 'The main solve did not produce active recipes to cluster.' };
    case 'disabled':
      return { label: 'Disabled', tone: 'info', description: 'Optimized clustering was explicitly disabled for this solve.' };
  }
}

export function hasOptimizedClusterCostAlias(result: OptimizedClusteringResultDto): boolean {
  return 'cluster_cost' in result.objective_components || 'cluster_cost' in result.cost_breakdown;
}

export function externalBoundaryLabel(row: OptimizedClusteringExternalFlowDto): string {
  if (row.boundary_label === 'aggregate_external_balance') return 'aggregate external balance';
  return row.boundary_label.replace(/_/g, ' ');
}

export function componentLabel(name: string): string {
  if (name === 'cluster_size_penalty') return 'cluster size penalty';
  return name.replace(/_/g, ' ');
}

export function formatMaybeNumber(value: number | null): string {
  return value == null ? 'n/a' : formatNumber(value);
}
