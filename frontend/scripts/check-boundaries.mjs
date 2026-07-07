import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const forbidden = [/factory_plan_optimizer/, /optimizer-core/, /\.py\b/, /backend\//];
const roots = ['src'];
const violations = [];

// This is a small frontend/backend/Python separation check. It does not enforce
// internal frontend layer direction between src/api, src/domain, and src/ui.

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) walk(path);
    else if (/\.(ts|tsx|css|html)$/.test(name)) {
      const text = readFileSync(path, 'utf8');
      for (const pattern of forbidden) if (pattern.test(text)) violations.push(`${path}: ${pattern}`);
    }
  }
}

for (const root of roots) walk(root);
if (violations.length) {
  console.error('Frontend boundary violations found:');
  console.error(violations.join('\n'));
  process.exit(1);
}
console.log('Frontend backend/Python boundary check passed.');
