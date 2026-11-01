import { describe, expect, it } from "vitest";
import { artworkImageKey, shouldShowArtwork } from "@/lib/artwork-state";

describe("artwork image state", () => {
  it("treats a refreshed artwork URL as a new image for the same track", () => {
    const failedTrack = { id: "track-1", artwork_url: "/artwork?v=old" };
    const refreshedTrack = { ...failedTrack, artwork_url: "/artwork?v=new" };
    const failedImageKey = artworkImageKey(failedTrack);

    expect(shouldShowArtwork(failedTrack, failedImageKey)).toBe(false);
    expect(shouldShowArtwork(refreshedTrack, failedImageKey)).toBe(true);
  });
});
