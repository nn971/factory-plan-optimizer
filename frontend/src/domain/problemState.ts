import type { ExternalInputDto, ProblemDto, SolveModeDto, SolveRequestDto, SparseClusteringModeDto } from '../api/dtos';

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
  sparseClustering: EditableSparseClustering;
  clusteringGuardrails: ClusteringGuardrails;
};

export type ClusteringGuardrails = {
  sparse: {
    maxRuntimeSecondsExclusiveMin: number;
    hubItemTopKMin: number;
  };
};

export type ValidationError = {
  field: string;
  message: string;
};

export class EditableProblemValidationError extends Error {
  readonly errors: ValidationError[];

  constructor(errors: ValidationError[]) {
    super('Editable problem has invalid numeric settings');
    this.name = 'EditableProblemValidationError';
    this.errors = errors;
  }
}

export type EditableSparseClustering = {
  enabled: boolean;
  mode: SparseClusteringModeDto;
  targetClusterCount: string;
  minClusterCount: string;
  maxClusterCount: string;
  maxRuntimeSeconds: string;
  hubItemTopK: string;
  portCostWeight: string;
  sizePenaltyWeight: string;
  flowCostWeight: string;
  minClusterSizeRatio: string;
  maxClusterSizeRatio: string;
  maxRefinementPasses: string;
  portEpsilon: string;
};

export const DEFAULT_RAW_INPUT_ENABLED = true;
export const DEFAULT_RAW_INPUT_COST = '0';
export const DEFAULT_RAW_INPUT_CAPACITY = '1000000';

export type ExternalInputRowIdentity = {
  item_id: string;
  kind?: ExternalInputDto['kind'];
  source?: ExternalInputDto['source'];
  default_approved?: boolean;
};

export function createExternalInputRow(identity: ExternalInputRowIdentity): EditableExternalInput {
  return {
    item_id: identity.item_id,
    kind: identity.kind ?? 'unknown',
    enabled: DEFAULT_RAW_INPUT_ENABLED,
    cost: DEFAULT_RAW_INPUT_COST,
    capacity: DEFAULT_RAW_INPUT_CAPACITY,
    source: identity.source,
    defaultApproved: identity.default_approved ?? false,
  };
}

export const DEFAULT_SPARSE_CLUSTERING: EditableSparseClustering = {
  enabled: false,
  mode: 'fast',
  targetClusterCount: '',
  minClusterCount: '',
  maxClusterCount: '',
  maxRuntimeSeconds: '5',
  hubItemTopK: '100',
  portCostWeight: '1000',
  sizePenaltyWeight: '10',
  flowCostWeight: '0',
  minClusterSizeRatio: '0.5',
  maxClusterSizeRatio: '1.5',
  maxRefinementPasses: '',
  portEpsilon: '0.000000001',
};

export const DEFAULT_CLUSTERING_GUARDRAILS: ClusteringGuardrails = {
  sparse: {
    maxRuntimeSecondsExclusiveMin: 0,
    hubItemTopKMin: 1,
  },
};

export function createEditableProblem(problem: ProblemDto): EditableProblem {
  const targetDemandIds = problem.target_demands ?? [];
  const rawInputCandidates = problem.raw_input_candidates ?? [];
  const externalInputs = rawInputCandidates.length > 0
    ? rawInputCandidates.map((input) => createExternalInputRow(input))
    : (problem.external_inputs ?? []).map((input) => ({
        item_id: input.item_id,
        kind: input.kind ?? 'unknown',
        enabled: input.enabled,
        cost: String(input.cost),
        capacity: input.capacity == null ? '' : String(input.capacity),
        source: input.source,
        defaultApproved: input.default_approved ?? false,
      }));
  return {
    solveMode: problem.default_solve_mode,
    displayRateUnits: normalizeDisplayRateUnits(problem.rate_units),
    demands: Object.fromEntries(
      targetDemandIds.map((itemId) => [itemId, '']),
    ),
    externalInputs,
    sparseClustering: sparseClusteringDefaults(problem.sparse_clustering_defaults),
    clusteringGuardrails: clusteringGuardrails(problem),
  };
}

function clusteringGuardrails(problem: ProblemDto): ClusteringGuardrails {
  const sparse = recordOrEmpty(problem.sparse_clustering_defaults?.guardrails);
  const runtime = recordOrEmpty(sparse.max_runtime_seconds);
  const hubTopK = recordOrEmpty(sparse.hub_item_top_k);
  return {
    sparse: {
      maxRuntimeSecondsExclusiveMin: numericDefault(runtime.exclusive_min, DEFAULT_CLUSTERING_GUARDRAILS.sparse.maxRuntimeSecondsExclusiveMin),
      hubItemTopKMin: numericDefault(hubTopK.min, DEFAULT_CLUSTERING_GUARDRAILS.sparse.hubItemTopKMin),
    },
  };
}

