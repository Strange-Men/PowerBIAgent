import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import { MoreHorizontal } from 'lucide-react'

const VIEWPORT_MARGIN = 8
const MENU_GAP = 6

interface FloatingActionMenuProps {
  label: string
  open: boolean
  onOpenChange: (open: boolean) => void
  children: ReactNode
}

interface MenuPosition {
  left: number
  top: number
  visibility: 'hidden' | 'visible'
}

export function FloatingActionMenu({
  label,
  open,
  onOpenChange,
  children,
}: FloatingActionMenuProps) {
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState<MenuPosition>({
    left: VIEWPORT_MARGIN,
    top: VIEWPORT_MARGIN,
    visibility: 'hidden',
  })
  const [placement, setPlacement] = useState<'above' | 'below'>('below')

  useLayoutEffect(() => {
    if (!open) return
    const updatePosition = () => {
      const trigger = triggerRef.current
      const menu = menuRef.current
      if (!trigger || !menu) return
      const triggerRect = trigger.getBoundingClientRect()
      const menuRect = menu.getBoundingClientRect()
      const width = menuRect.width || 148
      const height = menuRect.height || 120
      const viewportWidth = document.documentElement.clientWidth || window.innerWidth
      const viewportHeight = document.documentElement.clientHeight || window.innerHeight
      const belowTop = triggerRect.bottom + MENU_GAP
      const fitsBelow = belowTop + height <= viewportHeight - VIEWPORT_MARGIN
      const nextPlacement = fitsBelow ? 'below' : 'above'
      const rawTop = fitsBelow
        ? belowTop
        : triggerRect.top - MENU_GAP - height
      setPlacement(nextPlacement)
      setPosition({
        left: Math.max(
          VIEWPORT_MARGIN,
          Math.min(triggerRect.right - width, viewportWidth - width - VIEWPORT_MARGIN),
        ),
        top: Math.max(
          VIEWPORT_MARGIN,
          Math.min(rawTop, viewportHeight - height - VIEWPORT_MARGIN),
        ),
        visibility: 'visible',
      })
    }

    updatePosition()
    window.addEventListener('resize', updatePosition)
    window.addEventListener('scroll', updatePosition, true)
    const frame = window.requestAnimationFrame(() => {
      menuRef.current
        ?.querySelector<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')
        ?.focus()
    })
    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener('resize', updatePosition)
      window.removeEventListener('scroll', updatePosition, true)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const closeOutside = (event: PointerEvent) => {
      const target = event.target
      if (!(target instanceof Node)) return
      if (
        !triggerRef.current?.contains(target) &&
        !menuRef.current?.contains(target)
      ) {
        onOpenChange(false)
      }
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      onOpenChange(false)
      triggerRef.current?.focus()
    }
    document.addEventListener('pointerdown', closeOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOutside)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [onOpenChange, open])

  return (
    <>
      <button
        ref={triggerRef}
        className="conversation-actions-trigger"
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => onOpenChange(!open)}
      >
        <MoreHorizontal size={17} />
      </button>
      {open
        ? createPortal(
            <div
              ref={menuRef}
              className="floating-action-menu"
              data-placement={placement}
              role="menu"
              aria-label={label.replace(/^管理/, '').replace('：', '操作：')}
              style={position}
            >
              {children}
            </div>,
            document.body,
          )
        : null}
    </>
  )
}
