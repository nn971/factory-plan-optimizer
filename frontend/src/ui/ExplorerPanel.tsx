import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import type {
  ExplorerItemDto,
  ExplorerRecipeDto,
  ExplorerRecipeIODto,
  ExplorerRecipeLinkDto,
  ExplorerResponseDto,
  UnlockConditionDto,
} from '../api/dtos';
import {
  filterExplorerItems,
  filterExplorerRecipes,
  selectedItem,
  selectedRecipe,
  type ExplorerKindFilter,
  type ExplorerSelection,
} from '../domain/explorerState';

type ExplorerPanelProps = {
  explorer: ExplorerResponseDto | null;
  loading: boolean;
  stale: boolean;
  selection: ExplorerSelection;
  onSelect: (selection: ExplorerSelection) => void;
  onRefresh: () => void;
};

export function ExplorerPanel({ explorer, loading, stale, selection, onSelect, onRefresh }: ExplorerPanelProps) {
  const [itemSearch, setItemSearch] = useState('');
  const [recipeSearch, setRecipeSearch] = useState('');
  const [kindFilter, setKindFilter] = useState<ExplorerKindFilter>('all');
  const [itemCategory, setItemCategory] = useState('all');
  const [recipeCategory, setRecipeCategory] = useState('all');
  const packageId = explorer?.package_id ?? null;

  useEffect(() => {
    setItemSearch('');
    setRecipeSearch('');
    setKindFilter('all');
    setItemCategory('all');
    setRecipeCategory('all');
  }, [packageId]);

  const visibleItems = useMemo(
    () => filterExplorerItems(explorer?.items ?? [], itemSearch, kindFilter, itemCategory),
    [explorer, itemCategory, itemSearch, kindFilter],
  );
  const visibleRecipes = useMemo(
    () => filterExplorerRecipes(explorer?.recipes ?? [], recipeSearch, recipeCategory),
    [explorer, recipeCategory, recipeSearch],
  );
  const item = selectedItem(selection, explorer);
  const recipe = selectedRecipe(selection, explorer);

  return (
    <section className="explorer-shell">
      <div className="explorer-header panel">
        <div>
          <p className="eyebrow">Read-only encyclopedia</p>
          <h2>Item and recipe explorer</h2>
          <p className="muted">
            Browse the active package without starting the solver. Follow producers, consumers,
            inputs, and outputs as links.
          </p>
        </div>
        <div className="explorer-status">
          {explorer && <span className="source-pill">package {explorer.package_id}</span>}
          {stale && <span className="source-pill warning">needs refresh</span>}
          <button type="button" onClick={onRefresh} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh explorer'}
          </button>
        </div>
      </div>

      <div className="explorer-layout">
        <aside className="panel explorer-index" aria-label="Explorer index">
          <IndexSection
            title="Items and fluids"
            count={visibleItems.length}
            search={itemSearch}
            onSearch={setItemSearch}
            searchPlaceholder="Search item id"
          >
            <div className="explorer-controls">
              <label>
                Kind
                <select value={kindFilter} onChange={(event) => setKindFilter(event.target.value as ExplorerKindFilter)}>
                  <option value="all">All</option>
                  <option value="item">Items</option>
                  <option value="fluid">Fluids</option>
                  <option value="unknown">Unknown</option>
                </select>
              </label>
              <CategorySelect value={itemCategory} categories={explorer?.overview.item_categories ?? []} onChange={setItemCategory} />
            </div>
            <EntityList
              emptyLabel="No matching items or fluids."
              rows={visibleItems.map((row) => ({ id: row.id, category: row.category, meta: row.kind }))}
              activeId={selection?.type === 'item' ? selection.id : null}
              onSelect={(id) => onSelect({ type: 'item', id })}
            />
          </IndexSection>

          <IndexSection
            title="Recipes"
            count={visibleRecipes.length}
            search={recipeSearch}
            onSearch={setRecipeSearch}
            searchPlaceholder="Search recipe id"
          >
            <div className="explorer-controls single">
              <CategorySelect value={recipeCategory} categories={explorer?.overview.recipe_categories ?? []} onChange={setRecipeCategory} />
            </div>
            <EntityList
              emptyLabel="No matching recipes."
              rows={visibleRecipes.map((row) => ({ id: row.id, category: row.category, meta: 'recipe' }))}
              activeId={selection?.type === 'recipe' ? selection.id : null}
              onSelect={(id) => onSelect({ type: 'recipe', id })}
            />
          </IndexSection>
        </aside>

        <main className="panel explorer-detail">
          {loading && !explorer ? (
            <p>Loading explorer data…</p>
          ) : explorer == null ? (
            <EmptyExplorer onRefresh={onRefresh} loading={loading} />
          ) : item ? (
            <ItemDetail item={item} onSelectRecipe={(id) => onSelect({ type: 'recipe', id })} />
          ) : recipe ? (
            <RecipeDetail recipe={recipe} onSelectItem={(id) => onSelect({ type: 'item', id })} />
          ) : (
            <Overview explorer={explorer} />
          )}
        </main>
      </div>
    </section>
  );
}

function IndexSection({
  title,
  count,
  search,
  onSearch,
  searchPlaceholder,
  children,
}: {
  title: string;
  count: number;
  search: string;
  onSearch: (value: string) => void;
  searchPlaceholder: string;
  children: ReactNode;
}) {
  return (
    <section className="explorer-index-section">
      <div className="explorer-section-title">
        <h3>{title}</h3>
        <span>{count}</span>
      </div>
      <input type="search" placeholder={searchPlaceholder} value={search} onChange={(event) => onSearch(event.target.value)} />
      {children}
    </section>
  );
}