function sparseClusteringDefaults(defaults: Record<string, unknown> | null | undefined): EditableSparseClustering {
  return {
    ...DEFAULT_SPARSE_CLUSTERING,
    enabled: booleanDefault(defaults?.enabled, DEFAULT_SPARSE_CLUSTERING.enabled),
    mode: defaults?.mode === 'balanced' ? 'balanced' : DEFAULT_SPARSE_CLUSTERING.mode,
    maxRuntimeSeconds: numericStringDefault(defaults?.max_runtime_seconds, DEFAULT_SPARSE_CLUSTERING.maxRuntimeSeconds),
    hubItemTopK: numericStringDefault(defaults?.hub_item_top_k, DEFAULT_SPARSE_CLUSTERING.hubItemTopK),
    portCostWeight: numericStringDefault(defaults?.port_cost_weight, DEFAULT_SPARSE_CLUSTERING.portCostWeight),
    sizePenaltyWeight: numericStringDefault(defaults?.size_penalty_weight, DEFAULT_SPARSE_CLUSTERING.sizePenaltyWeight),
    flowCostWeight: numericStringDefault(defaults?.flow_cost_weight, DEFAULT_SPARSE_CLUSTERING.flowCostWeight),
    minClusterSizeRatio: numericStringDefault(defaults?.min_cluster_size_ratio, DEFAULT_SPARSE_CLUSTERING.minClusterSizeRatio),
    maxClusterSizeRatio: numericStringDefault(defaults?.max_cluster_size_ratio, DEFAULT_SPARSE_CLUSTERING.maxClusterSizeRatio),
    maxRefinementPasses: optionalNumericStringDefault(defaults?.max_refinement_passes, DEFAULT_SPARSE_CLUSTERING.maxRefinementPasses),
    portEpsilon: numericStringDefault(defaults?.port_epsilon, DEFAULT_SPARSE_CLUSTERING.portEpsilon),
  };
}

function numericStringDefault(value: unknown, fallback: string): string {
  return typeof value === 'number' && Number.isFinite(value) ? String(value) : fallback;
}

