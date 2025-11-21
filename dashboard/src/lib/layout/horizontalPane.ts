/** Controller configuration for maintaining a draggable horizontal pane layout. */
export interface HorizontalPaneOptions {
  initialRightWidth?: number;
  minWidth?: number;
  gutterWidth?: number;
  onWidthChange?: (width: number) => void;
}

/**
 * Create a controller for a resizable horizontal pane splitter.
 * @param options Behaviour overrides and resize callbacks.
 * @returns An imperative controller supporting drag lifecycle hooks.
 */
export class HorizontalPaneController {
  private rightWidth: number;
  private isDragging = false;
  private readonly minWidth: number;
  private readonly gutterWidth: number;
  private readonly minX: number;
  private readonly onWidthChange?: (width: number) => void;

  constructor(options: HorizontalPaneOptions = {}) {
    this.minWidth = options.minWidth ?? 200;
    this.gutterWidth = options.gutterWidth ?? 10;
    this.minX = this.minWidth;
    this.onWidthChange = options.onWidthChange;
    this.rightWidth = options.initialRightWidth ?? this.calculateDefaultRightWidth();
  }

  /** Determine a reasonable starting width for the right pane, clamped to the minimum width. */
  private calculateDefaultRightWidth(): number {
    if (typeof window === "undefined") {
      return 400;
    }
    return Math.max(this.minWidth, window.innerWidth * 0.35);
  }

  /** Begin a drag sequence, switching the cursor to a resize indicator. */
  startDrag(): void {
    this.isDragging = true;
    document.body.style.cursor = "col-resize";
  }

  /** Finish a drag sequence and restore the cursor. */
  stopDrag(): void {
    if (!this.isDragging) {
      return;
    }
    this.isDragging = false;
    document.body.style.cursor = "";
  }

  /**
   * Adjust pane widths while dragging.
   * @param event Pointer movement used to determine the new split position.
   */
  handleDrag(event: PointerEvent): void {
    if (!this.isDragging || typeof window === "undefined") {
      return;
    }

    const maxX = window.innerWidth - this.minWidth - this.gutterWidth;
    const clampedX = Math.min(maxX, Math.max(this.minX, event.clientX));
    this.rightWidth = window.innerWidth - clampedX;

    this.onWidthChange?.(this.rightWidth);
  }

  /**
   * Expose the most recently computed right-hand width.
   * @returns The width to apply to the right pane.
   */
  getRightWidth(): number {
    return this.rightWidth;
  }
}
