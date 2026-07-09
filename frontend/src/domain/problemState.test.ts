import { describe, expect, it } from 'vitest';

import type { EditableProblem } from './problemState';
import { toSolveRequest } from './problemState';

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
});

function editableProblem(): EditableProblem {
  return {
    solveMode: 'hard_demand',
    displayRateUnits: 'items_per_second',
    demands: { 'science-pack-a': '1' },
    externalInputs: [],
  };
}
