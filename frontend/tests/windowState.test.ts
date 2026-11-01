import assert from 'node:assert/strict'
import test from 'node:test'
import {
  fitBoundsWithinWorkArea,
  ManualMaximizeController,
  rectanglesEqual,
} from '../electron/modules/windowState.ts'

test('手动最大化保存普通窗口尺寸并覆盖当前显示器工作区', () => {
  const controller = new ManualMaximizeController()
  const normalBounds = { x: 120, y: 80, width: 1280, height: 800 }
  const workArea = { x: 0, y: 0, width: 1920, height: 1040 }

  assert.deepEqual(controller.maximize(normalBounds, workArea), workArea)
  assert.equal(controller.isMaximized(), true)
  assert.deepEqual(controller.getRestoreBounds(), normalBounds)
})

test('重复最大化不会覆盖首次保存的还原尺寸', () => {
  const controller = new ManualMaximizeController()
  const normalBounds = { x: 120, y: 80, width: 1280, height: 800 }
  const workArea = { x: 0, y: 0, width: 1920, height: 1040 }

  controller.maximize(normalBounds, workArea)
  controller.maximize(workArea, workArea)

  assert.deepEqual(controller.restore(workArea), normalBounds)
  assert.equal(controller.isMaximized(), false)
  assert.equal(controller.getRestoreBounds(), null)
})

test('还原时将屏幕外窗口完整收回带负坐标的显示器工作区', () => {
  const bounds = { x: -2800, y: -200, width: 1400, height: 1000 }
  const workArea = { x: -1920, y: 0, width: 1920, height: 1040 }

  assert.deepEqual(fitBoundsWithinWorkArea(bounds, workArea), {
    x: -1920,
    y: 0,
    width: 1400,
    height: 1000,
  })
})

test('过大的窗口会按工作区收缩且矩形比较保持精确', () => {
  const workArea = { x: 1920, y: 0, width: 1600, height: 900 }
  const fitted = fitBoundsWithinWorkArea({ x: 1800, y: -50, width: 2000, height: 1200 }, workArea)

  assert.deepEqual(fitted, workArea)
  assert.equal(rectanglesEqual(fitted, workArea), true)
  assert.equal(rectanglesEqual(fitted, { ...workArea, height: 899 }), false)
})
