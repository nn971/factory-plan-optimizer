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

export type MilestoneDto = {
  item_id: string;
  recipe_ids: string[];
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
  milestones: MilestoneDto[];
  items: ExplorerItemDto[];
  recipes: ExplorerRecipeDto[];
};

export type ExternalInputDto = {
  item_id: string;
  kind?: 'item' | 'fluid' | 'unknown';
  enabled: boolean;
  cost: number;
  capacity: number | null;
  source?: 'default_input' | 'inferred_unproduced' | 'inferred_fluid' | null;
  default_approved?: boolean;
};

export type SolveModeDto = 'hard_demand' | 'soft_diagnostics';

export type OptimizedClusteringPresetDto = 'balanced' | 'fewer_ports' | 'even_size';
export type MaxClusterSizeConstraintDto = 'soft' | 'hard';

export type OptimizedClusteringStatusDto =
  | 'optimal'
  | 'feasible_non_optimal'
  | 'timeout_no_incumbent'
  | 'infeasible'
  | 'solver_unavailable'
  | 'model_too_large'
  | 'no_active_recipes'
  | 'disabled';

export type OptimizedClusteringConfigDto = {
  enabled: boolean;
  mode?: 'continuous_split';
  preset?: OptimizedClusteringPresetDto;
  flow_cost_per_quantity?: number | null;
  port_cost_per_item_type?: number | null;
  cluster_size_penalty_weight?: number | null;
  min_cluster_size?: number | null;
  max_cluster_size?: number | null;
  reporting_epsilon?: number | null;
  time_limit_seconds?: number | null;
  max_cluster_size_constraint?: MaxClusterSizeConstraintDto;
  allow_recipe_splitting?: boolean;
  splittable_recipe_ids?: string[];
};

export type SparseClusteringModeDto = 'fast' | 'balanced' | 'exact-small';


export type SparseClusteringStatusDto =
  | 'success'
  | 'skipped'
  | 'model_too_large'
  | 'timeout'
  | 'unsupported'
  | 'failed';

export type SparseClusteringConfigDto = {
  enabled: boolean;
  mode?: SparseClusteringModeDto;
  target_cluster_count?: number | null;
  min_cluster_count?: number | null;
  max_cluster_count?: number | null;
  max_runtime_seconds?: number | null;
  min_recipe_rate?: number | null;
  hub_item_top_k?: number | null;
  port_cost_weight?: number | null;
  size_penalty_weight?: number | null;
  flow_cost_weight?: number | null;
  min_cluster_size_ratio?: number | null;
  max_cluster_size_ratio?: number | null;
  max_refinement_passes?: number | null;
  port_epsilon?: number | null;
  seed?: number | null;
  result_caps?: Record<string, number>;
};

export type SparseCappedArrayDto<TItem extends Record<string, unknown> = Record<string, unknown>> = {
  items: TItem[];
  total_count: number;
  truncated: boolean;
};

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
  milestones: MilestoneDto[];
  item_metadata: Record<string, Record<string, string>>;
  recipe_metadata: Record<string, Record<string, string>>;
};

export type SolveRequestDto = {
  package_id?: string | null;
  selected_milestone?: string | null;
  solve_mode: SolveModeDto;
  demands: Record<string, number>;
  external_inputs: ExternalInputDto[];
  optimized_clustering?: OptimizedClusteringConfigDto | null;
  sparse_clustering?: SparseClusteringConfigDto | null;
};

export type PackageProblemDto = { package_id: string; problem: ProblemDto };

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export type SolveQueuedDto = { job_id: string; status: JobStatus };

export type ClusterBoundaryDirectionDto = 'input' | 'output';

export type ClusterBoundaryItemDto = {
  item_id: string;
  direction: ClusterBoundaryDirectionDto;
  is_zero_net: boolean;
  quantity: number;
  flow_cost: number;
  port_cost: number;
};

export type ClusterDto = {
  id: string;
  label: string;
  category: string;
  recipe_ids: string[];
  active_recipe_count: number;
  boundary_item_type_count: number;
  boundary_items: ClusterBoundaryItemDto[];
  diagnostic_components: Record<string, number>;
};

export type ClusterCostDefaultsDto = {
  flow_cost_per_quantity: number;
  port_cost_per_boundary_type: number;
  recipe_size_penalty: number;
  boundary_type_size_penalty: number;
  target_active_recipes: number[];
  target_boundary_item_types: number[];
};

export type ClusterDiagnosticsDto = {
  mode: 'diagnostic_only';
  active_epsilon: number;
  cost_defaults: ClusterCostDefaultsDto;
  diagnostic_components: Record<string, number>;
  base_objective_value: number;
  diagnostic_total: number;
  combined_diagnostic_objective_value: number;
  clusters: ClusterDto[];
};

