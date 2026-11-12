import { useEffect, useRef, useState } from "react";
import { TextInput } from "@mantine/core";
import { useTranslation } from "react-i18next";

import { normalizeTime } from "@/components/records/fields";

/**
 * 24-hour time entry. Free typing ("8", "830", "14.30") is tidied to "HH:MM"
 * on blur; until then an unparseable value keeps the form unsaveable.
 */
export function TimeField(props: {
  label: string;
  required?: boolean;
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState(props.value);
  // What we last sent up. The form stores the tidied "01:00" while the user
  // has typed only "1" — that echo must not overwrite what they're typing.
  const lastEmitted = useRef(props.value);
  useEffect(() => {
    if (props.value !== lastEmitted.current) {
      lastEmitted.current = props.value;
      setText(props.value);
    }
  }, [props.value]);
  const invalid = text.trim() !== "" && normalizeTime(text) === null;
  return (
    <TextInput
      label={props.label}
      required={props.required}
      placeholder="14:30"
      maxLength={5}
      inputMode="numeric"
      value={text}
      error={invalid ? t("common.badTime") : undefined}
      onChange={(e) => {
        const raw = e.currentTarget.value;
        setText(raw);
        const next = normalizeTime(raw) ?? raw;
        lastEmitted.current = next;
        props.onChange(next);
      }}
      onBlur={() => {
        const tidy = normalizeTime(text);
        if (tidy) setText(tidy);
      }}
      onFocus={(e) => e.currentTarget.select()}
    />
  );
}
