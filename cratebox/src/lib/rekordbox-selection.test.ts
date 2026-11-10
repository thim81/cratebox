import { expect, it } from 'vitest';
import { selectionAfterEdit } from './rekordbox-selection';

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
