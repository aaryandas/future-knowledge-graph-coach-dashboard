class ChartResizeObserver implements ResizeObserver {
  constructor(private readonly callback: ResizeObserverCallback) {}

  disconnect(): void {}

  observe(target: Element): void {
    this.callback(
      [
        {
          target,
          contentRect: new DOMRectReadOnly(0, 0, 420, 188),
          borderBoxSize: [],
          contentBoxSize: [],
          devicePixelContentBoxSize: [],
        },
      ],
      this,
    );
  }

  unobserve(): void {}
}

globalThis.ResizeObserver = ChartResizeObserver;

Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
  configurable: true,
  value(this: HTMLElement) {
    if (this.classList.contains("recharts-legend-wrapper")) {
      return new DOMRect(0, 0, 420, 20);
    }
    if (
      this.classList.contains("recharts-responsive-container") ||
      this.classList.contains("copilot-chart-canvas")
    ) {
      return new DOMRect(0, 0, 420, 188);
    }
    return new DOMRect();
  },
});

Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  value: () => undefined,
});
