/**
 * A tab-like switch (a view, a filter, a period): a row of options on wider
 * screens, a dropdown on phones — where a row of more than a few options
 * doesn't fit the screen.
 */
import type { CSSProperties } from "react";
import { type MantineSize, SegmentedControl, Select } from "@mantine/core";

export function ChoiceTabs<T extends string>(props: {
  value: T;
  onChange: (value: T) => void;
  data: { value: T; label: string }[];
  /** Names the dropdown for screen readers (it has no visible label). */
  label: string;
  size?: MantineSize;
  /** The row's style (wider screens). */
  style?: CSSProperties;
  /** The dropdown's width (phones). */
  selectWidth?: string | number;
}) {
  return (
    <>
      <SegmentedControl
        visibleFrom="sm"
        size={props.size}
        value={props.value}
        onChange={(v) => props.onChange(v as T)}
        data={props.data}
        style={props.style}
      />
      <Select
        hiddenFrom="sm"
        size={props.size}
        w={props.selectWidth}
        aria-label={props.label}
        value={props.value}
        onChange={(v) => v && props.onChange(v as T)}
        data={props.data}
        allowDeselect={false}
      />
    </>
  );
}
