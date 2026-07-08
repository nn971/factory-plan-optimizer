import type { ExternalInputDto, ProblemDto, SolveModeDto, SolveRequestDto } from '../api/dtos';

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
};

export function createEditableProblem(problem: ProblemDto): EditableProblem {
  const targetDemandIds = problem.target_demands ?? [];
  const externalInputs = problem.raw_input_candidates.length > 0
    ? problem.raw_input_candidates
    : problem.external_inputs;
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
  };
}

export function toSolveRequest(
  editable: EditableProblem,
  packageId?: string | null,
): SolveRequestDto {
  return {
    package_id: packageId ?? undefined,
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
