/**
 * Drag across a line chart to pick a span of its points (a time range).
 * Spread ``chartProps`` on a Mantine ``LineChart`` and render ``area`` as its
 * child; ``onSelect(from, to)`` gets the first and last point's index once the
 * drag ends — also outside the chart, so overshooting the edge works. Touch
 * drags work too (Recharts reports them as mouse events). A plain click or
 * tap (one point) selects nothing.
 */
import { useEffect, useRef, useState } from "react";
import { ReferenceArea } from "recharts";

type ChartState = { activeTooltipIndex?: number } | null;
type Drag = { start: number; end: number };

export function useRangeSelect(xValues: string[], onSelect?: (from: number, to: number) => void) {
  const [drag, setDrag] = useState<Drag | null>(null);
  const latest = useRef<Drag | null>(null);
  const select = useRef(onSelect);
  select.current = onSelect;

  const update = (d: Drag | null) => {
    latest.current = d;
    setDrag(d);
  };
  // Ends the drag once: the chart's release and the window's both call it.
  const finish = useRef(() => {
    const d = latest.current;
    if (!d) return;
    update(null);
    if (d.start !== d.end) select.current?.(Math.min(d.start, d.end), Math.max(d.start, d.end));
  }).current;

  const dragging = drag !== null;
  useEffect(() => {
    if (!dragging) return;
    window.addEventListener("mouseup", finish);
    return () => window.removeEventListener("mouseup", finish);
  }, [dragging, finish]);

  if (!onSelect) return { chartProps: {}, area: null };
  const at = (s: ChartState) => s?.activeTooltipIndex;
  return {
    chartProps: {
      // No text selection while dragging; vertical swipes still scroll the page.
      style: { userSelect: "none" as const, cursor: "crosshair", touchAction: "pan-y" },
      lineChartProps: {
        onMouseDown: (s: ChartState) => {
          const i = at(s);
          if (i != null) update({ start: i, end: i });
        },
        onMouseMove: (s: ChartState) => {
          const i = at(s);
          const d = latest.current;
          if (i != null && d && d.end !== i) update({ ...d, end: i });
        },
        onMouseUp: finish,
      },
    },
    area:
      drag && drag.start !== drag.end ? (
        <ReferenceArea
          yAxisId="left" // Mantine's axis id
          x1={xValues[drag.start]}
          x2={xValues[drag.end]}
          fill="var(--mantine-color-blue-5)"
          fillOpacity={0.15}
          stroke="var(--mantine-color-blue-5)"
          strokeOpacity={0.4}
        />
      ) : null,
  };
}
