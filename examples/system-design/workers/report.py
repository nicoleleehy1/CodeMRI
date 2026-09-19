"""Example Python worker included in the system inventory."""
import json

def summarize_orders(orders):
    return json.dumps({'orders': len(orders), 'revenue': sum(o['total'] for o in orders)})
