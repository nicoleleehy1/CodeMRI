import test from 'node:test';
import assert from 'node:assert/strict';
import { calculatePrice } from '../src/pricing';
import { applyCoupon } from '../src/coupons';

test('calculatePrice sums items and applies the coupon', () => {
  assert.equal(calculatePrice([10, 20, 30], 15), 45);
});

test('applyCoupon never returns a negative total', () => {
  assert.equal(applyCoupon(10, 25), 0);
  assert.equal(applyCoupon(30, 5), 25);
});
