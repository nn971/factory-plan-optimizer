import type { FlowSelectionDetails } from '../../domain/solveResultFlow';

export function NodeDetails({ details }: { details: FlowSelectionDetails | null }) {
  return (
    <aside className="flow-node-details" aria-live="polite">
      <p className="eyebrow">Selected graph element</p>
      {details ? (
        <>
          <h4>{details.label}</h4>
          <p className="muted">{details.summary}</p>
          <code>{details.id}</code>
          {details.rows.length > 0 && (
            <dl>
              {details.rows.map((row, index) => (
                <div key={`${row.label}:${row.id ?? ''}:${index}`}>
                  <dt>{row.label}</dt>
                  <dd>
                    {row.id && <code>{row.id}</code>}
                    {row.quantity !== undefined && <strong>{formatNumber(row.quantity)}</strong>}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </>
      ) : (
        <p className="muted">Click an item, recipe, diagnostic, or cluster node to inspect exact IDs and quantities.</p>
      )}
    </aside>
  );
}

function formatNumber(value: number) {
  return Number.isInteger(value) ? String(value) : value.toPrecision(8);
}
