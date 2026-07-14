import { describe, expect, it } from 'vitest';

import type { ProblemDto } from '../api/dtos';
import type { EditableProblem } from './problemState';
import { DEFAULT_CLUSTERING_GUARDRAILS, EditableProblemValidationError, createEditableProblem, toSolveRequest, toValidatedSolveRequest, validateEditableProblem } from './problemState';

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

  it('uses API clustering defaults when present', () => {
    const editable = createEditableProblem({
      package_id: 'package-a',
      scenario_id: 'scenario-a',
      scenario_label: 'Scenario',
      items: [],
      demands: {},
      target_demands: [],
      rate_units: 'items/s',
      default_solve_mode: 'hard_demand',
      external_inputs: [],
      raw_input_candidates: [],
      recipe_ids: [],
      milestones: [],
      item_metadata: {},
      recipe_metadata: {},
      sparse_clustering_defaults: {
        mode: 'fast',
        max_runtime_seconds: 7,
        hub_item_top_k: 80,
        port_cost_weight: 900,
        size_penalty_weight: 11,
        flow_cost_weight: 0,
        min_cluster_size_ratio: 0.25,
        max_cluster_size_ratio: 2,
        max_refinement_passes: null,
        port_epsilon: 1e-8,
      },
    });

    expect(editable.sparseClustering.maxRuntimeSeconds).toBe('7');
    expect(editable.sparseClustering.maxRefinementPasses).toBe('');
    expect(editable.clusteringGuardrails.sparse.maxRuntimeSecondsExclusiveMin).toBe(0);
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

  it('omits sparse clustering config by default', () => {
    expect(toSolveRequest(editableProblem())).not.toHaveProperty('sparse_clustering');
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

  it('does not send an explicit sparse fast refinement override by default', () => {
    const request = toSolveRequest({
      ...editableProblem(),
      sparseClustering: {
        ...editableProblem().sparseClustering,
        enabled: true,
        mode: 'fast',
      },
    });

    expect(request.sparse_clustering?.max_refinement_passes).toBeNull();
  });
});

describe('validateEditableProblem', () => {
  it('reports malformed demand and external input numbers', () => {
    const errors = validateEditableProblem({
      ...editableProblem(),
      demands: { 'science-pack-a': 'abc', 'science-pack-b': '-1' },
      externalInputs: [{ item_id: 'iron-ore', kind: 'item', enabled: true, cost: 'bad', capacity: '-5', defaultApproved: true }],
    });

    expect(errors.map((error) => error.field)).toEqual([
      'demands.science-pack-a',
      'demands.science-pack-b',
      'externalInputs.iron-ore.cost',
      'externalInputs.iron-ore.capacity',
    ]);
  });

  it('applies sparse clustering integer, guardrail, and relationship checks', () => {
    const errors = validateEditableProblem({
      ...editableProblem(),
      sparseClustering: {
        ...editableProblem().sparseClustering,
        enabled: true,
        targetClusterCount: '1',
        minClusterCount: '2',
        maxClusterCount: 'bad',
        maxRuntimeSeconds: '0',
        hubItemTopK: '1.5',
        maxRefinementPasses: '2.2',
        minClusterSizeRatio: '2',
        maxClusterSizeRatio: '1',
      },
    });

    expect(errors.map((error) => error.field)).toEqual(expect.arrayContaining([
      'sparseClustering.maxClusterCount',
      'sparseClustering.maxRuntimeSeconds',
      'sparseClustering.hubItemTopK',
      'sparseClustering.maxRefinementPasses',
      'sparseClustering.targetClusterCount',
      'sparseClustering.minClusterSizeRatio',
    ]));
  });
});

describe('toValidatedSolveRequest', () => {
  it('throws structured errors instead of serializing invalid numbers', () => {
    const editable = { ...editableProblem(), demands: { 'science-pack-a': 'not-a-number' } };

    expect(() => toValidatedSolveRequest(editable)).toThrow(EditableProblemValidationError);
    try {
      toValidatedSolveRequest(editable);
    } catch (error) {
      expect(error).toBeInstanceOf(EditableProblemValidationError);
      expect((error as EditableProblemValidationError).errors).toEqual([
        { field: 'demands.science-pack-a', message: 'Target rate must be a nonnegative number.' },
      ]);
    }
  });
});

function editableProblem(): EditableProblem {
  return {
    solveMode: 'hard_demand',
    displayRateUnits: 'items_per_second',
    demands: { 'science-pack-a': '1' },
    externalInputs: [],
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
      maxRefinementPasses: '',
      portEpsilon: '0.000000001',
    },
    clusteringGuardrails: DEFAULT_CLUSTERING_GUARDRAILS,
  };
}
