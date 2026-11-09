import { describe, expect, it, vi } from "vitest";
import { confirmOnEnter } from "@/lib/dialog-actions";

describe("dialog keyboard actions", () => {
  it("confirms on Enter and prevents the default action", () => {
    const confirm = vi.fn();
    const event = { key: "Enter", preventDefault: vi.fn(), stopPropagation: vi.fn() };

    confirmOnEnter(event, confirm);

    expect(event.preventDefault).toHaveBeenCalledOnce();
    expect(confirm).toHaveBeenCalledOnce();
  });

  it("stops Enter from triggering app-wide keyboard shortcuts", () => {
    const confirm = vi.fn();
    const event = {
      key: "Enter",
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
    };

    confirmOnEnter(event, confirm);

    expect(event.stopPropagation).toHaveBeenCalledOnce();
  });

  it("ignores Enter while the action is disabled", () => {
    const confirm = vi.fn();
    const event = { key: "Enter", preventDefault: vi.fn(), stopPropagation: vi.fn() };

    confirmOnEnter(event, confirm, true);

    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(confirm).not.toHaveBeenCalled();
  });

  it("ignores other keys", () => {
    const confirm = vi.fn();
    const event = { key: "Escape", preventDefault: vi.fn(), stopPropagation: vi.fn() };

    confirmOnEnter(event, confirm);

    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(confirm).not.toHaveBeenCalled();
  });
});
