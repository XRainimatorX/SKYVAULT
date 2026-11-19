"use client";

import { useEffect, useRef } from "react";
import type { EChartsOption } from "echarts";

/** One ECharts chart; re-rendered when option changes, resized with its box. */
export default function Chart({ option, height = 280, label }: {
  option: EChartsOption;
  height?: number;
  label: string;
}) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = box.current;
    if (!element) return;
    let disposed = false;
    let chart: import("echarts").ECharts | null = null;
    let observer: ResizeObserver | null = null;
    import("echarts").then((echarts) => {
      if (disposed) return;
      chart = echarts.init(element, null, { renderer: "svg" });
      chart.setOption(option);
      observer = new ResizeObserver(() => chart?.resize());
      observer.observe(element);
    });
    return () => {
      disposed = true;
      observer?.disconnect();
      chart?.dispose();
    };
  }, [option]);

  return <div ref={box} role="img" aria-label={label} style={{ width: "100%", height }} />;
}