function numericDefault(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function recordOrEmpty(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function optionalNumericStringDefault(value: unknown, fallback: string): string {
  if (value == null) return fallback;
  return numericStringDefault(value, fallback);
}

function booleanDefault(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

export function toSolveRequest(
  editable: EditableProblem,
  packageId?: string | null,
  selectedMilestone?: string | null,
): SolveRequestDto {
  const trimmedMilestone = selectedMilestone?.trim();
  const sparseClustering = editable.sparseClustering.enabled
    ? {
        enabled: true,
        mode: editable.sparseClustering.mode,
        target_cluster_count: parseOptionalPositiveNumber(editable.sparseClustering.targetClusterCount),
        min_cluster_count: parseOptionalPositiveNumber(editable.sparseClustering.minClusterCount),
        max_cluster_count: parseOptionalPositiveNumber(editable.sparseClustering.maxClusterCount),
        max_runtime_seconds: parsePositiveNumber(editable.sparseClustering.maxRuntimeSeconds),
        hub_item_top_k: parsePositiveInteger(editable.sparseClustering.hubItemTopK),
        port_cost_weight: parseNonnegativeNumber(editable.sparseClustering.portCostWeight),
        size_penalty_weight: parseNonnegativeNumber(editable.sparseClustering.sizePenaltyWeight),
        flow_cost_weight: parseNonnegativeNumber(editable.sparseClustering.flowCostWeight),
        min_cluster_size_ratio: parseNonnegativeNumber(editable.sparseClustering.minClusterSizeRatio),
        max_cluster_size_ratio: parseNonnegativeNumber(editable.sparseClustering.maxClusterSizeRatio),
        max_refinement_passes: parseOptionalNonnegativeInteger(editable.sparseClustering.maxRefinementPasses),
        port_epsilon: parseNonnegativeNumber(editable.sparseClustering.portEpsilon),
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
    ...(sparseClustering ? { sparse_clustering: sparseClustering } : {}),
  };
}

export function validateEditableProblem(editable: EditableProblem): ValidationError[] {
  const errors: ValidationError[] = [];
  for (const [itemId, value] of Object.entries(editable.demands)) {
    if (!isOptionalNonnegativeNumber(value)) errors.push(error(`demands.${itemId}`, 'Target rate must be a nonnegative number.'));
  }
  for (const input of editable.externalInputs) {
    if (!input.enabled) continue;
    if (!isValidProvidedCapacity(input.cost)) errors.push(error(`externalInputs.${input.item_id}.cost`, 'Raw input cost must be a finite nonnegative number.'));
    if (!isValidProvidedCapacity(input.capacity)) errors.push(error(`externalInputs.${input.item_id}.capacity`, 'Raw input capacity must be a finite nonnegative number.'));
  }

  if (editable.sparseClustering.enabled) {
    const settings = editable.sparseClustering;
    requireOptionalPositive(errors, 'sparseClustering.targetClusterCount', settings.targetClusterCount);
    requireOptionalPositive(errors, 'sparseClustering.minClusterCount', settings.minClusterCount);
    requireOptionalPositive(errors, 'sparseClustering.maxClusterCount', settings.maxClusterCount);
    requireGreaterThan(errors, 'sparseClustering.maxRuntimeSeconds', settings.maxRuntimeSeconds, editable.clusteringGuardrails.sparse.maxRuntimeSecondsExclusiveMin);
    requireIntegerAtLeast(errors, 'sparseClustering.hubItemTopK', settings.hubItemTopK, editable.clusteringGuardrails.sparse.hubItemTopKMin);
    requireNonnegative(errors, 'sparseClustering.portCostWeight', settings.portCostWeight);
    requireNonnegative(errors, 'sparseClustering.sizePenaltyWeight', settings.sizePenaltyWeight);
    requireNonnegative(errors, 'sparseClustering.flowCostWeight', settings.flowCostWeight);
    requireNonnegative(errors, 'sparseClustering.minClusterSizeRatio', settings.minClusterSizeRatio);
    requireNonnegative(errors, 'sparseClustering.maxClusterSizeRatio', settings.maxClusterSizeRatio);
    requireOptionalNonnegativeInteger(errors, 'sparseClustering.maxRefinementPasses', settings.maxRefinementPasses);
    requireNonnegative(errors, 'sparseClustering.portEpsilon', settings.portEpsilon);
    const min = parseNumber(settings.minClusterCount);
    const max = parseNumber(settings.maxClusterCount);
    const target = parseNumber(settings.targetClusterCount);
    if (min != null && max != null && min > max) errors.push(error('sparseClustering.minClusterCount', 'Min clusters cannot exceed max clusters.'));
    if (target != null && min != null && target < min) errors.push(error('sparseClustering.targetClusterCount', 'Target clusters cannot be below min clusters.'));
    if (target != null && max != null && target > max) errors.push(error('sparseClustering.targetClusterCount', 'Target clusters cannot be above max clusters.'));
    const minRatio = parseNumber(settings.minClusterSizeRatio);
    const maxRatio = parseNumber(settings.maxClusterSizeRatio);
    if (minRatio != null && maxRatio != null && minRatio > maxRatio) errors.push(error('sparseClustering.minClusterSizeRatio', 'Min cluster size ratio cannot exceed max cluster size ratio.'));
  }

  return errors;
}

export function toValidatedSolveRequest(editable: EditableProblem, packageId?: string | null, selectedMilestone?: string | null): SolveRequestDto {
  const errors = validateEditableProblem(editable);
  if (errors.length > 0) throw new EditableProblemValidationError(errors);
  return toSolveRequest(editable, packageId, selectedMilestone);
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

function parseOptionalPositiveNumber(value: string): number | null {
  if (value.trim() === '') return null;
  const parsed = parsePositiveNumber(value);
  return parsed > 0 ? parsed : null;
}

function parseOptionalNonnegativeInteger(value: string): number | null {
  if (value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

function parseNonnegativeNumber(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

function parsePositiveNumber(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function parsePositiveInteger(value: string): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 0;
}

function error(field: string, message: string): ValidationError {
  return { field, message };
}

function parseNumber(value: string): number | null {
  if (value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function isOptionalNonnegativeNumber(value: string): boolean {
  if (value.trim() === '') return true;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0;
}

function requireNonnegative(errors: ValidationError[], field: string, value: string): void {
  const parsed = parseNumber(value);
  if (parsed == null || parsed < 0) errors.push(error(field, 'Must be a nonnegative number.'));
}

function requirePositive(errors: ValidationError[], field: string, value: string): void {
  const parsed = parseNumber(value);
  if (parsed == null || parsed <= 0) errors.push(error(field, 'Must be a positive number.'));
}

function requireOptionalPositive(errors: ValidationError[], field: string, value: string): void {
  if (value.trim() === '') return;
  requirePositive(errors, field, value);
}

function requireRange(errors: ValidationError[], field: string, value: string, min: number, max: number): void {
  const parsed = parseNumber(value);
  if (parsed == null || parsed < min || parsed > max) errors.push(error(field, `Must be between ${min} and ${max}.`));
}

function requireGreaterThan(errors: ValidationError[], field: string, value: string, minExclusive: number): void {
  const parsed = parseNumber(value);
  if (parsed == null || parsed <= minExclusive) errors.push(error(field, `Must be greater than ${minExclusive}.`));
}

function requireIntegerAtLeast(errors: ValidationError[], field: string, value: string, min: number): void {
  const parsed = Number(value);
  if (value.trim() === '' || !Number.isInteger(parsed) || parsed < min) errors.push(error(field, `Must be an integer at least ${min}.`));
}

function requireOptionalNonnegativeInteger(errors: ValidationError[], field: string, value: string): void {
  if (value.trim() === '') return;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) errors.push(error(field, 'Must be a nonnegative integer.'));
}

function parseRecipeIdList(value: string): string[] {
  return [...new Set(value.split(/[\n,]/).map((entry) => entry.trim()).filter(Boolean))];
}
