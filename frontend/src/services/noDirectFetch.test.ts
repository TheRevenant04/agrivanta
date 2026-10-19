import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC_DIR = join(process.cwd(), 'src');
const SERVICES_DIR = join(SRC_DIR, 'services');

function listSourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const fullPath = join(dir, entry);

    if (statSync(fullPath).isDirectory()) {
      return listSourceFiles(fullPath);
    }

    return /\.(ts|tsx)$/.test(entry) ? [fullPath] : [];
  });
}

const forbiddenPatterns: Array<{ name: string; pattern: RegExp }> = [
  { name: 'fetch()', pattern: /\bfetch\s*\(/ },
  { name: 'XMLHttpRequest', pattern: /\bXMLHttpRequest\b/ },
  { name: 'axios', pattern: /from\s+['"]axios['"]/ },
];

describe('services layer is the only backend surface', () => {
  it('has no component, page, hook, or store outside src/services calling the backend directly', () => {
    const violations = listSourceFiles(SRC_DIR)
      .filter((file) => !file.startsWith(SERVICES_DIR + sep))
      .flatMap((file) => {
        const source = readFileSync(file, 'utf8');

        return forbiddenPatterns
          .filter(({ pattern }) => pattern.test(source))
          .map(({ name }) => `${relative(SRC_DIR, file)}: ${name}`);
      });

    expect(violations).toEqual([]);
  });
});
