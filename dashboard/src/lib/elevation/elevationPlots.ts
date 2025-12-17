/**
 * Utilities for constructing and managing uPlot elevation visualisations.
 */
import type uPlot from "uplot";

export interface ElevationPlotManagerElements {
  container: HTMLElement | null;
  elevationPlot: HTMLElement | null;
  differencePlot: HTMLElement | null;
  warningBanner?: HTMLElement | null;
}

export interface ElevationPlotManagerOptions extends ElevationPlotManagerElements {
  onCursorMove?: (index: number | null) => void;
  createPlot: (
    element: HTMLElement,
    config: uPlot.Options,
    data: uPlot.AlignedData,
  ) => uPlot;
}

const ELEVATION_MARGIN = 5;
const DIFFERENCE_MARGIN = 2;
const PADDING: [number, number, number, number] = [8, 8, 0, 0];

/**
 * Build an elevation plot manager responsible for initialising, updating and disposing charts.
 * @param options DOM references and callbacks required to drive the plots.
 * @returns A manager exposing lifecycle and update helpers.
 */
export class ElevationPlotManager {
  private elevationPlot: uPlot | null = null;
  private differencePlot: uPlot | null = null;
  private readonly options: ElevationPlotManagerOptions;

  constructor(options: ElevationPlotManagerOptions) {
    this.options = options;
  }

  /** Tear down any instantiated charts to keep uPlot resource usage in check. */
  destroy(): void {
    this.elevationPlot?.destroy();
    this.differencePlot?.destroy();
    this.elevationPlot = null;
    this.differencePlot = null;
  }

  /**
   * Compute the current chart dimensions based on the container width.
   * @returns The width and height to apply to each plot.
   */
  private getDimensions(): { width: number; height: number } {
    const width = this.options.container?.clientWidth ?? 300;
    const height = Math.round(width * 2 / 3);
    return { width, height };
  }

  /** Lazily instantiate the charts once the required DOM mounts exist. */
  private ensureInitialized(): void {
    if (!this.options.elevationPlot || !this.options.differencePlot) {
      return;
    }

    if (!this.elevationPlot) {
      const { width, height } = this.getDimensions();
      this.elevationPlot = this.options.createPlot(
        this.options.elevationPlot,
        {
          width,
          height,
          series: [
            { label: "distance" },
            { label: "2013 elevation", stroke: "#ff7f0e" },
            { label: "2022 elevation", stroke: "#1f77b4" },
          ],
          axes: [
            { label: "distance along curve (meters)", labelFont: "12px Arial", size: 40 },
            { label: "elevation (meters)", labelFont: "12px Arial", size: 50 },
          ],
          scales: { x: { time: false } },
          padding: PADDING,
          cursor: { show: true },
          hooks: {
            setCursor: [
              (u) => {
                this.options.onCursorMove?.(u.cursor.idx ?? null);
              },
            ],
          },
        },
        [[], [], []],
      );
    }

    if (!this.differencePlot) {
      const { width, height } = this.getDimensions();
      this.differencePlot = this.options.createPlot(
        this.options.differencePlot,
        {
          width,
          height,
          series: [
            { label: "distance" },
            { label: "elevation difference", stroke: "#2ca02c" },
          ],
          axes: [
            { label: "distance along curve (meters)", labelFont: "12px Arial", size: 40 },
            { label: "2022 minus 2013 (meters)", labelFont: "12px Arial", size: 50 },
          ],
          scales: { x: { time: false } },
          padding: PADDING,
          cursor: { show: true },
          hooks: {
            setCursor: [
              (u) => {
                this.options.onCursorMove?.(u.cursor.idx ?? null);
              },
            ],
          },
        },
        [[], []],
      );
    }
  }

  /** Resize plots when the available width changes. */
  resize(): void {
    if (!this.elevationPlot && !this.differencePlot) {
      return;
    }

    const { width, height } = this.getDimensions();

    this.elevationPlot?.setSize({ width, height });
    this.differencePlot?.setSize({ width, height });
  }

