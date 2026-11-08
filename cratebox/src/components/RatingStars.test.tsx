import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RatingStars } from "@/components/RatingStars";

describe("RatingStars", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("sets the clicked rating", () => {
    const onChange = vi.fn();
    act(() => root.render(<RatingStars rating={2} onChange={onChange} />));

    act(() => container.querySelector<HTMLButtonElement>('[aria-label="Set rating to 4 stars"]')?.click());

    expect(onChange).toHaveBeenCalledWith(4);
  });

  it("clears the rating when the active star is clicked again", () => {
    const onChange = vi.fn();
    act(() => root.render(<RatingStars rating={3} onChange={onChange} />));

    act(() => container.querySelector<HTMLButtonElement>('[aria-label="Set rating to 3 stars"]')?.click());

    expect(onChange).toHaveBeenCalledWith(0);
  });
});
