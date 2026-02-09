import antfu from '@antfu/eslint-config'

export default antfu({
  ignores: ['**/node_modules/**', '**/dist/**', '**/public/**'],
  rules: {
    'no-console': 'off',
    'vue/singleline-html-element-content-newline': ['warn', {
      ignores: ['template'],
    }],
  },
})
