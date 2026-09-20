import test from 'node:test';
import assert from 'node:assert/strict';
import { trackPage } from '../src/analytics';

test('trackPage records a view event', () => {
  assert.deepEqual(trackPage('/cart'), { event: 'view', page: '/cart' });
});
