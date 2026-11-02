import certifi
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4
from datetime import timedelta
from dotenv import load_dotenv
from bson import json_util
from pymongo import MongoClient, ReplaceOne
from sentinel.source import supabase_rows, local_rows
from sentinel.model import documents
from sentinel.queries import fraud_pipeline, top_customers_pipeline

ROOT = Path(__file__).resolve().parents[1]


def save(name, value):
    target = ROOT / 'outputs' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json_util.dumps(value, indent=2) + '\n')


def prepare(source, limit):
    if limit < 5000:
        raise ValueError('Submission requires at least 5,000 transactions')
    rows = supabase_rows(limit) if source == 'supabase' else local_rows(os.environ['SENTINEL_DATA_DIR'], limit)
    customers, transactions = documents(rows)
    if len(transactions) < 5000:
        raise ValueError('Source contains fewer than 5,000 valid transactions')
    report = {'source': source, 'transactions': len(transactions), 'customers': len(customers),
              'labeled': sum(t['fraud_label'] is not None for t in transactions),
              'fraudulent': sum(t['fraud_label'] == 1 for t in transactions),
              'first_time': min(t['time'] for t in transactions),
              'last_time': max(t['time'] for t in transactions)}
    save('private/sample.json', {'customers': customers, 'transactions': transactions})
    save('source_validation.json', report)
    print(json_util.dumps(report, indent=2))


def connect():
    uri = os.environ['MONGODB_URI']
    options = {'tlsCAFile': certifi.where()} if uri.startswith('mongodb+srv://') or 'tls=true' in uri.lower() else {}
    client = MongoClient(uri, serverSelectionTimeoutMS=15000, tz_aware=True, **options)
    client.admin.command('ping')
    return client


def load(db):
    data = json_util.loads((ROOT / 'outputs/private/sample.json').read_text())
    for name in ['customers', 'transactions']:
        docs = data[name]
        # Stable source IDs make re-running a load idempotent.
        for offset in range(0, len(docs), 500):
            db[name].bulk_write([ReplaceOne({'_id': d['_id']}, d, upsert=True)
                                 for d in docs[offset:offset+500]], ordered=False)
    report = {name: db[name].count_documents({}) for name in ['customers','transactions']}
    if report['transactions'] < 5000:
        raise ValueError('MongoDB load has fewer than 5,000 transactions')
    save('load.json', report)
    print('Loaded:', report)


def crud(db):
    # Demonstrate writes on disposable customer records only.
    tag = 'demo_' + uuid4().hex
    ids = [tag + str(i) for i in range(3)]
    try:
        one = db.customers.insert_one({'_id': ids[0], 'customer_id': ids[0], 'demo_run': tag, 'devices': []})
        many = db.customers.insert_many([{'_id': i, 'customer_id': i, 'demo_run': tag, 'devices': []} for i in ids[1:]])
        sample = db.transactions.find_one({})
        found = list(db.transactions.find(
            {'customer_id': sample['customer_id'], 'amount_paise': {'$gt': 0}},
            {'_id': 0, 'customer_id': 1, 'amount_paise': 1, 'time': 1}).limit(5))
        updated = db.customers.update_many({'demo_run': tag}, {'$set': {'reviewed': True}})
        deleted = db.customers.delete_one({'_id': ids[0], 'demo_run': tag})
        report = {'insert_one': 1 if one.acknowledged else 0,
                  'insert_many': len(many.inserted_ids), 'find_with_projection': found,
                  'update_many': updated.modified_count, 'delete_one': deleted.deleted_count}
        save('crud.json', report)
        print('CRUD:', json_util.dumps(report))
    finally:
        for identifier in ids:
            db.customers.delete_one({'_id': identifier, 'demo_run': tag})


def indexes(db):
    sample = db.transactions.find_one({})
    query = {'customer_id': sample['customer_id'],
             'time': {'$gte': sample['time'] - timedelta(days=1)}}
    # Force collection scan for a reproducible baseline even on repeated runs.
    before = db.transactions.find(query).hint([('$natural', 1)]).explain()
    db.customers.create_index('customer_id', unique=True)
    db.transactions.create_index('customer_id')
    db.transactions.create_index('time')
    name = db.transactions.create_index([('customer_id', 1), ('time', 1)])
    after = db.transactions.find(query).hint(name).explain()
    save('explain_before.json', before)
    save('explain_after.json', after)
    summary = {label: {k: plan['executionStats'][k] for k in
                       ['nReturned', 'totalDocsExamined', 'totalKeysExamined', 'executionTimeMillis']}
               for label, plan in [('before', before), ('after', after)]}
    if summary['before']['nReturned'] != summary['after']['nReturned']:
        raise ValueError('Explain result counts differ')
    save('index_comparison.json', summary)
    print('Explain:', json.dumps(summary))


def aggregate(db):
    result = {'fraud_rate_per_merchant_category': list(db.transactions.aggregate(fraud_pipeline())),
              'top_10_customers_last_24h': list(db.transactions.aggregate(top_customers_pipeline()))}
    save('aggregations.json', result)
    print(json_util.dumps(result, indent=2))


def main():
    load_dotenv(ROOT / '.env')
    parser = argparse.ArgumentParser(description='SENTINEL MongoDB assignment')
    parser.add_argument('command', choices=['prepare', 'load', 'crud', 'indexes', 'aggregate', 'all', 'check'])
    parser.add_argument('--source', choices=['supabase','csv'], default='supabase')
    parser.add_argument('--limit', type=int, default=5000)
    args = parser.parse_args()
    try:
        if args.command in ('prepare', 'all'):
            prepare(args.source, args.limit)
            if args.command == 'prepare':
                return
        with connect() as client:
            db = client[os.environ.get('MONGODB_DB', 'sentinel_project')]
            if args.command == 'check':
                print('MongoDB ping successful')
            for name, fn in [('load',load), ('crud',crud), ('indexes',indexes), ('aggregate',aggregate)]:
                if args.command in (name, 'all'):
                    fn(db)
    except Exception as error:
        # Driver exceptions can contain credentials, hosts, or source records.
        parser.exit(1, f'{type(error).__name__}: operation failed. Check configuration, access, source schema, and README troubleshooting. Credentials withheld.\n')

if __name__ == '__main__':
    main()
