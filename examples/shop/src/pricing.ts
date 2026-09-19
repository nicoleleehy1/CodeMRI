import { applyCoupon as discount } from './coupons';
export function calculatePrice(items: number[], coupon: number): number {
  const subtotal = items.reduce((sum, price) => sum + price, 0);
  return discount(subtotal, coupon);
}
