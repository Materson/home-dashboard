/**
 * Money amount field used by every form.
 *
 * - Empty by default (the "0,00" is only a placeholder), so you can click
 *   and type straight away.
 * - Focusing selects the whole value, so a pre-filled amount (edit,
 *   duplicate, bookmark) is replaced by typing instead of appended to.
 * - Both "," and "." work as the decimal separator while typing; amounts
 *   are shown with the UI language's separator ("12,50" in Polish).
 * - `value` / `onChange` speak the API's format: a dot-decimal string
 *   ("12.50", "" when empty). The text as typed is kept locally, so
 *   in-progress input like "12," isn't rewritten mid-keystroke.
 */
import { useEffect, useRef, useState } from "react";
import { NumberInput, type NumberInputProps } from "@mantine/core";
import { useTranslation } from "react-i18next";

type Props = Omit<NumberInputProps, "value" | "onChange"> & {
  value: string;
  onChange: (value: string) => void;
};

/** API string → what NumberInput displays. */
export const toInput = (value: string): number | string => (value.trim() === "" ? "" : Number(value));

/** What NumberInput reports → API string (dot decimal, "" when empty). */
export const toApi = (v: number | string): string =>
  typeof v === "number" ? String(v) : v.replace(/\s/g, "").replace(",", ".");

export function AmountInput({ value, onChange, onFocus, ...rest }: Props) {
  const { i18n } = useTranslation();
  const decimalSeparator = i18n.language.startsWith("pl") ? "," : ".";

  const [typed, setTyped] = useState<number | string>(() => toInput(value));
  const lastEmitted = useRef(value);
  // Only resync when the value changes from outside (form reset / prefill).
  useEffect(() => {
    if (value !== lastEmitted.current) {
      lastEmitted.current = value;
      setTyped(toInput(value));
    }
  }, [value]);

  return (
    <NumberInput
      decimalScale={2}
      min={0}
      allowNegative={false}
      hideControls
      decimalSeparator={decimalSeparator}
      allowedDecimalSeparators={[",", "."]}
      placeholder={`0${decimalSeparator}00`}
      {...rest}
      value={typed}
      onChange={(v) => {
        setTyped(v);
        const api = toApi(v);
        lastEmitted.current = api;
        onChange(api);
      }}
      onFocus={(e) => {
        e.currentTarget.select();
        onFocus?.(e);
      }}
    />
  );
}

/** True when the string is a usable positive amount. */
export function isPositiveAmount(value: string): boolean {
  return value.trim() !== "" && Number(value) > 0;
}
