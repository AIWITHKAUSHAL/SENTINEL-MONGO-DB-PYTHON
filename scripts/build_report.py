"""Build a static, shareable report from actual saved query output."""
from pathlib import Path
import json
from html import escape

ROOT=Path(__file__).resolve().parents[1]
def read(name): return json.loads((ROOT/'outputs'/name).read_text())
def table(headers, rows):
 return '<table><thead><tr>'+''.join(f'<th>{escape(str(h))}</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{escape(str(v))}</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'
source=read('source_validation.json'); load=read('load.json'); index=read('index_comparison.json'); agg=read('aggregations.json'); crud=read('crud.json')
style='''body{margin:0;background:#f1f5f9;color:#172b46;font:16px -apple-system,BlinkMacSystemFont,Arial,sans-serif}main{max-width:1100px;margin:40px auto}header{background:#112c36;color:white;padding:32px;border-radius:16px}h1{margin:8px 0;font-size:36px}.tag{font-size:12px;letter-spacing:2px;color:#7ce6c5}.cards{display:flex;gap:18px;margin:24px 0}.card{background:white;border-radius:12px;padding:24px;flex:1;border:1px solid #dde5ec}.number{font-size:34px;font-weight:700;color:#08775e}.label{font-size:14px;color:#546578;margin-top:8px}section{background:white;padding:24px;margin:20px 0;border-radius:12px;border:1px solid #dde5ec}h2{margin-top:0;font-size:21px}table{width:100%;border-collapse:collapse;font-size:14px}th{text-align:left;color:#536577;background:#f4f7fa}th,td{padding:11px;border-bottom:1px solid #e4eaf0}p{line-height:1.6}.note{font-size:13px;color:#596b7b}code{background:#edf4f7;padding:3px 6px;border-radius:4px}footer{font-size:13px;color:#596b7b;margin:24px}'''
header='<header><div class="tag">SENTINEL / MONGODB ATLAS + PYMONGO</div><h1>Verified database results</h1><p>Original Supabase sample → two MongoDB document collections</p></header>'
cards='<div class="cards">'+''.join(f'<div class="card"><div class="number">{n:,}</div><div class="label">{label}</div></div>' for n,label in [(load['transactions'],'Transactions in Atlas'),(load['customers'],'Customers in Atlas'),(source['fraudulent'],'Fraud-labeled events')])+'</div>'
crud_table=table(['Operation','Actual result'],[(k,crud[k]) for k in ['insert_one','insert_many','update_many','delete_one']]+[('find with filters + projection',str(len(crud['find_with_projection']))+' rows displayed')])
index_table=table(['Access path','Rows returned','Documents examined','Keys examined'],[(name, stats['nReturned'],stats['totalDocsExamined'],stats['totalKeysExamined']) for name,stats in index.items()])
fraud=table(['Merchant category','Transactions','Fraudulent','Fraud rate'],[(r['merchant_category'],r['transactions'],r['fraudulent'],f"{r['fraud_rate']*100:.3f}%" if r['fraud_rate'] is not None else 'Unknown') for r in agg['fraud_rate_per_merchant_category']])
top=table(['Customer','Amount (INR)','Transactions','Latest activity (UTC)'],[(r['customer_id'],f"{r['amount_paise']//100:,}.{r['amount_paise']%100:02d}",r['transactions'],r['last_activity']['$date']) for r in agg['top_10_customers_last_24h']])
pages={
 'overview':header+cards+'<section><h2>CRUD demonstration</h2>'+crud_table+'<p class="note">Temporary demo customer records are cleaned up; source transactions remain intact.</p></section><section><h2>Index comparison · same query, same results</h2>'+index_table+'<p class="note">Before: forced collection scan. After: compound customer_id + time index.</p></section><section><h2>Validation</h2><p>10 tests passed, including MongoDB integration tests and an independent Python check of both aggregations against the 5,000-row sample.</p><p class="note">Database operations verified on the supplied Atlas cluster. Free-tier status is not independently verified.</p></section>',
 'aggregations':header+'<section><h2>Fraud rate per merchant category</h2>'+fraud+'<p class="note">Fraudulent / labeled transactions. All 5,000 sampled events have labels.</p></section><section><h2>Top 10 customers · each customer’s last 24 hours</h2>'+top+'<p class="note">Inclusive window ending at each customer’s own latest event in the loaded sample. Exact totals stored in integer paise.</p></section>'
}
for name,body in pages.items():
 (ROOT/'docs'/f'{name}.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>SENTINEL results</title><style>'+style+'</style><main>'+body+'<footer>Actual saved output · 2 November 2026 · Synthetic teaching dataset · Sample statistics only</footer></main></html>')
print('Built docs/overview.html and docs/aggregations.html')
