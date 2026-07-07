export type ItemDto = { id: string; kind: 'item' | 'fluid' | 'unknown' };

export type ExternalInputDto = {
  item_id: string;
  enabled: boolean;
  cost: number;
  capacity: number | null;
};

export type ProblemDto = {
  package_id?: string | null;
  items: ItemDto[];
  demands: Record<string, number>;
  external_inputs: ExternalInputDto[];
  recipe_ids: string[];
};

export type SolveRequestDto = {
  package_id?: string | null;
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
