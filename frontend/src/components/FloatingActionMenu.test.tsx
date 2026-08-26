import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FloatingActionMenu } from './FloatingActionMenu'

function rect({
  bottom,
  height,
  left,
  right,
  top,
  width,
}: Partial<DOMRect>): DOMRect {
  return {
    bottom: bottom ?? (top ?? 0) + (height ?? 0),
    height: height ?? 0,
    left: left ?? 0,
    right: right ?? (left ?? 0) + (width ?? 0),
    top: top ?? 0,
    width: width ?? 0,
    x: left ?? 0,
    y: top ?? 0,
    toJSON: () => ({}),
  }
}

function Harness() {
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null)
  const [open, setOpen] = useState(false)
  return (
    <div data-testid="scroll-container" style={{ overflow: 'hidden' }}>
      <button type="button" onClick={(event) => {
        setAnchor(event.currentTarget)
        setOpen((value) => !value)
      }}>
        打开操作
      </button>
      {open && anchor ? (
        <FloatingActionMenu
          anchor={anchor}
          ariaLabel="资源操作"
          onClose={() => setOpen(false)}
        >
          <button type="button" role="menuitem">重命名</button>
          <button type="button" role="menuitem">删除</button>
        </FloatingActionMenu>
      ) : null}
    </div>
  )
}

function mockRects(triggerRect: () => DOMRect, menuRect: DOMRect) {
  return vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    return this.getAttribute('role') === 'menu' ? menuRect : triggerRect()
  })
}

afterEach(() => {
  vi.restoreAllMocks()
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 })
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 768 })
})

describe('FloatingActionMenu', () => {
  it('portals below the trigger and outside its clipping container', () => {
    mockRects(
      () => rect({ bottom: 132, height: 32, left: 220, right: 252, top: 100, width: 32 }),
      rect({ height: 120, width: 132 }),
    )
    render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: '打开操作' }))

    const menu = screen.getByRole('menu', { name: '资源操作' })
    expect(menu.parentElement).toBe(document.body)
    expect(menu).toHaveAttribute('data-placement', 'below')
    expect(menu).toHaveStyle({ left: '120px', top: '138px', visibility: 'visible' })
    expect(screen.getByRole('menuitem', { name: '重命名' })).toHaveFocus()
  })

  it('places above near the viewport bottom and clamps to viewport margins', () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 160 })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 600 })
    mockRects(
      () => rect({ bottom: 592, height: 32, left: 4, right: 36, top: 560, width: 32 }),
      rect({ height: 120, width: 132 }),
    )
    render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: '打开操作' }))

    expect(screen.getByRole('menu')).toHaveAttribute('data-placement', 'above')
    expect(screen.getByRole('menu')).toHaveStyle({ left: '8px', top: '434px' })
  })

  it('closes on outside pointer and Escape, restoring focus to the trigger', () => {
    mockRects(
      () => rect({ bottom: 132, height: 32, left: 220, right: 252, top: 100, width: 32 }),
      rect({ height: 120, width: 132 }),
    )
    render(<Harness />)
    const trigger = screen.getByRole('button', { name: '打开操作' })

    fireEvent.click(trigger)
    fireEvent.mouseDown(document.body)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()

    fireEvent.click(trigger)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('repositions when a scroll container moves the trigger', async () => {
    let triggerRect = rect({ bottom: 132, height: 32, left: 220, right: 252, top: 100, width: 32 })
    mockRects(() => triggerRect, rect({ height: 120, width: 132 }))
    render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: '打开操作' }))
    expect(screen.getByRole('menu')).toHaveStyle({ top: '138px' })

    triggerRect = rect({ bottom: 332, height: 32, left: 220, right: 252, top: 300, width: 32 })
    fireEvent.scroll(screen.getByTestId('scroll-container'))
    await waitFor(() => expect(screen.getByRole('menu')).toHaveStyle({ top: '338px' }))
  })
})
