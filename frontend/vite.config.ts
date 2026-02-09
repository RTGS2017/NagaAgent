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
    ...(!isWebOnly
      ? [
          electron({
            main: {
              entry: 'electron/main.ts',
              vite: {
                build: {
                  rollupOptions: {
                    external: ['electron', 'electron-updater'],
                  },
                },
              },
            },
            preload: {
              input: 'electron/preload.ts',
            },
          }),
        ]
      : []),
  ],
  resolve: { alias: { '@': '/src' } },
})
