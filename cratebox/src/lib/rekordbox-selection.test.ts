import { expect, it } from 'vitest';
import { selectionAfterEdit, tracksInSavedOrder } from './rekordbox-selection';

it('keeps the selected occurrence of a repeated song after reordering', () => {
  const previous = [{id:'501'}, {id:'502'}, {id:'503'}];
  expect(selectionAfterEdit(previous, [previous[2]!,previous[0]!,previous[1]!], '503')).toBe('503');
});
it('selects the replacement or adjacent entry after removal, and handles an empty playlist', () => {
  const previous = [{id:'501'}, {id:'502'}, {id:'503'}];
  expect(selectionAfterEdit(previous, [{id:'501'},{id:'new'},{id:'503'}], '502')).toBe('new');
  expect(selectionAfterEdit(previous, [{id:'501'},{id:'502'}], '503')).toBe('502');
  expect(selectionAfterEdit(previous, [], '503')).toBeUndefined();
});

it('applies the saved entry order without mixing up repeated tracks', () => {
  const track = {
    id: '501', rekordbox_id: '1', title: 'Fixture', artist: '', album: '',
    duration: 180, rating: 0, bpm: 120, key: '', quality: 'WAV', url: '',
  };
  const repeated = { ...track, id: '503' };
  const entries = [
    { entry_id: '503', track_id: '1' },
    { entry_id: '501', track_id: '1' },
  ];
  expect(tracksInSavedOrder([track, repeated], entries)).toEqual([repeated, track]);
  expect(tracksInSavedOrder([track, repeated], [entries[0]!, entries[0]!])).toBeNull();
  expect(tracksInSavedOrder([track, repeated], [{ ...entries[0]!, track_id: '2' }, entries[1]!])).toBeNull();
});
