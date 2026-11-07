import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { ApiError } from "@/lib/api";
import { demoData, demoReviews } from "@/lib/demo";
import { detailSchema } from "@/lib/contracts";
import { Reviews } from "@/components/reviews";
import { FindingCard, ReviewDetail } from "@/components/review-detail";
import { Empty, ErrorState, Loading } from "@/components/ui";

const nav = vi.hoisted(() => ({ query: "", replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/reviews",
  useSearchParams: () => new URLSearchParams(nav.query),
  useRouter: () => ({ replace: nav.replace }),
}));
function mount(children: ReactNode) {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      {children}
    </SWRConfig>,
  );
}
beforeEach(() => {
  nav.query = "";
  nav.replace.mockClear();
});

describe("review interactions", () => {
  it("loads reviews and resets the cursor when repository/state filters change", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) => {
        const url = new URL(path, "http://localhost");
        return Response.json(
          demoData(url.pathname.replace("/api/backend/", ""), url.searchParams),
        );
      }),
    );
    mount(<Reviews />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading reviews");
    expect(
      await screen.findByRole("link", { name: "Pull request #248" }),
    ).toHaveAttribute("href", `/reviews/${demoReviews[0].id}`);
    const user = userEvent.setup();
    await user.selectOptions(
      screen.getByLabelText("Filter by state"),
      "failed",
    );
    expect(nav.replace).toHaveBeenCalledWith("/reviews?state=failed", {
      scroll: false,
    });
    await user.type(screen.getByLabelText("Pull request number"), "248");
    await user.click(screen.getByRole("button", { name: "Find" }));
    expect(nav.replace).toHaveBeenCalledWith(
      "/reviews?pull_request_number=248",
      { scroll: false },
    );
    vi.unstubAllGlobals();
  });
  it("supports a manual retry after an API failure and displays empty results honestly", async () => {
    let fail = true;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        fail
          ? new Response("private-response", { status: 503 })
          : Response.json({ items: [], next_cursor: null }),
      ),
    );
    mount(<Reviews />);
    for (const alert of await screen.findAllByRole("alert"))
      expect(alert).not.toHaveTextContent("private-response");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByText("No reviews in this view"),
    ).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
  it("groups finding detail by file and discloses partial/mock coverage", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json(
          demoData(
            `v1/dashboard/reviews/${demoReviews[0].id}`,
            new URLSearchParams(),
          ),
        ),
      ),
    );
    mount(<ReviewDetail id={demoReviews[0].id} />);
    expect(
      await screen.findByRole("heading", { name: "Pull request #248" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "src/storage.py" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Deterministic mock-assisted/)).toBeInTheDocument();
    expect(screen.getByText(/Partial coverage/)).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "View source" })[0],
    ).toHaveAttribute("rel", "noopener noreferrer");
    vi.unstubAllGlobals();
  });
  it("renders hostile evidence and explanations as inert text", () => {
    const finding = detailSchema.parse(
      demoData(
        `v1/dashboard/reviews/${demoReviews[0].id}`,
        new URLSearchParams(),
      ),
    ).findings.items[0];
    const hostile = '<img src=x onerror="alert(1)">';
    const { container } = mount(
      <FindingCard
        finding={{
          ...finding,
          explanation: hostile,
          snippet: "<script>secret()</script>",
        }}
      />,
    );
    expect(screen.getByText(hostile)).toBeInTheDocument();
    expect(container.querySelector("img,script")).toBeNull();
    expect(screen.getByLabelText(/Source evidence/)).toHaveAttribute(
      "tabindex",
      "0",
    );
  });
  it("has announced loading/error states, a sign-in route, and accessible retry", async () => {
    const retry = vi.fn();
    const view = mount(<Loading />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    view.unmount();
    mount(<ErrorState error={new ApiError(401)} retry={retry} />);
    expect(screen.getByRole("link", { name: "Sign in again" })).toHaveAttribute(
      "href",
      "/login",
    );
    await waitFor(() => expect(retry).not.toHaveBeenCalled());
  });
  it("offers clear empty-state instructions", () => {
    mount(
      <Empty title="No findings" description="No stored findings match." />,
    );
    expect(
      screen.getByRole("heading", { name: "No findings" }),
    ).toBeInTheDocument();
  });
});
