import { useMemo, useRef, useState } from 'react';

import type { ProblemDto } from '../api/dtos';
import { friendlyItemName } from '../domain/itemDisplay';
import type { EditableExternalInput } from '../domain/problemState';
import {
  createExternalInputRow,
  type EditableProblem,
} from '../domain/problemState';
import {
  dropdownKeyTransition,
  dropdownClosedState,
  rawInputSearchResults,
  selectionAction,
  type RawInputCatalogEntry,
} from '../domain/rawInputCatalog';

export function RawInputReviewPanel({
  problem,
  externalInputs,
  onChange,
}: {
  problem: Pick<ProblemDto, 'items' | 'raw_input_candidates'>;
  externalInputs: EditableExternalInput[];
  onChange: (externalInputs: EditableProblem['externalInputs']) => void;
}) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const rowRefs = useRef(new Map<string, HTMLDivElement>());
  const itemNames = useMemo(() => new Set(problem.items.map((item) => item.id)), [problem.items]);
  const results = rawInputSearchResults(problem, externalInputs, query);

  function updateExternalInput(itemId: string, patch: Partial<{ enabled: boolean; cost: string; capacity: string }>) {
    onChange(externalInputs.map((input) => (input.item_id === itemId ? { ...input, ...patch } : input)));
  }

  function removeExternalInput(itemId: string) {
    onChange(externalInputs.filter((input) => input.item_id !== itemId));
  }

  function focusRow(itemId: string) {
    window.setTimeout(() => {
      const row = rowRefs.current.get(itemId);
      row?.scrollIntoView({ block: 'nearest' });
      row?.focus();
    }, 0);
  }

  function selectEntry(entry: RawInputCatalogEntry) {
    const action = selectionAction(entry);
    if (action.type === 'focus') {
      focusRow(action.item_id);
    } else if (!externalInputs.some((input) => input.item_id === action.item_id)) {
      onChange([...externalInputs, createExternalInputRow(action)]);
      focusRow(action.item_id);
    }
    setQuery('');
    setOpen(false);
    setActiveIndex(-1);
  }

  return (
    <>
      <div className="raw-input-search">
        <label className="raw-input-search-label">
          Search or add raw input
          <input
            type="search"
            placeholder="Type an item or fluid id"
            value={query}
            aria-controls="raw-input-results"
            onFocus={() => setOpen(true)}
            onChange={(event) => {
              setQuery(event.target.value);
              setOpen(true);
              setActiveIndex(-1);
            }}
            onKeyDown={(event) => {
              if (!['ArrowDown', 'ArrowUp', 'Enter', 'Escape'].includes(event.key)) return;
              event.preventDefault();
              const next = dropdownKeyTransition({ open, activeIndex }, event.key as 'ArrowDown' | 'ArrowUp' | 'Enter' | 'Escape', results.length);
              if (next.select && results[activeIndex]) {
                selectEntry(results[activeIndex]);
                const closed = dropdownClosedState();
                setOpen(closed.open);
                setActiveIndex(closed.activeIndex);
                return;
              }
              setOpen(next.open);
              setActiveIndex(next.activeIndex);
            }}
          />
        </label>
        <p className="raw-input-search-hint">Suggestions open first; searching also checks the full loaded catalog.</p>
        {open && (
          <RawInputSearchResultsList results={results} activeIndex={activeIndex} onSelect={selectEntry} />
        )}
      </div>

      {externalInputs.map((input) => (
        <div
          className="input-card raw-input-row"
          key={input.item_id}
          ref={(node) => {
            if (node) rowRefs.current.set(input.item_id, node);
            else rowRefs.current.delete(input.item_id);
          }}
          tabIndex={-1}
        >
          <div className="raw-input-row-main">
            <label className="check raw-input-enable">
              <input type="checkbox" checked={input.enabled} onChange={(event) => updateExternalInput(input.item_id, { enabled: event.target.checked })} />{' '}
              <span>
                <strong>{friendlyItemName(input.item_id)}</strong>
                <small>{input.enabled ? 'Used in solve payload' : 'Kept here, not used while off'}</small>
              </span>
            </label>
            <div className="raw-input-row-meta">
              <span className={`source-pill raw-kind raw-kind-${input.kind ?? 'unknown'}`}>{input.kind ?? 'unknown'}</span>
              <span className="source-pill">{sourceLabel(input.source)}</span>
              {!itemNames.has(input.item_id) && <small>Not in item table</small>}
              {input.defaultApproved && <small>Default suggestion</small>}
            </div>
          </div>
          <button type="button" className="remove-input" onClick={() => removeExternalInput(input.item_id)}>Remove</button>
          <label>
            Cost
            <input type="number" min="0" step="any" value={input.cost} onChange={(event) => updateExternalInput(input.item_id, { cost: event.target.value })} />
          </label>
          <label>
            Capacity
            <input type="number" min="0" step="any" placeholder="required cap" value={input.capacity} onChange={(event) => updateExternalInput(input.item_id, { capacity: event.target.value })} />
          </label>
        </div>
      ))}
      {!externalInputs.length && <p className="muted">No raw inputs selected. Search the catalog to add one.</p>}
    </>
  );
}

export function RawInputSearchResultsList({
  results,
  activeIndex,
  onSelect,
}: {
  results: RawInputCatalogEntry[];
  activeIndex: number;
  onSelect: (entry: RawInputCatalogEntry) => void;
}) {
  return (
    <div className="raw-input-dropdown" id="raw-input-results" role="listbox">
      {results.length ? results.map((entry, index) => (
        <button
          type="button"
          role="option"
          aria-selected={index === activeIndex}
          className={`raw-input-option ${index === activeIndex ? 'active' : ''}`}
          key={entry.item_id}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => onSelect(entry)}
        >
          <span className="raw-input-option-main">
            <span className={`source-pill raw-kind raw-kind-${entry.kind}`}>{entry.kind}</span>
            <span>
              <strong>{entry.label}</strong>
              <small>{entry.item_id}</small>
            </span>
          </span>
          <span className="raw-input-option-meta">
            {entry.isStartupSuggestion && <small>Suggested</small>}
            {entry.source && <small>{sourceLabel(entry.source)}</small>}
          </span>
          <span className={`raw-input-option-state ${entry.isExisting ? 'existing' : ''}`}>{entry.isExisting ? 'Focus' : 'Add'}</span>
        </button>
      )) : <p className="muted raw-input-empty">No matching catalog entries.</p>}
    </div>
  );
}

function sourceLabel(source: string | null | undefined): string {
  switch (source) {
    case 'package_external_supply':
    case 'default_input':
      return 'Default input';
    case 'inferred_unproduced':
      return 'Suggested';
    case 'inferred_fluid':
      return 'Suggested fluid';
    default:
      return 'Catalog';
  }
}
