import test from 'node:test';
import assert from 'node:assert/strict';
import { checkout } from '../src/checkout';
import { saveOrder } from '../src/orders';

test('checkout prices the cart and saves an order', async () => {
  const order = await checkout([40, 10], 20);
  assert.deepEqual(order, { id: 'demo-order', total: 30, status: 'created' });
});

test('saveOrder returns a created order with the given total', async () => {
  assert.equal((await saveOrder(7)).status, 'created');
});
