export type ItemDto = { id: string; kind: 'item' | 'fluid' | 'unknown' };

export type UnlockConditionDto = {
  type: 'technology' | 'start-unlocked' | 'unknown';
  id: string | null;
};

export type ExplorerOverviewDto = {
  item_count: number;
  fluid_count: number;
  recipe_count: number;
  item_categories: string[];
  recipe_categories: string[];
};

export type ExplorerRecipeLinkDto = { id: string; category: string };

export type ExplorerItemDto = {
  id: string;
  kind: 'item' | 'fluid' | 'unknown';
  category: string;
  unlock_condition: UnlockConditionDto;
  produced_by: ExplorerRecipeLinkDto[];
  consumed_by: ExplorerRecipeLinkDto[];
};

export type RecipeTermDto = {
  type: 'item' | 'fluid' | 'unknown';
  name: string;
  amount: number | null;
  amount_min: number | null;
  amount_max: number | null;
  probability: number | null;
  catalyst_amount: number | null;
  temperature: number | null;
  minimum_temperature: number | null;
  maximum_temperature: number | null;
  fluidbox_index: number | null;
};

export type ExplorerRecipeIODto = {
  item_id: string;
  kind: 'item' | 'fluid' | 'unknown';
  category: string;
  amount: number;
  terms: RecipeTermDto[];
};

export type ExplorerRecipeDto = {
  id: string;
  category: string;
  unlock_condition: UnlockConditionDto;
  energy_required: number;
  production_cost: number;
  source_prototype_type: 'recipe' | 'boiler';
  source_prototype_name: string | null;
  inputs: ExplorerRecipeIODto[];
  outputs: ExplorerRecipeIODto[];
};

export type ExplorerResponseDto = {
  package_id: string;
  overview: ExplorerOverviewDto;
  items: ExplorerItemDto[];
  recipes: ExplorerRecipeDto[];
};

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
