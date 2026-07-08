export type ItemDto = { id: string; kind: 'item' | 'fluid' | 'unknown' };

export type ExternalInputDto = {
  item_id: string;
  kind?: 'item' | 'fluid' | 'unknown';
  enabled: boolean;
  cost: number;
  capacity: number | null;
  source?: 'package_external_supply' | 'inferred_unproduced' | 'inferred_fluid' | null;
  default_approved?: boolean;
};

export type SolveModeDto = 'hard_demand' | 'soft_diagnostics';

export type ProblemDto = {
  package_id?: string | null;
  scenario_id?: string | null;
  scenario_label: string;
  items: ItemDto[];
  demands: Record<string, number>;
  target_demands: string[];
  rate_units: string;
  default_solve_mode: SolveModeDto;
  external_inputs: ExternalInputDto[];
  raw_input_candidates: ExternalInputDto[];
  recipe_ids: string[];
  item_metadata: Record<string, Record<string, string>>;
  recipe_metadata: Record<string, Record<string, string>>;
};

export type SolveRequestDto = {
  package_id?: string | null;
  solve_mode: SolveModeDto;
  demands: Record<string, number>;
  external_inputs: ExternalInputDto[];
};

export type PackageProblemDto = { package_id: string; problem: ProblemDto };

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export type SolveQueuedDto = { job_id: string; status: JobStatus };

export type SolveResultDto = {
  solver_status: string;
  objective_value: number | null;
  objective_components: Record<string, number>;
  recipe_rates: Record<string, number>;
  external_supplies: Record<string, number>;
  unmet_demand: Record<string, number>;
  surplus: Record<string, number>;
  balance_residuals: Record<string, number>;
  message?: string;
  details?: string;
};

export type ErrorDto = { type: string; message: string; details?: string };

export type SolveJobDto = {
  job_id: string;
  status: JobStatus;
  result?: SolveResultDto | null;
  error?: ErrorDto | null;
};
