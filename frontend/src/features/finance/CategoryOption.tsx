/** Dropdown row for a category picker: sub-categories indented under their main one. */
import { type ComboboxItem, type ComboboxLikeRenderOptionInput, Text } from "@mantine/core";

import { PATH_SEP } from "./categoryTree";

export function renderCategoryOption({ option }: ComboboxLikeRenderOptionInput<ComboboxItem>) {
  const [main, sub] = option.label.split(PATH_SEP);
  return sub === undefined ? (
    <Text size="sm" fw={500}>
      {main}
    </Text>
  ) : (
    <Text size="sm" pl="md">
      {sub}
    </Text>
  );
}
