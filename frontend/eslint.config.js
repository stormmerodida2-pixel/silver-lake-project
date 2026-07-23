import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import eslintConfigPrettier from 'eslint-config-prettier'
import globals from 'globals'

export default [
  {
    ignores: ['dist/**', 'test-results/**', 'playwright-report/**'],
  },
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      // Vue's SFC style guide asks for multi-word component names for real app components,
      // but this project's view components (HomeView, AdminBookingsView, etc.) are pages, not
      // reusable components, and are never referenced as custom elements - the rule doesn't
      // apply to them.
      'vue/multi-word-component-names': 'off',
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }],
      // Several components (e.g. BookingPaymentCollector) intentionally update an object prop's
      // own fields via Object.assign after a save, so the same reference the parent's list holds
      // reflects the fresh server response without extra emit plumbing - only flag replacing the
      // prop binding itself, not mutating its members.
      'vue/no-mutating-props': ['error', { shallowOnly: true }],
    },
  },
  {
    files: ['e2e/**/*.js', 'playwright.config.js'],
    languageOptions: {
      globals: { ...globals.node },
    },
  },
  eslintConfigPrettier,
]
