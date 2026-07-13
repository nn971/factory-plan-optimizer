import { describe, expect, it } from 'vitest';

import type { ProblemDto } from '../api/dtos';
import type { EditableProblem } from './problemState';
import { createEditableProblem, toSolveRequest } from './problemState';

describe('createEditableProblem', () => {
  it('falls back to external inputs when raw input candidates are absent', () => {
    const problem = {
      package_id: 'legacy-package',
      scenario_id: 'legacy-scenario',
      scenario_label: 'Legacy scenario',
      items: [{ id: 'iron-ore', kind: 'item' }],
      demands: {},
      target_demands: ['science-pack-a'],
      rate_units: 'items/s',
      default_solve_mode: 'hard_demand',
      external_inputs: [{ item_id: 'iron-ore', kind: 'item', enabled: true, cost: 1, capacity: 10 }],
      recipe_ids: [],
      milestones: [],
      item_metadata: {},
      recipe_metadata: {},
    } as unknown as ProblemDto;

    expect(createEditableProblem(problem).externalInputs).toEqual([
      {
        item_id: 'iron-ore',
        kind: 'item',
        enabled: true,
        cost: '1',
        capacity: '10',
        source: undefined,
        defaultApproved: false,
      },
    ]);
  });
});

describe('toSolveRequest', () => {
  it('includes non-empty selected milestone', () => {
    expect(toSolveRequest(editableProblem(), 'package-a', ' science-pack-a ')).toMatchObject({
      package_id: 'package-a',
      selected_milestone: 'science-pack-a',
    });
  });

  it('omits blank selected milestone', () => {
    expect(toSolveRequest(editableProblem(), 'package-a', '  ')).not.toHaveProperty('selected_milestone');
  });

  it('omits optimized clustering config by default', () => {
    expect(toSolveRequest(editableProblem())).not.toHaveProperty('optimized_clustering');
  });

  it('omits sparse clustering config by default', () => {
    expect(toSolveRequest(editableProblem())).not.toHaveProperty('sparse_clustering');
  });

  it('submits optimized clustering config only when enabled', () => {
    expect(
      toSolveRequest({
        ...editableProblem(),
        optimizedClustering: {
          enabled: true,
          allowRecipeSplitting: false,
          splittableRecipeIds: 'recipe-a\nrecipe-b, recipe-a',
          preset: 'fewer_ports',
          reportingEpsilon: '0.00001',
          timeLimitSeconds: '30',
          flowCostPerQuantity: '2',
          portCostPerItemType: '200',
          clusterSizePenaltyWeight: '7',
          minClusterSize: '3',
          maxClusterSize: '12',
          maxClusterSizeConstraint: 'hard',
        },
      }).optimized_clustering,
    ).toEqual({
      enabled: true,
      mode: 'continuous_split',
      preset: 'fewer_ports',
      allow_recipe_splitting: false,
      splittable_recipe_ids: ['recipe-a', 'recipe-b'],
      reporting_epsilon: 0.00001,
      time_limit_seconds: 30,
      flow_cost_per_quantity: 2,
      port_cost_per_item_type: 200,
      cluster_size_penalty_weight: 7,
      min_cluster_size: 3,
      max_cluster_size: 12,
      max_cluster_size_constraint: 'hard',
    });
  });

  it('submits sparse clustering config only when enabled', () => {
    expect(
      toSolveRequest({
        ...editableProblem(),
        sparseClustering: {
          enabled: true,
          mode: 'balanced',
          targetClusterCount: '4',
          minClusterCount: '2',
          maxClusterCount: '8',
          maxRuntimeSeconds: '5',
          hubItemTopK: '50',
          portCostWeight: '1200',
          sizePenaltyWeight: '12',
          flowCostWeight: '0.5',
          minClusterSizeRatio: '0.4',
          maxClusterSizeRatio: '1.8',
          maxRefinementPasses: '6',
          portEpsilon: '0.000001',
        },
      }).sparse_clustering,
    ).toEqual({
      enabled: true,
      mode: 'balanced',
      target_cluster_count: 4,
      min_cluster_count: 2,
      max_cluster_count: 8,
      max_runtime_seconds: 5,
      hub_item_top_k: 50,
      port_cost_weight: 1200,
      size_penalty_weight: 12,
      flow_cost_weight: 0.5,
      min_cluster_size_ratio: 0.4,
      max_cluster_size_ratio: 1.8,
      max_refinement_passes: 6,
      port_epsilon: 0.000001,
    });
  });
});

function editableProblem(): EditableProblem {
  return {
    solveMode: 'hard_demand',
    displayRateUnits: 'items_per_second',
    demands: { 'science-pack-a': '1' },
    externalInputs: [],
    optimizedClustering: {
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
    },
    sparseClustering: {
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
      maxRefinementPasses: '8',
      portEpsilon: '0.000000001',
    },
  };
}
