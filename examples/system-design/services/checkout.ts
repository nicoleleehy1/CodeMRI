import { saveOrder } from '../database/store';
export function applyCoupon(total: number, coupon: number) {
  return Math.max(0, total - coupon);
}
export async function checkout(items: number[], coupon: number) {
  const total = applyCoupon(items.reduce((sum, value) => sum + value, 0), coupon);
  return saveOrder(total);
}
