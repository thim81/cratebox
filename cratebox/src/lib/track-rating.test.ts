import { describe, expect, it } from "vitest";
import { updateTrackRating } from "@/lib/track-rating";

describe("updateTrackRating", () => {
  it("updates the loaded track identity even when another row is selected", () => {
    const tracks = [
      { id: "loaded", rating: 1 },
      { id: "selected", rating: 2 },
    ];

    expect(updateTrackRating(tracks, "loaded", 5)).toEqual([
      { id: "loaded", rating: 5 },
      { id: "selected", rating: 2 },
    ]);
  });

  it("matches the loaded Rekordbox track when row IDs are playlist occurrences", () => {
    const tracks = [
      { id: "42-1", rekordbox_id: "42", rating: 1 },
      { id: "43-1", rekordbox_id: "43", rating: 2 },
    ];

    expect(updateTrackRating(tracks, "collection-42", 5, "42")).toEqual([
      { id: "42-1", rekordbox_id: "42", rating: 5 },
      { id: "43-1", rekordbox_id: "43", rating: 2 },
    ]);
  });
});
