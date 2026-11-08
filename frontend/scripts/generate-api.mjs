import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { readFile, unlink, writeFile } from 'node:fs/promises';

const frontendDirectory = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
const localSchema = path.resolve(
  frontendDirectory,
  '..',
  'backend',
  'api',
  'openapi.yaml',
);
const generatedSchema = path.join(
  frontendDirectory,
  `.api-schema-input-${process.pid}.yaml`,
);

async function main() {
  const schemaUrl = process.env.AGRIVANTA_OPENAPI_URL;
  let schema;
  if (schemaUrl) {
    const response = await fetch(schemaUrl);
    if (!response.ok) {
      throw new Error(
        `Could not download OpenAPI schema (${response.status} ${response.statusText}).`,
      );
    }
    schema = await response.text();
  } else {
    schema = await readFile(localSchema, 'utf8');
  }

  const lines = schema.split(/\r?\n/);
  const chatPathStart = lines.indexOf('  /chat:');
  if (chatPathStart !== -1) {
    const chatPathEnd = lines.findIndex(
      (line, index) =>
        index > chatPathStart &&
        (line.startsWith('  /') || line === 'components:'),
    );
    if (chatPathEnd === -1) {
      throw new Error('Could not locate the end of the /chat OpenAPI path.');
    }
    lines.splice(chatPathStart, chatPathEnd - chatPathStart);
    schema = lines.join('\n');
  }

  await writeFile(generatedSchema, schema, { encoding: 'utf8', flag: 'wx' });
  try {
    const result = spawnSync(
      process.execPath,
      [
        path.join(
          frontendDirectory,
          'node_modules',
          '@hey-api',
          'openapi-ts',
          'bin',
          'run.js',
        ),
        '-i',
        generatedSchema,
        '-o',
        'src/services/generated',
        '--no-log-file',
      ],
      {
        cwd: frontendDirectory,
        stdio: 'inherit',
      },
    );
    if (result.error) throw result.error;
    if (result.status !== 0) process.exitCode = result.status ?? 1;
  } finally {
    await unlink(generatedSchema);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
