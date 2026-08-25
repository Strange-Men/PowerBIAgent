import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { FloatingActionMenu } from './FloatingActionMenu'

function rect(top: number, bottom: number, left = 180, right = 220) {
  return {
    x: left,
    y: top,
    top,
    bottom,
    left,
    right,
    width: right - left,
    height: bottom - top,
    toJSON: () => ({}),
  } as DOMRect
}

function Fixture() {
  const [open, setOpen] = useState(false)
  return (
    <div data-testid="overflow-parent" style={{ overflow: 'hidden' }}>
      <FloatingActionMenu
        label="管理对话：测试"
        open={open}
        onOpenChange={setOpen}
      >
        <button type="button" role="menuitem">重命名</button>
        <button type="button" role="menuitem">归档</button>
        <button type="button" role="menuitem">删除</button>
      </FloatingActionMenu>
    </div>
  )
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('FloatingActionMenu', () => {
  it('portals below a top or middle trigger outside overflow containers', () => {
    render(<Fixture />)
    const trigger = screen.getByRole('button', { name: '管理对话：测试' })
    Object.defineProperty(trigger, 'getBoundingClientRect', {
      value: () => rect(80, 110),
    })
    vi.spyOn(HTMLDivElement.prototype, 'getBoundingClientRect').mockReturnValue(
      rect(0, 120, 0, 148),
    )

    fireEvent.click(trigger)

    const menu = screen.getByRole('menu')
    expect(menu.parentElement).toBe(document.body)
    expect(menu).toHaveAttribute('data-placement', 'below')
    expect(menu.style.top).toBe('116px')
  })

  it('portals above a bottom trigger and clamps inside the viewport', () => {
    vi.stubGlobal('innerHeight', 300)
    vi.stubGlobal('innerWidth', 260)
    render(<Fixture />)
    const trigger = screen.getByRole('button', { name: '管理对话：测试' })
    Object.defineProperty(trigger, 'getBoundingClientRect', {
      value: () => rect(270, 294, 238, 258),
    })
    vi.spyOn(HTMLDivElement.prototype, 'getBoundingClientRect').mockReturnValue(
      rect(0, 120, 0, 148),
    )

    fireEvent.click(trigger)

    const menu = screen.getByRole('menu')
    expect(menu).toHaveAttribute('data-placement', 'above')
    expect(menu.style.top).toBe('144px')
    expect(menu.style.left).toBe('104px')
  })

  it('closes on outside pointer and Escape while restoring trigger focus', () => {
    render(<Fixture />)
    const trigger = screen.getByRole('button', { name: '管理对话：测试' })
    fireEvent.click(trigger)
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()

    fireEvent.click(trigger)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })
})
