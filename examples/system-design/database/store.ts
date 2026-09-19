import pg from 'pg';
const pool = new pg.Pool({ connectionString: process.env.DATABASE_URL });
export async function saveOrder(total: number) {
  const result = await pool.query('INSERT INTO orders (total) VALUES ($1) RETURNING id, total', [total]);
  return result.rows[0];
}