  /**
   * Push new data into the plots and keep axes/visibility in sync.
   * @param distances Distance values used for the X axis.
   * @param values2013 Elevation values for the 2013 dataset.
   * @param values2022 Elevation values for the 2022 dataset.
   */
  update(
    distances: number[],
    values2013: Array<number | null>,
    values2022: Array<number | null>,
  ): void {
    this.ensureInitialized();

    if (!this.elevationPlot || !this.options.elevationPlot) {
      return;
    }

    if (!values2013.some(isFiniteNumber) && !values2022.some(isFiniteNumber)) {
      hideElement(this.options.elevationPlot);
      if (this.differencePlot && this.options.differencePlot) {
        hideElement(this.options.differencePlot);
      }
      return;
    }

    showElement(this.options.elevationPlot);
    const [elevationLow, elevationHigh] = percentileRange(
      [...values2013, ...values2022],
      0.05,
    );
    this.elevationPlot.setData([distances, values2013, values2022]);
    this.elevationPlot.setScale("x", { min: 0, max: distances[distances.length - 1] ?? 0 });
    this.elevationPlot.setScale("y", {
      min: elevationLow - ELEVATION_MARGIN,
      max: elevationHigh + ELEVATION_MARGIN,
    });

    if (!this.differencePlot || !this.options.differencePlot) {
      return;
    }

    const difference = values2022.map((value2022, index) => {
      const value2013 = values2013[index];
      if (value2022 === null || value2013 === null) {
        return null;
      }
      return value2022 - value2013;
    });

    if (!difference.some(isFiniteNumber)) {
      hideElement(this.options.differencePlot);
      return;
    }

    showElement(this.options.differencePlot);
    const [differenceLow, differenceHigh] = percentileRange(difference, 0.02);
    this.differencePlot.setData([distances, difference]);
    this.differencePlot.setScale("x", { min: 0, max: distances[distances.length - 1] ?? 0 });
    this.differencePlot.setScale("y", {
      min: differenceLow - DIFFERENCE_MARGIN,
      max: differenceHigh + DIFFERENCE_MARGIN,
    });
  }

  /**
   * Toggle the warning banner that indicates the drawn line exceeded safe tile limits.
   * @param tooLong Whether the line length should be considered invalid.
   */
  setLineTooLong(tooLong: boolean): void {
    if (!this.options.warningBanner) {
      return;
    }
    this.options.warningBanner.style.display = tooLong ? "block" : "none";
    if (tooLong) {
      if (this.options.elevationPlot) {
        hideElement(this.options.elevationPlot);
      }
      if (this.options.differencePlot) {
        hideElement(this.options.differencePlot);
      }
    }
  }

  /** Reset and initialise plots in one call, primarily for component mount. */
  initialize(): void {
    this.destroy();
    this.ensureInitialized();
  }

  /**
   * Hide both plots and reset warning state while preserving layout.
   */
  hideAll(): void {
    if (this.options.elevationPlot) {
      hideElement(this.options.elevationPlot);
    }
    if (this.options.differencePlot) {
      hideElement(this.options.differencePlot);
    }
  }
}

/**
 * Hide a plot element without removing it from the DOM.
 * @param element Host element for the chart.
 */
function hideElement(element: HTMLElement): void {
  element.style.visibility = "hidden";
}

/**
 * Make a plot element visible.
 * @param element Host element for the chart.
 */
function showElement(element: HTMLElement): void {
  element.style.visibility = "visible";
}

/**
 * Type guard for filtering finite numeric values from nullable datasets.
 * @param value Candidate value.
 * @returns True when the input is a finite number.
 */
function isFiniteNumber(value: number | null): value is number {
  return value !== null && Number.isFinite(value);
}

/**
 * Calculate the low and high percentile bounds for a dataset.
 * @param data Source values, potentially including nulls.
 * @param p Percentile expressed as a 0-1 fraction.
 * @returns A tuple [low, high] percentile values.
 */
function percentileRange(data: Array<number | null>, p: number): [number, number] {
  const sorted = data
    .filter(isFiniteNumber)
    .sort((a, b) => a - b);

  if (sorted.length === 0) {
    return [0, 0];
  }

  const lowIndex = Math.max(0, Math.ceil((sorted.length - 1) * p));
  const highIndex = Math.max(0, Math.floor((sorted.length - 1) * (1 - p)));

  return [sorted[lowIndex], sorted[highIndex]];
}
