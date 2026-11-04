import { describe, expect, it, vi } from "vitest";
import { makeCachedLoader } from "../invites-cache";

describe("makeCachedLoader", () => {
  it("caches a successful result", async () => {
    const load = vi.fn(async () => true);
    const get = makeCachedLoader(load);
    expect(await get()).toBe(true);
    expect(await get()).toBe(true);
    expect(load).toHaveBeenCalledTimes(1);
  });
  it("caches a real false", async () => {
    const load = vi.fn(async () => false);
    const get = makeCachedLoader(load);
    await get();
    await get();
    expect(load).toHaveBeenCalledTimes(1);
  });
  it("does not cache a failure: retries next time", async () => {
    const load = vi.fn().mockRejectedValueOnce(new Error("x")).mockResolvedValueOnce(true);
    const get = makeCachedLoader(load);
    await expect(get()).rejects.toThrow("x");
    await Promise.resolve();
    expect(await get()).toBe(true);
    expect(load).toHaveBeenCalledTimes(2);
  });
});
