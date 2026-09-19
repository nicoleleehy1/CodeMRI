import { calculatePrice } from './pricing';
import { saveOrder } from './orders';
export async function checkout(items: number[], coupon: number) {
  const total = calculatePrice(items, coupon);
  return saveOrder(total);
}
