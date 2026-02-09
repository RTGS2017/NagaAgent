import { definePreset } from '@primeuix/themes'
import Lara from '@primeuix/themes/lara'
import PrimeVue from 'primevue/config'
import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
import 'virtual:uno.css'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: () => import('@/views/PanelView.vue') },
    { path: '/chat', component: () => import('@/views/MessageView.vue') },
    { path: '/model', component: () => import('@/views/ModelView.vue') },
    { path: '/memory', component: () => import('@/views/MemoryView.vue') },
    { path: '/mind', component: () => import('@/views/MindView.vue') },
    { path: '/skill', component: () => import('@/views/SkillView.vue') },
    { path: '/config', component: () => import('@/views/ConfigView.vue') },
  ],
})

createApp(App)
  .use(PrimeVue, {
    theme: {
      preset: definePreset(Lara),
      options: {
        darkModeSelector: '.p-dark',
      },
    },
  })
  .use(router)
  .mount('#app')
