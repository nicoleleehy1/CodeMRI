export async function submitCheckout(items: number[], coupon: number) {
  return fetch('/checkout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items, coupon }),
  });
}
