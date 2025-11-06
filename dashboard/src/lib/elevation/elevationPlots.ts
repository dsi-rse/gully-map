import type uPlot from "uplot";

export interface ElevationPlotManagerElements {
  container: HTMLElement | null;
  elevationPlot: HTMLElement | null;
  differencePlot: HTMLElement | null;
  warningBanner?: HTMLElement | null;
}

export interface ElevationPlotManager {
  initialize: () => void;
  resize: () => void;
  update: (
    distances: number[],
    values2013: Array<number | null>,
    values2022: Array<number | null>,
  ) => void;
  setLineTooLong: (tooLong: boolean) => void;
  destroy: () => void;
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

export function createElevationPlotManager(
  options: ElevationPlotManagerOptions,
): ElevationPlotManager {
  let elevationPlot: uPlot | null = null;
  let differencePlot: uPlot | null = null;

  function destroy(): void {
    elevationPlot?.destroy();
    differencePlot?.destroy();
    elevationPlot = null;
    differencePlot = null;
  }

  function getDimensions(): { width: number; height: number } {
    const width = options.container?.clientWidth ?? 300;
    const height = Math.round(width * 2 / 3);
    return { width, height };
  }

  function ensureInitialized(): void {
    if (!options.elevationPlot || !options.differencePlot) {
      return;
    }

    if (!elevationPlot) {
      const { width, height } = getDimensions();
      elevationPlot = options.createPlot(
        options.elevationPlot,
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
                options.onCursorMove?.(u.cursor.idx ?? null);
              },
            ],
          },
        },
        [[], [], []],
      );
    }

    if (!differencePlot) {
      const { width, height } = getDimensions();
      differencePlot = options.createPlot(
        options.differencePlot,
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
                options.onCursorMove?.(u.cursor.idx ?? null);
              },
            ],
          },
        },
        [[], []],
      );
    }
  }

  function resize(): void {
    if (!elevationPlot && !differencePlot) {
      return;
    }

    const { width, height } = getDimensions();

    elevationPlot?.setSize({ width, height });
    differencePlot?.setSize({ width, height });
  }

  function update(
    distances: number[],
    values2013: Array<number | null>,
    values2022: Array<number | null>,
  ): void {
    ensureInitialized();

    if (!elevationPlot || !options.elevationPlot) {
      return;
    }

    if (!values2013.some(isFiniteNumber) && !values2022.some(isFiniteNumber)) {
      hideElement(options.elevationPlot);
      if (differencePlot && options.differencePlot) {
        hideElement(options.differencePlot);
      }
      return;
    }

    showElement(options.elevationPlot);
    const [elevationLow, elevationHigh] = percentileRange(
      [...values2013, ...values2022],
      0.05,
    );
    elevationPlot.setData([distances, values2013, values2022]);
    elevationPlot.setScale("x", { min: 0, max: distances[distances.length - 1] ?? 0 });
    elevationPlot.setScale("y", {
      min: elevationLow - ELEVATION_MARGIN,
      max: elevationHigh + ELEVATION_MARGIN,
    });

    if (!differencePlot || !options.differencePlot) {
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
      hideElement(options.differencePlot);
      return;
    }

    showElement(options.differencePlot);
    const [differenceLow, differenceHigh] = percentileRange(difference, 0.05);
    differencePlot.setData([distances, difference]);
    differencePlot.setScale("x", { min: 0, max: distances[distances.length - 1] ?? 0 });
    differencePlot.setScale("y", {
      min: differenceLow - DIFFERENCE_MARGIN,
      max: differenceHigh + DIFFERENCE_MARGIN,
    });
  }

  function setLineTooLong(tooLong: boolean): void {
    if (!options.warningBanner) {
      return;
    }
    options.warningBanner.style.display = tooLong ? "block" : "none";
  }

  function initialize(): void {
    destroy();
    ensureInitialized();
  }

  return {
    initialize,
    resize,
    update,
    setLineTooLong,
    destroy,
  };
}

function hideElement(element: HTMLElement): void {
  element.style.visibility = "hidden";
}

function showElement(element: HTMLElement): void {
  element.style.visibility = "visible";
}

function isFiniteNumber(value: number | null): value is number {
  return value !== null && Number.isFinite(value);
}

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
