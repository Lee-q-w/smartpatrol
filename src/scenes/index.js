// ============================================================
// 场景注册表 —— 内置场景 + 自建场景（localStorage）管理
// ============================================================
import { PARK_SCENE } from './park.js'
import { validateScene } from './sceneSchema.js'

export { PARK_SCENE } from './park.js'
export { WAREHOUSE_SCENE } from './warehouse.js'
export * from './sceneSchema.js'

import { WAREHOUSE_SCENE } from './warehouse.js'

/** 内置场景（顺序即选择器显示顺序） */
export const BUILTIN_SCENES = [PARK_SCENE, WAREHOUSE_SCENE]

const LS_KEY = 'smartpatrol-custom-scenes'

/** 读取自建场景列表（编辑器保存用） */
export function loadCustomScenes() {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (!raw) return []
    const list = JSON.parse(raw)
    return Array.isArray(list) ? list.filter(s => validateScene(s).length === 0) : []
  } catch {
    return []
  }
}

/** 保存/更新一个自建场景（按 id 覆盖） */
export function saveCustomScene(scene) {
  const errs = validateScene(scene)
  if (errs.length) throw new Error('场景数据不合法：' + errs.join('；'))
  const list = loadCustomScenes().filter(s => s.id !== scene.id)
  list.push(scene)
  localStorage.setItem(LS_KEY, JSON.stringify(list))
  return scene
}

/** 删除自建场景 */
export function deleteCustomScene(sceneId) {
  const list = loadCustomScenes().filter(s => s.id !== sceneId)
  localStorage.setItem(LS_KEY, JSON.stringify(list))
}

/** 合并内置 + 自建（供场景选择器；同 id 时内置优先） */
export function allScenes() {
  const builtinIds = new Set(BUILTIN_SCENES.map(s => s.id))
  return [...BUILTIN_SCENES, ...loadCustomScenes().filter(s => !builtinIds.has(s.id))]
}
