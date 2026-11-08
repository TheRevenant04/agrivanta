import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';
import prettier from 'eslint-config-prettier';

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'node_modules', 'src/services/generated'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      ...tseslint.configs.recommended,
      reactHooks.configs.flat['recommended-latest'],
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
  },
  {
    // Only the services layer may talk to the backend. Everything else must
    // go through `useServices()` so both implementations stay interchangeable.
    files: ['src/**/*.{ts,tsx}'],
    ignores: ['src/services/**'],
    rules: {
      'no-restricted-globals': [
        'error',
        {
          name: 'fetch',
          message: 'Call the typed services layer instead of fetch directly.',
        },
        {
          name: 'XMLHttpRequest',
          message:
            'Call the typed services layer instead of XMLHttpRequest directly.',
        },
      ],
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: 'axios',
              message:
                'Call the typed services layer instead of axios directly.',
            },
          ],
        },
      ],
      'no-restricted-syntax': [
        'error',
        {
          selector: "NewExpression[callee.name='XMLHttpRequest']",
          message:
            'Call the typed services layer instead of XMLHttpRequest directly.',
        },
      ],
    },
  },
  prettier,
);
