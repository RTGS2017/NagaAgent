import { computed } from 'vue'
import { pX, pY } from '@/utils/parallax'

interface ParallaxOptions {
  /** Max rotateX in degrees (tilt up/down) */
  rotateX?: number
  /** Max rotateY in degrees (tilt left/right) */
  rotateY?: number
  /** Max translateX in px */
  translateX?: number
  /** Max translateY in px */
  translateY?: number
  /** Reverse direction (for background layers) */
  invert?: boolean
  /** Reverse tilt only: mouse left -> component tilts right */
  invertRotate?: boolean
  /** CSS perspective value */
  perspective?: number
}

export function useParallax(opts: ParallaxOptions = {}) {
  const {
    rotateX = 0,
    rotateY = 0,
    translateX = 0,
    translateY = 0,
    invert = false,
    invertRotate = false,
    perspective = 1000,
  } = opts

  const sign = invert ? -1 : 1
  const rotateSign = invertRotate ? -1 : 1

  const rx = computed(() => +(pY.value * rotateX * sign * rotateSign).toFixed(3))
  const ry = computed(() => +(pX.value * rotateY * sign * rotateSign).toFixed(3))
  const tx = computed(() => +(pX.value * translateX * sign).toFixed(2))
  const ty = computed(() => +(pY.value * translateY * sign).toFixed(2))

  const transform = computed(() => {
    const parts: string[] = []
    if (perspective)
      parts.push(`perspective(${perspective}px)`)
    if (rotateX)
      parts.push(`rotateX(${rx.value}deg)`)
    if (rotateY)
      parts.push(`rotateY(${ry.value}deg)`)
    if (translateX || translateY)
      parts.push(`translate(${tx.value}px, ${ty.value}px)`)
    return parts.join(' ')
  })

  return { rx, ry, tx, ty, transform }
}
