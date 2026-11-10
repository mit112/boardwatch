import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QueueRowItem } from "../components/QueueRowItem";
import { queueRow } from "../test/rows";

/*
 * A row that is by hand for a reason the config knows says so. The route itself decides which list
 * the lead is in; this only explains it, so a row with no reason must not grow a line.
 */
function renderRow(overrides = {}) {
  return render(
    <QueueRowItem
      row={queueRow(overrides)}
      selected={false}
      active
      collapsing={false}
      onSelect={() => undefined}
    />,
  );
}

describe("the reason a lead is by hand", () => {
  it("shows the account wall the config named", () => {
    renderRow({ apply_route: "hand", apply_route_reason: "needs an account on myworkdayjobs.com" });
    screen.getByText("needs an account on myworkdayjobs.com");
  });

  it("shows nothing when the config knows no reason", () => {
    renderRow({ apply_route: "hand", apply_route_reason: null });
    expect(screen.queryByText(/needs an account on/)).toBeNull();
  });

  it("reads a row from a viewer that omits the field as having no reason", () => {
    const row = queueRow({ apply_route: "hand" });
    delete (row as { apply_route_reason?: string | null }).apply_route_reason;
    render(
      <QueueRowItem row={row} selected={false} active collapsing={false} onSelect={() => undefined} />,
    );
    expect(screen.queryByText(/needs an account on/)).toBeNull();
  });
});