export type OptimizedClusteringClusterDto = {
  cluster_id: string;
  used: boolean;
  size: number;
  under_min: number;
  over_max: number;
};

export type OptimizedClusteringAllocationDto = {
  recipe_id: string;
  cluster_id: string;
  rate: number;
  fraction: number;
};

export type OptimizedClusteringFlowDto = {
  from_cluster_id: string;
  to_cluster_id: string;
  item_id: string;
  quantity: number;
};

export type OptimizedClusteringExternalFlowDto = {
  cluster_id: string;
  item_id: string;
  direction: 'in' | 'out' | string;
  boundary_label: 'aggregate_external_balance' | string;
  quantity: number;
};

export type OptimizedClusteringResultDto = {
  status: OptimizedClusteringStatusDto;
  mode: 'continuous_split';
  effective_parameters: Record<string, boolean | number | string | string[]>;
  objective_value: number | null;
  objective_components: Record<string, number>;
  cost_breakdown: Record<string, number>;
  clusters: OptimizedClusteringClusterDto[];
  allocations: OptimizedClusteringAllocationDto[];
  flows: OptimizedClusteringFlowDto[];
  external_flows: OptimizedClusteringExternalFlowDto[];
  reconciliation: Record<string, boolean | number>;
  message?: string | null;
  details?: string | null;
  model_size?: Record<string, unknown> | null;
};

export type SparseClusterSummaryDto = {
  cluster_id: number | string;
  recipe_count: number;
  recipe_ids: string[];
  net_input_port_count?: number;
  net_output_port_count?: number;
  net_port_count?: number;
};

export type SparseRecipeAssignmentDto = {
  recipe_id: string;
  cluster_id: number | string;
};

export type SparseBoundaryFlowDto = {
  source_cluster_id: number | string;
  target_cluster_id: number | string;
  item_id: string;
  estimated_flow: number;
};

export type SparseBoundaryPortTypeDto = {
  cluster_id: number | string;
  item_id: string;
  direction: 'input' | 'output' | string;
  net_amount?: number;
};

export type SparseExternalBoundaryPortTypeDto = SparseBoundaryPortTypeDto & {
  source_or_demand_amount: number;
};

export type SparseSurplusUnmetSummaryDto = {
  item_id: string;
  surplus: number;
  unmet_demand: number;
};

export type SparseHubSummaryDto = {
  item_id: string;
  kept_count: number;
  skipped_count: number;
  skipped_estimated_flow: number;
};

export type SparsePortAwareObjectiveDto = {
  port_cost: number;
  size_penalty: number;
  flow_cost: number;
  total_score: number;
  net_port_count: number;
  refinement_passes: number;
};

export type SparseClusteringResultDto = {
  status: SparseClusteringStatusDto;
  message: string;
  mode: SparseClusteringModeDto;
  graph_type: 'recipe-to-recipe';
  optimization_effect: 'none';
  fallback_attempted: boolean;
  fallback_mode: 'fast' | null;
  fallback: Record<string, string> | null;
  engine: string | null;
  cluster_count: number | null;
  target_cluster_count: number | null;
  effective_config: Record<string, unknown>;
  warnings: string[];
  quality: Record<string, number> | null;
  boundary_port_type_count: number | null;
  net_port_count?: number | null;
  port_aware_objective?: SparsePortAwareObjectiveDto | null;
  external_boundary_port_type_count: number | null;
  graph_statistics: Record<string, unknown> | null;
  cluster_summaries?: SparseCappedArrayDto<SparseClusterSummaryDto> | null;
  recipe_assignments?: SparseCappedArrayDto<SparseRecipeAssignmentDto> | null;
  boundary_flows?: SparseCappedArrayDto<SparseBoundaryFlowDto> | null;
  boundary_port_types?: SparseCappedArrayDto<SparseBoundaryPortTypeDto> | null;
  external_boundary_port_types?: SparseCappedArrayDto<SparseExternalBoundaryPortTypeDto> | null;
  surplus_unmet_summary?: SparseCappedArrayDto<SparseSurplusUnmetSummaryDto> | null;
  hub_summaries?: SparseCappedArrayDto<SparseHubSummaryDto> | null;
};

export type SolveResultDto = {
  solver_status: string;
  objective_value: number | null;
  objective_components: Record<string, number>;
  recipe_rates: Record<string, number>;
  external_supplies: Record<string, number>;
  unmet_demand: Record<string, number>;
  surplus: Record<string, number>;
  balance_residuals: Record<string, number>;
  cluster_diagnostics?: ClusterDiagnosticsDto | null;
  optimized_clustering?: OptimizedClusteringResultDto | null;
  sparse_clustering?: SparseClusteringResultDto | null;
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
