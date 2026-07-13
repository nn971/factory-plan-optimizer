import type { ExternalInputDto, MaxClusterSizeConstraintDto, OptimizedClusteringPresetDto, ProblemDto, SolveModeDto, SolveRequestDto } from '../api/dtos';

export type DisplayRateUnits = 'items_per_second' | 'items_per_minute';

export type EditableExternalInput = {
  item_id: string;
  kind: ExternalInputDto['kind'];
  enabled: boolean;
  cost: string;
  capacity: string;
  source?: ExternalInputDto['source'];
  defaultApproved: boolean;
};

export type EditableProblem = {
  solveMode: SolveModeDto;
  displayRateUnits: DisplayRateUnits;
  demands: Record<string, string>;
  externalInputs: EditableExternalInput[];
  optimizedClustering: EditableOptimizedClustering;
};

export type EditableOptimizedClustering = {
  enabled: boolean;
  allowRecipeSplitting: boolean;
  splittableRecipeIds: string;
  preset: OptimizedClusteringPresetDto;
  reportingEpsilon: string;
  timeLimitSeconds: string;
  flowCostPerQuantity: string;
  portCostPerItemType: string;
  clusterSizePenaltyWeight: string;
  minClusterSize: string;
  maxClusterSize: string;
  maxClusterSizeConstraint: MaxClusterSizeConstraintDto;
};

export const DEFAULT_OPTIMIZED_CLUSTERING: EditableOptimizedClustering = {
  enabled: false,
  allowRecipeSplitting: false,
  splittableRecipeIds: '',
  preset: 'balanced',
  reportingEpsilon: '0.000001',
  timeLimitSeconds: '60',
  flowCostPerQuantity: '1',
  portCostPerItemType: '100',
  clusterSizePenaltyWeight: '10',
  minClusterSize: '5',
  maxClusterSize: '15',
  maxClusterSizeConstraint: 'soft',
};

export function createEditableProblem(problem: ProblemDto): EditableProblem {
  const targetDemandIds = problem.target_demands ?? [];
  const rawInputCandidates = problem.raw_input_candidates ?? [];
  const externalInputs = rawInputCandidates.length > 0
    ? rawInputCandidates
    : problem.external_inputs ?? [];
  return {
    solveMode: problem.default_solve_mode,
    displayRateUnits: normalizeDisplayRateUnits(problem.rate_units),
    demands: Object.fromEntries(
      targetDemandIds.map((itemId) => [itemId, '']),
    ),
    externalInputs: externalInputs.map((input) => ({
      item_id: input.item_id,
      kind: input.kind ?? 'unknown',
      enabled: input.enabled,
      cost: String(input.cost),
      capacity: input.capacity == null ? '' : String(input.capacity),
      source: input.source,
      defaultApproved: input.default_approved ?? false,
    })),
    optimizedClustering: { ...DEFAULT_OPTIMIZED_CLUSTERING },
  };
}

export function toSolveRequest(
  editable: EditableProblem,
  packageId?: string | null,
  selectedMilestone?: string | null,
): SolveRequestDto {
  const trimmedMilestone = selectedMilestone?.trim();
  const optimizedClustering = editable.optimizedClustering.enabled
    ? {
        enabled: true,
        mode: 'continuous_split' as const,
        preset: editable.optimizedClustering.preset,
        flow_cost_per_quantity: parseNonnegativeNumber(editable.optimizedClustering.flowCostPerQuantity),
        port_cost_per_item_type: parseNonnegativeNumber(editable.optimizedClustering.portCostPerItemType),
        cluster_size_penalty_weight: parseNonnegativeNumber(editable.optimizedClustering.clusterSizePenaltyWeight),
        min_cluster_size: parseNonnegativeNumber(editable.optimizedClustering.minClusterSize),
        max_cluster_size: parsePositiveNumber(editable.optimizedClustering.maxClusterSize),
        max_cluster_size_constraint: editable.optimizedClustering.maxClusterSizeConstraint,
        reporting_epsilon: parsePositiveNumber(editable.optimizedClustering.reportingEpsilon),
        time_limit_seconds: parsePositiveNumber(editable.optimizedClustering.timeLimitSeconds),
        allow_recipe_splitting: editable.optimizedClustering.allowRecipeSplitting,
        splittable_recipe_ids: parseRecipeIdList(editable.optimizedClustering.splittableRecipeIds),
      }
    : undefined;
  return {
    package_id: packageId ?? undefined,
    ...(trimmedMilestone ? { selected_milestone: trimmedMilestone } : {}),
    solve_mode: editable.solveMode,
    demands: Object.fromEntries(
      Object.entries(editable.demands)
        .map(([itemId, value]) => [
          itemId,
          displayRateToItemsPerSecond(parseNonnegativeNumber(value), editable.displayRateUnits),
        ] as const)
        .filter(([, value]) => value > 0),
    ),
    external_inputs: editable.externalInputs.map((input) => ({
      item_id: input.item_id,
      kind: input.kind,
      enabled: input.enabled,
      cost: parseNonnegativeNumber(input.cost),
      capacity: parseOptionalNonnegativeNumber(input.capacity),
      source: input.source,
      default_approved: input.defaultApproved,
    })),
    ...(optimizedClustering ? { optimized_clustering: optimizedClustering } : {}),
  };
}

export function displayRateToItemsPerSecond(value: number, units: DisplayRateUnits | string): number {
  if (!Number.isFinite(value)) return 0;
  switch (normalizeDisplayRateUnits(units)) {
    case 'items_per_minute':
      return value / 60;
    case 'items_per_second':
    default:
      return value;
  }
}

export function normalizeDisplayRateUnits(units: DisplayRateUnits | string): DisplayRateUnits {
  if (units === 'items_per_minute' || units === 'items/min' || units === 'items/m') {
    return 'items_per_minute';
  }
  return 'items_per_second';
}

export function findApprovedInputsMissingCapacity(
  externalInputs: EditableExternalInput[],
): string[] {
  return externalInputs
    .filter((input) => input.enabled && !isValidProvidedCapacity(input.capacity))
    .map((input) => input.item_id)
    .sort();
}

export function hasPositiveDemand(demands: Record<string, string>): boolean {
  return Object.values(demands).some((value) => parseNonnegativeNumber(value) > 0);
}

export function problemLocalStorageKey(problem: Pick<ProblemDto, 'package_id' | 'scenario_id'>): string {
  return `factory-plan:${safeKeyPart(problem.package_id, 'default-package')}:${safeKeyPart(
    problem.scenario_id,
    'default-scenario',
  )}`;
}

function isValidProvidedCapacity(value: string): boolean {
  if (value.trim() === '') return false;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0;
}

function safeKeyPart(value: string | null | undefined, fallback: string): string {
  const trimmed = value?.trim();
  if (!trimmed) return fallback;
  return encodeURIComponent(trimmed);
}

function parseOptionalNonnegativeNumber(value: string): number | null {
  if (value.trim() === '') return null;
  return parseNonnegativeNumber(value);
}

function parseNonnegativeNumber(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

function parsePositiveNumber(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function parseRecipeIdList(value: string): string[] {
  return [...new Set(value.split(/[\n,]/).map((entry) => entry.trim()).filter(Boolean))];
}
