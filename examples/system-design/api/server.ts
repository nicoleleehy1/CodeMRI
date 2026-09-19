import express from 'express';
import { checkout } from '../services/checkout';
const app = express();
app.use(express.json());
export async function createOrder(items: number[], coupon: number) {
  return checkout(items, coupon);
}
app.post('/checkout', async (request, response) => {
  const order = await createOrder(request.body.items, request.body.coupon);
  response.json(order);
});
app.listen(3000);
