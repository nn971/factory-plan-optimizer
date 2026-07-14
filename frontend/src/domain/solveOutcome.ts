import type { ExplorerResponseDto, JobStatus, SolveJobDto, SolveResultDto } from '../api/dtos';

export const EPSILON = 1e-9;

export type OutcomeTone = 'neutral' | 'info' | 'success' | 'warning' | 'error';

export type StatusSummary = {
  label: string;
  description: string;
  tone: OutcomeTone;
};

export type ObjectiveComponentInfo = {
  label: string;
  description: string;
};

export const objectiveComponentInfo: Record<string, ObjectiveComponentInfo> = {
  raw_cost: {
    label: 'Raw cost',
    description: 'Cost of externally supplied raw inputs used by the solution.',
  },
  production_cost: {
    label: 'Production cost',
    description: 'Cost assigned to running recipes in the production plan.',
  },
  flow_cost: {
    label: 'Flow cost',
    description: 'Cost assigned to item movement or flow in the model.',
  },
  port_cost: {
    label: 'Port cost',
    description: 'Cost assigned to boundary or port usage in decomposed models.',
  },
  cluster_cost: {
    label: 'Cluster cost',
    description: 'Cost assigned to using grouped production clusters.',
  },
  duplication_cost: {
    label: 'Duplication cost',
    description: 'Penalty for duplicated production across clusters or partitions.',
  },
  unmet_demand_penalty: {
    label: 'Unmet demand penalty',
    description: 'Penalty added when soft diagnostics leave requested demand unmet.',
  },
};

export function describeJobStatus(status: JobStatus): StatusSummary {
  switch (status) {
    case 'queued':
      return { label: 'Queued', description: 'The solve request is waiting to run.', tone: 'info' };
    case 'running':
      return { label: 'Running', description: 'The solver is currently working on this request.', tone: 'info' };
    case 'succeeded':
      return { label: 'Succeeded', description: 'The job finished and returned a solver result.', tone: 'success' };
    case 'failed':
      return { label: 'Failed', description: 'The job failed before returning a usable solver result.', tone: 'error' };
  }
}

export function describeSolverStatus(result: SolveResultDto | null | undefined): StatusSummary {
  if (!result) return { label: 'No solver result', description: 'No nested solver status is available yet.', tone: 'neutral' };
  const normalized = result.solver_status.toLowerCase();
  if (normalized === 'optimal') {
    return { label: result.solver_status, description: 'The solver reported an optimal solution.', tone: 'success' };
  }
  if (normalized.includes('infeasible') || normalized.includes('unbounded') || normalized.includes('error')) {
    return { label: result.solver_status, description: 'The solver reported a non-usable outcome.', tone: 'error' };
  }
  return { label: result.solver_status, description: 'Review diagnostics because this solver outcome is not the usual optimal status.', tone: 'warning' };
}

export function graphAvailability({
  job,
  explorer,
  explorerLoading,
  explorerStale,
  currentPackageId,
}: {
  job: SolveJobDto | null;
  explorer: ExplorerResponseDto | null;
  explorerLoading: boolean;
  explorerStale: boolean;
  currentPackageId?: string | null;
}): StatusSummary {
  if (!job?.result) return { label: 'Flow graph unavailable', description: 'Run a solve before inspecting result flows.', tone: 'neutral' };
  if (explorerLoading) return { label: 'Loading recipe data', description: 'Flow graph can render partial result IDs while explorer recipe data loads.', tone: 'info' };
  if (!explorer) return { label: 'Recipe data not loaded', description: 'Rendering a partial ID-only graph. Load explorer recipe data for full recipe IO topology.', tone: 'info' };
  if (explorerStale) return { label: 'Recipe data stale', description: 'Rendering uses the available explorer topology, but refresh recipe data to update enrichment for this solve result.', tone: 'warning' };
  if (currentPackageId && explorer.package_id && currentPackageId !== explorer.package_id) {
    return { label: 'Recipe data mismatch', description: 'Rendering uses the available explorer topology, but explorer data belongs to a different package.', tone: 'warning' };
  }
  return { label: 'Flow graph ready', description: 'Recipe data is available for this result view. Raw diagnostics remain below for exact inspection.', tone: 'success' };
}
