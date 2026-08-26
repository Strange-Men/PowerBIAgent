import type { ReactNode } from 'react'
import { useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

const VIEWPORT_MARGIN = 8
const TRIGGER_GAP = 6

interface FloatingActionMenuProps {
  anchor: HTMLElement
  ariaLabel: string
  children: ReactNode
  onClose: () => void
}

interface MenuPosition {
  left: number
  placement: 'above' | 'below'
  top: number
  visible: boolean
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), Math.max(minimum, maximum))
}

export function FloatingActionMenu({
  anchor,
  ariaLabel,
  children,
  onClose,
}: FloatingActionMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState<MenuPosition>({
    left: VIEWPORT_MARGIN,
    placement: 'below',
    top: VIEWPORT_MARGIN,
    visible: false,
  })

  useLayoutEffect(() => {
    const menu = menuRef.current
    if (!menu) return

    const updatePosition = () => {
      const triggerRect = anchor.getBoundingClientRect()
      const menuRect = menu.getBoundingClientRect()
      const fitsBelow =
        triggerRect.bottom + TRIGGER_GAP + menuRect.height <=
        window.innerHeight - VIEWPORT_MARGIN
      const placement = fitsBelow ? 'below' : 'above'
      const preferredTop = fitsBelow
        ? triggerRect.bottom + TRIGGER_GAP
        : triggerRect.top - TRIGGER_GAP - menuRect.height
      const preferredLeft = triggerRect.right - menuRect.width

      setPosition({
        left: clamp(
          preferredLeft,
          VIEWPORT_MARGIN,
          window.innerWidth - menuRect.width - VIEWPORT_MARGIN,
        ),
        placement,
        top: clamp(
          preferredTop,
          VIEWPORT_MARGIN,
          window.innerHeight - menuRect.height - VIEWPORT_MARGIN,
        ),
        visible: true,
      })
    }

    const closeOnOutsidePointer = (event: MouseEvent) => {
      const target = event.target
      if (
        target instanceof Node &&
        !menu.contains(target) &&
        !anchor.contains(target)
      ) {
        onClose()
      }
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      onClose()
    }

    updatePosition()
    const firstMenuItem = menu.querySelector<HTMLElement>(
      '[role="menuitem"]:not([disabled])',
    )
    firstMenuItem?.focus()

    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)
    document.addEventListener('scroll', updatePosition, true)
    document.addEventListener('mousedown', closeOnOutsidePointer)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition, true)
      document.removeEventListener('scroll', updatePosition, true)
      document.removeEventListener('mousedown', closeOnOutsidePointer)
      document.removeEventListener('keydown', closeOnEscape)
      if (document.contains(anchor)) anchor.focus()
    }
  }, [anchor, onClose])

  return createPortal(
    <div
      ref={menuRef}
      className="floating-action-menu"
      data-placement={position.placement}
      role="menu"
      aria-label={ariaLabel}
      style={{
        left: position.left,
        top: position.top,
        visibility: position.visible ? 'visible' : 'hidden',
      }}
    >
      {children}
    </div>,
    document.body,
  )
}
