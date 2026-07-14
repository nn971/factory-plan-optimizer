import { describe, expect, it } from 'vitest';

import type { ExplorerResponseDto, SolveJobDto } from '../api/dtos';
import { graphAvailability } from './solveOutcome';

describe('graphAvailability', () => {
  it('reports partial graph state when explorer is absent even if stale flag is set', () => {
    const status = graphAvailability({
      job: solvedJob(),
      explorer: null,
      explorerLoading: false,
      explorerStale: true,
      currentPackageId: 'package-a',
    });

    expect(status).toMatchObject({
      label: 'Recipe data not loaded',
      tone: 'info',
    });
    expect(status.description).toContain('partial ID-only graph');
  });

  it('reports stale explorer topology when explorer is present and stale', () => {
    const status = graphAvailability({
      job: solvedJob(),
      explorer: explorer('package-a'),
      explorerLoading: false,
      explorerStale: true,
      currentPackageId: 'package-a',
    });

    expect(status).toMatchObject({
      label: 'Recipe data stale',
      tone: 'warning',
    });
    expect(status.description).toContain('available explorer topology');
  });

  it('reports package mismatch as warning while allowing explorer-backed topology', () => {
    const status = graphAvailability({
      job: solvedJob(),
      explorer: explorer('package-b'),
      explorerLoading: false,
      explorerStale: false,
      currentPackageId: 'package-a',
    });

    expect(status).toMatchObject({
      label: 'Recipe data mismatch',
      tone: 'warning',
    });
    expect(status.description).toContain('available explorer topology');
  });
});

function solvedJob(): SolveJobDto {
  return {
    job_id: 'job-1',
    status: 'succeeded',
    result: {
      solver_status: 'optimal',
      objective_value: 1,
      objective_components: {},
      recipe_rates: {},
      external_supplies: {},
      unmet_demand: {},
      surplus: {},
      balance_residuals: {},
    },
    error: null,
  };
}

function explorer(packageId: string): ExplorerResponseDto {
  return {
    package_id: packageId,
    overview: {
      item_count: 0,
      fluid_count: 0,
      recipe_count: 0,
      item_categories: [],
      recipe_categories: [],
    },
    milestones: [],
    items: [],
    recipes: [],
  };
}
