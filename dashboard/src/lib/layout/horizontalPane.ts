export interface HorizontalPaneOptions {
  initialRightWidth?: number;
  minWidth?: number;
  gutterWidth?: number;
  onWidthChange?: (width: number) => void;
}

export interface HorizontalPaneController {
  startDrag: () => void;
  stopDrag: () => void;
  handleDrag: (event: MouseEvent) => void;
  getRightWidth: () => number;
}

export function createHorizontalPaneController(
  options: HorizontalPaneOptions = {},
): HorizontalPaneController {
  const minWidth = options.minWidth ?? 200;
  const gutterWidth = options.gutterWidth ?? 10;
  const minX = minWidth;

  let rightWidth = options.initialRightWidth ?? calculateDefaultRightWidth();
  let isDragging = false;

  function calculateDefaultRightWidth(): number {
    if (typeof window === "undefined") {
      return 400;
    }
    return Math.max(minWidth, window.innerWidth * 0.35);
  }

  function startDrag(): void {
    isDragging = true;
    document.body.style.cursor = "col-resize";
  }

  function stopDrag(): void {
    if (!isDragging) {
      return;
    }
    isDragging = false;
    document.body.style.cursor = "";
  }

  function handleDrag(event: MouseEvent): void {
    if (!isDragging || typeof window === "undefined") {
      return;
    }

    const maxX = window.innerWidth - minWidth - gutterWidth;
    const clampedX = Math.min(maxX, Math.max(minX, event.clientX));
    rightWidth = window.innerWidth - clampedX;

    options.onWidthChange?.(rightWidth);
  }

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
