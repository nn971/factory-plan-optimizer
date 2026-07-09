import { useState } from 'react';

import type { SolveResultDto } from '../../api/dtos';
import { EPSILON, objectiveComponentInfo } from '../../domain/solveOutcome';

export function RawResultTables({ result }: { result: SolveResultDto }) {
  const [filter, setFilter] = useState('');
  return (
    <div className="result-raw-tables">
      <input
        type="search"
        placeholder="Filter result rows"
        value={filter}
        onChange={(event) => setFilter(event.target.value)}
      />
      <KeyValueTable title="Recipe rates" values={result.recipe_rates} filter={filter} onlyNonzero />
      <ObjectiveComponentsTable values={result.objective_components} filter={filter} />
      <KeyValueTable title="External supplies" values={result.external_supplies} filter={filter} onlyNonzero />
      <KeyValueTable title="Unmet demand" values={result.unmet_demand} filter={filter} onlyNonzero />
      <KeyValueTable title="Surplus" values={result.surplus} filter={filter} onlyNonzero />
      <KeyValueTable title="Residuals" values={result.balance_residuals} filter={filter} onlyNonzero />
      {result.details && (
        <details>
          <summary>Debug details</summary>
          <pre>{result.details}</pre>
        </details>
      )}
    </div>
  );
}

function ObjectiveComponentsTable({ values, filter }: { values: Record<string, number>; filter: string }) {
  const normalizedFilter = filter.toLowerCase();
  const rows = Object.entries(values).filter(([key]) => key.toLowerCase().includes(normalizedFilter));
  return (
    <section className="kv">
      <h3>Objective components</h3>
      {rows.length ? (
        <table>
          <tbody>
            {rows.map(([key, value]) => {
              const info = objectiveComponentInfo[key];
              return (
                <tr key={key} title={info?.description}>
                  <th>{info ? `${info.label} (${key})` : key}</th>
                  <td>{formatNumber(value)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="muted">None</p>
      )}
    </section>
  );
}

function KeyValueTable({
  title,
  values,
  filter = '',
  onlyNonzero = false,
}: {
  title: string;
  values: Record<string, number>;
  filter?: string;
  onlyNonzero?: boolean;
}) {
  const normalizedFilter = filter.toLowerCase();
  const rows = Object.entries(values).filter(
    ([key, value]) => key.toLowerCase().includes(normalizedFilter) && (!onlyNonzero || Math.abs(value) > EPSILON),
  );
  return (
    <section className="kv">
      <h3>{title}</h3>
      {rows.length ? (
        <table>
          <tbody>
            {rows.map(([key, value]) => (
              <tr key={key}>
                <th>{key}</th>
                <td>{formatNumber(value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">None</p>
      )}
    </section>
  );
}

function formatNumber(value: number) {
  return Number.isInteger(value) ? String(value) : value.toPrecision(8);
}
