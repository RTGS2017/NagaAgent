import process from 'node:process'
import vue from '@vitejs/plugin-vue'
import unocss from 'unocss/vite'
import { defineConfig } from 'vite'
import electron from 'vite-plugin-electron/simple'

const isWebOnly = !!process.env.WEB_ONLY

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [
    vue(),
    unocss(),
    !isWebOnly && electron({
      main: {
        entry: 'electron/main.ts',
        vite: {
          build: {
            rollupOptions: {
              // Keep native/electron-side deps as runtime externals.
              // This avoids Rolldown trying to bundle `electron-updater` internals
              // (e.g. its `lodash.isequal` import), which can fail on some installs.
              external: ['electron', 'electron-updater', 'lodash.isequal'],
            },
          },
        },
      },
      preload: {
        input: 'electron/preload.ts',
      },
    }),
  ],
  resolve: { alias: { '@': '/src' } },
})
