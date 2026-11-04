import { describe, expect, it, vi } from "vitest";
import { fetchCandidates } from "../fetch-candidates";

const user = { id: "u1", display_name: "Ann", avatar_url: "", email: "a***@x.io" };

describe("fetchCandidates", () => {
  it("makes no request below 3 chars", async () => {
    const search = vi.fn();
    expect(await fetchCandidates({ search }, "ws", "p", "ab ")).toEqual({ results: [] });
    expect(await fetchCandidates({ search }, "ws", "p", undefined)).toEqual({ results: [] });
    expect(search).not.toHaveBeenCalled();
  });
  it("searches once with the trimmed query and returns the results", async () => {
    const search = vi.fn().mockResolvedValue([user]);
    expect(await fetchCandidates({ search }, "ws", "p", " ann ")).toEqual({ results: [user] });
    expect(search).toHaveBeenCalledTimes(1);
    expect(search).toHaveBeenCalledWith("ws", "p", "ann");
  });
});
