export interface WindowRectangle {
  x: number
  y: number
  width: number
  height: number
}

function copyRectangle(rectangle: WindowRectangle): WindowRectangle {
  return { ...rectangle }
}

export function fitBoundsWithinWorkArea(
  bounds: WindowRectangle,
  workArea: WindowRectangle,
): WindowRectangle {
  const width = Math.min(bounds.width, workArea.width)
  const height = Math.min(bounds.height, workArea.height)
  const maxX = workArea.x + workArea.width - width
  const maxY = workArea.y + workArea.height - height

  return {
    x: Math.min(Math.max(bounds.x, workArea.x), maxX),
    y: Math.min(Math.max(bounds.y, workArea.y), maxY),
    width,
    height,
  }
}

export function rectanglesEqual(left: WindowRectangle, right: WindowRectangle): boolean {
  return left.x === right.x
    && left.y === right.y
    && left.width === right.width
    && left.height === right.height
}

export class ManualMaximizeController {
  private maximized = false
  private restoreBounds: WindowRectangle | null = null

  isMaximized(): boolean {
    return this.maximized
  }

  getRestoreBounds(): WindowRectangle | null {
    return this.restoreBounds ? copyRectangle(this.restoreBounds) : null
  }

  maximize(currentBounds: WindowRectangle, workArea: WindowRectangle): WindowRectangle {
    if (!this.maximized) {
      this.restoreBounds = copyRectangle(currentBounds)
    }
    this.maximized = true
    return copyRectangle(workArea)
  }

  restore(fallbackBounds: WindowRectangle): WindowRectangle {
    const targetBounds = this.restoreBounds ?? fallbackBounds
    this.maximized = false
    this.restoreBounds = null
    return copyRectangle(targetBounds)
  }

  reset(): void {
    this.maximized = false
    this.restoreBounds = null
  }
}
