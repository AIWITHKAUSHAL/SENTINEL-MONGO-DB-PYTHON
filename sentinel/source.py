"""Read original SENTINEL rows; never invent missing labels or dimension records."""
import csv
import os
from pathlib import Path
from itertools import islice
import psycopg
from psycopg import sql
from psycopg.rows import dict_row


def supabase_rows(limit):
    schema = sql.Identifier(os.getenv('SOURCE_SCHEMA', 'public'))
    query = sql.SQL('''
      SELECT to_jsonb(t) AS transaction, to_jsonb(c) AS customer,
             to_jsonb(m) AS merchant, to_jsonb(d) AS device, to_jsonb(l) AS label
      FROM {s}.transactions t
      JOIN {s}.customers c USING(customer_id)
      JOIN {s}.merchants m USING(merchant_id)
      LEFT JOIN {s}.devices d USING(device_id)
      LEFT JOIN {s}.labels l USING(transaction_id)
      ORDER BY t.transaction_id LIMIT %s
    ''').format(s=schema)
    with psycopg.connect(os.environ['DATABASE_URL'], sslmode='require',
                         connect_timeout=15, row_factory=dict_row) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        conn.execute("SET statement_timeout = '120s'")
        return conn.execute(query, (limit,)).fetchall()


def csv_rows(root, table):
    for path in sorted((Path(root) / 'tables' / table).rglob('*.csv')):
        if path.is_file():
            with path.open(newline='', encoding='utf-8-sig') as stream:
                for row in csv.DictReader(stream, strict=True):
                    if None in row or any(v is None for v in row.values()):
                        raise ValueError(f'Malformed CSV in table {table}')
                    yield row


def local_rows(root, limit):
    dimensions = {}
    for table, key in [('customers','customer_id'), ('merchants','merchant_id'),
                       ('devices','device_id'), ('labels','transaction_id')]:
        dimensions[table] = {r[key]: r for r in csv_rows(root, table)}
    result = []
    for t in islice(csv_rows(root, 'transactions'), limit):
        c = dimensions['customers'].get(t['customer_id'])
        m = dimensions['merchants'].get(t['merchant_id'])
        if not c or not m:
            raise ValueError('Incomplete export: missing customer or merchant dimension; use Supabase')
        result.append(dict(transaction=t, customer=c, merchant=m,
                           device=dimensions['devices'].get(t['device_id']),
                           label=dimensions['labels'].get(t['transaction_id'])))
    return result