function CategorySelect({ value, categories, onChange }: { value: string; categories: string[]; onChange: (value: string) => void }) {
  return (
    <label>
      Category
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="all">All</option>
        {categories.map((category) => (
          <option value={category} key={category}>
            {category}
          </option>
        ))}
      </select>
    </label>
  );
}

function EntityList({
  rows,
  activeId,
  onSelect,
  emptyLabel,
}: {
  rows: { id: string; category: string; meta: string }[];
  activeId: string | null;
  onSelect: (id: string) => void;
  emptyLabel: string;
}) {
  if (!rows.length) return <p className="muted">{emptyLabel}</p>;
  return (
    <div className="entity-list">
      {rows.map((row) => (
        <button
          type="button"
          className={`entity-row ${activeId === row.id ? 'active' : ''}`}
          key={`${row.meta}-${row.id}`}
          onClick={() => onSelect(row.id)}
        >
          <span>
            <strong>{row.id}</strong>
            <small>{row.category}</small>
          </span>
          <em>{row.meta}</em>
        </button>
      ))}
    </div>
  );
}

function Overview({ explorer }: { explorer: ExplorerResponseDto }) {
  return (
    <div className="overview-card">
      <p className="eyebrow">Start here</p>
      <h2>Pick an item, fluid, or recipe.</h2>
      <p className="muted">
        Search or filter the lists, then select an entry to inspect producers, consumers,
        inputs, outputs, categories, and unlock conditions.
      </p>
      <div className="overview-stats">
        <Stat label="items" value={explorer.overview.item_count} />
        <Stat label="fluids" value={explorer.overview.fluid_count} />
        <Stat label="recipes" value={explorer.overview.recipe_count} />
      </div>
    </div>
  );
}

function EmptyExplorer({ onRefresh, loading }: { onRefresh: () => void; loading: boolean }) {
  return (
    <div className="overview-card">
      <h2>Explorer data is not loaded yet.</h2>
      <p className="muted">Open the explorer to load the active package, or refresh it now.</p>
      <button type="button" className="primary" onClick={onRefresh} disabled={loading}>
        Load explorer
      </button>
    </div>
  );
}

function ItemDetail({ item, onSelectRecipe }: { item: ExplorerItemDto; onSelectRecipe: (id: string) => void }) {
  return (
    <article className="detail-card">
      <DetailHeading eyebrow={item.kind} title={item.id} category={item.category} unlock={item.unlock_condition} />
      <div className="detail-grid">
        <LinkSection title="Produced by" links={item.produced_by} onSelect={onSelectRecipe} empty="No producing recipes." />
        <LinkSection title="Consumed by" links={item.consumed_by} onSelect={onSelectRecipe} empty="No consuming recipes." />
      </div>
    </article>
  );
}

function RecipeDetail({ recipe, onSelectItem }: { recipe: ExplorerRecipeDto; onSelectItem: (id: string) => void }) {
  return (
    <article className="detail-card">
      <DetailHeading eyebrow="recipe" title={recipe.id} category={recipe.category} unlock={recipe.unlock_condition} />
      <p className="production-cost">Production cost: <strong>{formatNumber(recipe.production_cost)}</strong></p>
      <div className="detail-grid">
        <IOSection title="Inputs" rows={recipe.inputs} onSelect={onSelectItem} empty="No inputs listed." />
        <IOSection title="Outputs" rows={recipe.outputs} onSelect={onSelectItem} empty="No outputs listed." />
      </div>
    </article>
  );
}

function DetailHeading({ eyebrow, title, category, unlock }: { eyebrow: string; title: string; category: string; unlock: UnlockConditionDto }) {
  return (
    <header className="detail-heading">
      <p className="eyebrow">{eyebrow}</p>
      <h2>{title}</h2>
      <div className="detail-badges">
        <span className={`source-pill ${category === 'unknown' ? 'unknown' : ''}`}>category {category}</span>
        <UnlockBadge unlock={unlock} />
      </div>
    </header>
  );
}

function LinkSection({ title, links, onSelect, empty }: { title: string; links: ExplorerRecipeLinkDto[]; onSelect: (id: string) => void; empty: string }) {
  return (
    <section className="relationship-section">
      <h3>{title}</h3>
      {links.length ? (
        <div className="link-stack">
          {links.map((link) => (
            <button type="button" className="relation-link" key={link.id} onClick={() => onSelect(link.id)}>
              <span>{link.id}</span>
              <small>{link.category}</small>
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">{empty}</p>
      )}
    </section>
  );
}

function IOSection({ title, rows, onSelect, empty }: { title: string; rows: ExplorerRecipeIODto[]; onSelect: (id: string) => void; empty: string }) {
  return (
    <section className="relationship-section">
      <h3>{title}</h3>
      {rows.length ? (
        <div className="link-stack">
          {rows.map((row) => (
            <button type="button" className="io-link" key={row.item_id} onClick={() => onSelect(row.item_id)}>
              <span>
                <strong>{row.item_id}</strong>
                <small>{row.category} · {row.kind}</small>
              </span>
              <em>{formatNumber(row.amount)}</em>
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">{empty}</p>
      )}
    </section>
  );
}

function UnlockBadge({ unlock }: { unlock: UnlockConditionDto }) {
  if (unlock.type === 'technology') {
    return <span className="source-pill tech">technology {unlock.id}</span>;
  }
  if (unlock.type === 'start-unlocked') {
    return <span className="source-pill start">start-unlocked</span>;
  }
  return <span className="source-pill unknown">unlock unknown</span>;
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat-card">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function formatNumber(value: number) {
  return Number.isInteger(value) ? String(value) : value.toPrecision(8);
}
