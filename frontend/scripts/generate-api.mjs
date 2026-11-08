import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { unlink, writeFile } from 'node:fs/promises';

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
const downloadedSchema = path.join(
  frontendDirectory,
  `.api-schema-input-${process.pid}.yaml`,
);
const defaultSchemaUrl = 'http://localhost:8000/openapi.yaml';

async function main() {
  let input = localSchema;
  let removeDownloadedSchema = false;
  const schemaUrl = process.env.AGRIVANTA_OPENAPI_URL ?? defaultSchemaUrl;

  try {
    const response = await fetch(schemaUrl, {
      signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) {
      throw new Error(
        `Could not download OpenAPI schema (${response.status} ${response.statusText}).`,
      );
    }
    await writeFile(downloadedSchema, await response.text(), {
      encoding: 'utf8',
      flag: 'wx',
    });
    input = downloadedSchema;
    removeDownloadedSchema = true;
  } catch (error) {
    if (process.env.AGRIVANTA_OPENAPI_URL) throw error;
    console.warn(
      `Could not reach ${defaultSchemaUrl}; generating from the checked-in backend schema.`,
    );
  }

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
        input,
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
    if (removeDownloadedSchema) await unlink(downloadedSchema);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
