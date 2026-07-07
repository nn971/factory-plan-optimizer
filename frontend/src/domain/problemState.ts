import type { ProblemDto, SolveRequestDto } from '../api/dtos';

export type EditableExternalInput = {
  item_id: string;
  enabled: boolean;
  cost: string;
  capacity: string;
};

export type EditableProblem = {
  demands: Record<string, string>;
  externalInputs: EditableExternalInput[];
};

export function createEditableProblem(problem: ProblemDto): EditableProblem {
  return {
    demands: Object.fromEntries(
      problem.items.map((item) => [item.id, String(problem.demands[item.id] ?? 0)]),
    ),
    externalInputs: problem.external_inputs.map((input) => ({
      item_id: input.item_id,
      enabled: input.enabled,
      cost: String(input.cost),
      capacity: input.capacity == null ? '' : String(input.capacity),
    })),
  };
}

export function toSolveRequest(editable: EditableProblem): SolveRequestDto {
  return {
    demands: Object.fromEntries(
      Object.entries(editable.demands)
        .map(([itemId, value]) => [itemId, parseNonnegativeNumber(value)] as const)
        .filter(([, value]) => value > 0),
    ),
    external_inputs: editable.externalInputs.map((input) => ({
      item_id: input.item_id,
      enabled: input.enabled,
      cost: parseNonnegativeNumber(input.cost),
      capacity: parseOptionalNonnegativeNumber(input.capacity),
    })),
  };
}

function parseOptionalNonnegativeNumber(value: string): number | null {
  if (value.trim() === '') return null;
  return parseNonnegativeNumber(value);
}

function parseNonnegativeNumber(value: string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}
