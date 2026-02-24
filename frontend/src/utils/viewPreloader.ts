/**
 * 预加载所有路由视图组件，与 main.ts 中 router 使用相同 import() 路径（Vite 自动去重）。
 * 串行 import 避免 Vite 冷启动时并发请求打满转换管线。
 */
const VIEW_IMPORTS: Array<{ name: string, load: () => Promise<any> }> = [
  { name: 'PanelView', load: () => import('@/views/PanelView.vue') },
  { name: 'MessageView', load: () => import('@/views/MessageView.vue') },
  { name: 'ModelView', load: () => import('@/views/ModelView.vue') },
  { name: 'MemoryView', load: () => import('@/views/MemoryView.vue') },
  { name: 'MindView', load: () => import('@/views/MindView.vue') },
  { name: 'SkillView', load: () => import('@/views/SkillView.vue') },
  { name: 'ConfigView', load: () => import('@/views/ConfigView.vue') },
]

export async function preloadAllViews(
  onProgress?: (loaded: number, total: number) => void,
): Promise<void> {
  const total = VIEW_IMPORTS.length
  for (let i = 0; i < total; i++) {
    const view = VIEW_IMPORTS[i]!
    console.log(`[Preload] 加载 ${view.name} (${i + 1}/${total})...`)
    try {
      await view.load()
    }
    catch (e) {
      console.warn(`[Preload] ${view.name} 加载失败，跳过:`, e)
      // 加载失败不阻塞启动，后续导航时会重新加载
    }
    onProgress?.(i + 1, total)
  }
}
