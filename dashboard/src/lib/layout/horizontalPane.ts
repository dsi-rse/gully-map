/** Controller configuration for maintaining a draggable horizontal pane layout. */
export interface HorizontalPaneOptions {
  initialRightWidth?: number;
  minWidth?: number;
  gutterWidth?: number;
  onWidthChange?: (width: number) => void;
}

/** Contract returned for imperatively driving the pane sizing behaviour. */
export interface HorizontalPaneController {
  startDrag: () => void;
  stopDrag: () => void;
  handleDrag: (event: PointerEvent) => void;
  getRightWidth: () => number;
}

/**
 * Create a controller for a resizable horizontal pane splitter.
 * @param options Behaviour overrides and resize callbacks.
 * @returns An imperative controller supporting drag lifecycle hooks.
 */
export function createHorizontalPaneController(
  options: HorizontalPaneOptions = {},
): HorizontalPaneController {
  const minWidth = options.minWidth ?? 200;
  const gutterWidth = options.gutterWidth ?? 10;
  const minX = minWidth;

  let rightWidth = options.initialRightWidth ?? calculateDefaultRightWidth();
  let isDragging = false;

  /**
   * Determine a reasonable starting width for the right pane, clamped to the minimum width.
   * @returns The starting width in pixels.
   */
  function calculateDefaultRightWidth(): number {
    if (typeof window === "undefined") {
      return 400;
    }
    return Math.max(minWidth, window.innerWidth * 0.35);
  }

  /** Begin a drag sequence, switching the cursor to a resize indicator. */
  function startDrag(): void {
    isDragging = true;
    document.body.style.cursor = "col-resize";
  }

  /** Finish a drag sequence and restore the cursor. */
  function stopDrag(): void {
    if (!isDragging) {
      return;
    }
    isDragging = false;
    document.body.style.cursor = "";
  }

  /**
   * Adjust pane widths while dragging.
   * @param event Pointer movement used to determine the new split position.
   */
  function handleDrag(event: PointerEvent): void {
    if (!isDragging || typeof window === "undefined") {
      return;
    }

    const maxX = window.innerWidth - minWidth - gutterWidth;
    const clampedX = Math.min(maxX, Math.max(minX, event.clientX));
    rightWidth = window.innerWidth - clampedX;

    options.onWidthChange?.(rightWidth);
  }

  /**
   * Expose the most recently computed right-hand width.
   * @returns The width to apply to the right pane.
   */
  function getRightWidth(): number {
    return rightWidth;
  }

  return {
    startDrag,
    stopDrag,
    handleDrag,
    getRightWidth,
  };
}
