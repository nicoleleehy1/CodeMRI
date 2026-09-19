export function applyCoupon(total: number, discount: number): number {
  return Math.max(0, total - discount);
}
