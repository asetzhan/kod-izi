import { describe, expect, it } from "vitest";

import kk from "./kk.json";
import ru from "./ru.json";

function keys(tree: object, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === "object" && value !== null
      ? keys(value as object, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  );
}

describe("sec13 interface languages", () => {
  it("sec13: kk and ru translation files have the same keys", () => {
    expect(keys(ru).sort()).toEqual(keys(kk).sort());
  });

  it("sec13: no translation is empty", () => {
    for (const tree of [kk, ru]) {
      const values = keys(tree).map((path) =>
        path.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown>)[part], tree),
      );
      expect(values.every((value) => typeof value === "string" && value.trim() !== "")).toBe(true);
    }
  });
});
