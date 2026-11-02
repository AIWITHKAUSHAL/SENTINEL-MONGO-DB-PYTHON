"""Pipelines operate on the loaded sample, using each customer's own latest event."""


def fraud_pipeline():
    return [
        {'$group': {'_id': '$merchant_category', 'transactions': {'$sum': 1},
                    'labeled': {'$sum': {'$cond': [{'$in': ['$fraud_label', [0, 1]]}, 1, 0]}},
                    'fraudulent': {'$sum': {'$cond': [{'$eq': ['$fraud_label', 1]}, 1, 0]}}}},
        {'$project': {'_id': 0, 'merchant_category': '$_id', 'transactions': 1,
                      'labeled': 1, 'fraudulent': 1,
                      'fraud_rate': {'$cond': [{'$gt': ['$labeled', 0]},
                                              {'$divide': ['$fraudulent', '$labeled']}, None]}}},
        {'$sort': {'fraud_rate': -1, 'merchant_category': 1}},
    ]


def top_customers_pipeline():
    return [
        {'$setWindowFields': {'partitionBy': '$customer_id',
                              'output': {'last_activity': {'$max': '$time',
                                          'window': {'documents': ['unbounded', 'unbounded']}}}}},
        {'$match': {'$expr': {'$gte': ['$time', {'$dateSubtract': {
            'startDate': '$last_activity', 'unit': 'hour', 'amount': 24}}]}}},
        {'$group': {'_id': '$customer_id', 'amount_paise': {'$sum': '$amount_paise'},
                    'transactions': {'$sum': 1}, 'last_activity': {'$max': '$time'}}},
        {'$sort': {'amount_paise': -1, '_id': 1}}, {'$limit': 10},
        {'$project': {'_id': 0, 'customer_id': '$_id', 'amount_paise': 1,
                      'transactions': 1, 'last_activity': 1}},
    ]
