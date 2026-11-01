import type { CustomLive2DModel } from '@/api/core'
import type { CustomLive2DModelConfig, Model } from '@/utils/config'
import { CONFIG } from '@/utils/config'

export function toCustomLive2DModelConfig(model: CustomLive2DModel): CustomLive2DModelConfig {
  return {
    id: model.id,
    name: model.name,
    source: model.source,
    model_path: model.modelPath,
    file_count: model.fileCount,
    total_bytes: model.totalBytes,
    created_at: model.createdAt,
  }
}

export function applyLive2DModel(model: Model): void {
  CONFIG.value.web_live2d.model = {
    source: model.source,
    x: model.x,
    y: model.y,
    size: model.size,
  }
  CONFIG.value.web_live2d.custom_model_id = null
}

export function applyCustomLive2DModel(model: CustomLive2DModel | CustomLive2DModelConfig): void {
  applyLive2DModel({
    source: model.source,
    x: CONFIG.value.web_live2d.model.x,
    y: CONFIG.value.web_live2d.model.y,
    size: CONFIG.value.web_live2d.model.size,
  })
  CONFIG.value.web_live2d.custom_model_id = model.id
  CONFIG.value.system.active_character = ''
}

export function upsertCustomLive2DModel(model: CustomLive2DModel): CustomLive2DModelConfig {
  const nextModel = toCustomLive2DModelConfig(model)
  const models = CONFIG.value.web_live2d.custom_models
  const index = models.findIndex(item => item.id === nextModel.id)
  if (index >= 0) {
    models[index] = nextModel
  }
  else {
    models.unshift(nextModel)
  }
  return nextModel
}
