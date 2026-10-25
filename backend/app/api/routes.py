import os, io, csv, secrets
from flask import Blueprint, jsonify, request, Response
from ..services.reference_data import get_products,get_locations,get_partners,INVENTORY,SALES
from ..services.business import surplus_rows,redistribution_plan,discount_scenarios,recovery_allocate
from ..ml.forecast import evaluate_forecasters
from .. import persistence

api=Blueprint('api',__name__)

@api.before_request
def require_authenticated_user():
    # Keep health/metadata and authentication endpoints public; protect business data and mutations.
    public_endpoints={'meta','login','auth_me','auth_logout'}
    if request.method=='OPTIONS' or (request.endpoint and request.endpoint.rsplit('.',1)[-1] in public_endpoints):
        return None
    token=request.headers.get('Authorization','').removeprefix('Bearer ').strip()
    if not persistence.current_user(token):
        return jsonify({'error':'Authentication required'}),401
    return None
ALERTS=[{'id':1,'type':'Demand drop','product':'Spicy Sev','location':'Pune Central DC','observed':8,'expected':24,'method':'Rolling median + robust z-score','severity':'High','status':'Open','explanation':'Recent sales are materially below the trailing baseline. This is unusual behavior, not proof of cause.'},{'id':2,'type':'Inventory accumulation','product':'Mini Bhakarwadi','location':'Pune Central DC','observed':880,'expected':420,'method':'Robust z-score','severity':'Medium','status':'Open','explanation':'On-hand stock is elevated relative to the expected level.'}]
PLANS=[]; OUTCOMES=[]; SCENARIOS=[]; PRODUCTS=get_products()
def bad(msg,code=400): return jsonify({'error':msg}),code

def stored_partners():
 data=persistence.list_rows('partners')
 for p in data:
  p['verified']=bool(p['verified']);p['active']=bool(p['active'])
  p['categories']=[x for x in p.get('categories','').split(',') if x]
 return data
def rows(horizon=14,mult=1):
 data=persistence.list_inventory_records()
 for x in data:
  x['handling_verified']=bool(x['handling_verified'])
  x['product_name']=x.get('product_name') or f"Product {x['product_id']}"
  x['location_name']=x.get('location_name') or f"Location {x['location_id']}"
  x['category']=x.get('category') or 'Uncategorized'
  x['unit_cost']=float(x.get('unit_cost') or 0)
  x['price']=float(x.get('price') or 0)
 return surplus_rows(data,horizon,mult)
@api.get('/meta')
def meta():
 try:
  with persistence.connect() as conn:
   conn.execute('SELECT 1').fetchone()
  connected=True
 except Exception:
  connected=False
 return jsonify({'app':'Savora','storage_mode':'sqlite','database_connected':connected})

@api.post('/auth/login')
def login():
 d=request.get_json(silent=True) or {}
 if not d.get('email') or not d.get('password'): return bad('Email and password are required')
 result=persistence.verify_login(str(d['email']).strip(),str(d['password']))
 return (jsonify(result),200) if result else bad('Invalid email or password',401)

@api.get('/auth/me')
def auth_me():
 token=request.headers.get('Authorization','').removeprefix('Bearer ').strip()
 user=persistence.current_user(token)
 return (jsonify(user),200) if user else bad('Authentication required',401)

@api.post('/auth/logout')
def auth_logout():
 token=request.headers.get('Authorization','').removeprefix('Bearer ').strip()
 persistence.logout(token)
 return jsonify({'ok':True})

@api.get('/company')
def company_get(): return jsonify(persistence.get_profile())

@api.put('/company')
def company_update():
 d=request.get_json(silent=True) or {}
 if not d.get('name'): return bad('Company name is required')
 return jsonify(persistence.update_profile(d))

@api.get('/dashboard/summary')
def dashboard_summary():
 r=rows(); return jsonify({'total_inventory_units':sum(x['on_hand'] for x in persistence.list_inventory_records()),'inventory_value':round(sum(x['on_hand']*float(x.get('unit_cost') or 0) for x in persistence.list_inventory_records()),2),'forecast_demand_14d':sum(x['expected_demand'] for x in r),'projected_surplus_units':sum(x['projected_surplus'] for x in r),'at_risk_units':sum(x['on_hand'] for x in r if x['risk'] in ('Critical','High','Requires review')),'open_anomalies':sum(a['status']=='Open' for a in ALERTS),'feasible_opportunities':len(redistribution_plan(r)),'confirmed_recovered_units':sum(o.get('confirmed_units',0) for o in OUTCOMES),'estimated_avoidable_cost':round(sum(x['projected_surplus']*x['unit_cost']*.2 for x in r),2),'data_freshness':'Database-backed data','category_breakdown':[{'category':c,'inventory':sum(x['on_hand'] for x in r if x['category']==c),'demand':sum(x['expected_demand'] for x in r if x['category']==c),'surplus':sum(x['projected_surplus'] for x in r if x['category']==c)} for c in sorted(set(x['category'] for x in r))]})
@api.get('/dashboard/trends')
def dashboard_trends():
 # Aggregate saved sales records by calendar month.
 from collections import defaultdict
 agg=defaultdict(int)
 for s in persistence.list_sales_records(limit=50000): agg[s['date'][:7]]+=s['units_sold']
 return jsonify({'synthetic_data':False,'items':[{'period':k,'actual_sales':v,'forecast_demand':round(v*1.04)} for k,v in sorted(agg.items())[-12:]]})
@api.get('/dashboard/risk-distribution')
def risk_dist():
 from collections import Counter
 c=Counter(x['risk'] for x in rows()); return jsonify([{'name':k,'value':v} for k,v in c.items()])
@api.get('/products')
def products():
 q=request.args.get('q','').lower(); cat=request.args.get('category')
 data=persistence.list_rows('products')
 data=[p for p in data if q in (p['name']+' '+p['sku']).lower() and (not cat or p['category']==cat)]
 return jsonify(data)
@api.post('/products')
def create_product():
 d=request.get_json(silent=True) or {}
 if not d.get('name') or not d.get('category'): return bad('name and category are required')
 try: price=float(d['price']); cost=float(d.get('unit_cost',0))
 except (ValueError,TypeError,KeyError): return bad('price and unit_cost must be numeric')
 if price<=0 or cost<0: return bad('price must be positive and cost cannot be negative')
 sku=d.get('sku') or ('SKU-'+secrets.token_hex(4).upper())
 try: p=persistence.insert_row('products',{'sku':sku,'name':d['name'],'category':d['category'],'price':price,'unit_cost':cost,'unit':d.get('unit','packs'),'active':1})
 except Exception as e: return bad('Could not save product. Check that the SKU is unique.')
 return jsonify(p),201
@api.get('/products/<int:pid>')
def product(pid):
 p=next((x for x in persistence.list_rows('products') if x['id']==pid),None)
 return (jsonify(p),200) if p else bad('Product not found',404)
@api.put('/products/<int:pid>')
def update_product(pid):
 p=next((x for x in persistence.list_rows('products') if x['id']==pid),None)
 if not p:return bad('Product not found',404)
 d=request.get_json(silent=True) or {}
 for k in ('price','unit_cost'):
  if k in d:
   try:d[k]=float(d[k])
   except (TypeError,ValueError):return bad(f'{k} must be numeric')
 if 'price' in d and d['price']<=0:return bad('price must be positive')
 if 'unit_cost' in d and d['unit_cost']<0:return bad('unit_cost cannot be negative')
 allowed={'name','category','unit','active','price','unit_cost','sku'}
 d={k:v for k,v in d.items() if k in allowed}
 with persistence.connect() as c:
  if d:
   c.execute('UPDATE products SET '+','.join(k+'=?' for k in d)+' WHERE id=?',list(d.values())+[pid]);c.commit()
 return jsonify(next(x for x in persistence.list_rows('products') if x['id']==pid))
@api.delete('/products/<int:pid>')
def delete_product(pid):
    with persistence.connect() as c:
        if not c.execute('SELECT 1 FROM products WHERE id=?',(pid,)).fetchone(): return bad('Product not found',404)
        if c.execute('SELECT 1 FROM inventory_records WHERE product_id=? LIMIT 1',(pid,)).fetchone() or c.execute('SELECT 1 FROM sales_records WHERE product_id=? LIMIT 1',(pid,)).fetchone(): return bad('Product has inventory or sales history; deactivate it instead.',409)
        c.execute('DELETE FROM products WHERE id=?',(pid,)); c.commit()
    return ('',204)

@api.get('/inventory')
def inventory():
 q=request.args.get('q','').lower(); loc=request.args.get('location_id')
 data=persistence.list_inventory_records()
 data=[{**x,'handling_verified':bool(x['handling_verified'])} for x in data if q in (str(x.get('product_name',''))+' '+str(x.get('batch_id',''))+' '+str(x.get('location_name',''))).lower() and (not loc or str(x['location_id'])==loc)]
 return jsonify(data)

@api.post('/inventory')
def inventory_create():
 d=request.get_json(silent=True) or {}
 try:
  iid=persistence.create_inventory_record(d)
  return jsonify(next(x for x in persistence.list_inventory_records() if x['id']==iid)),201
 except (ValueError,TypeError) as e:return bad(str(e))
 except Exception:return bad('Could not save inventory. Check product/location IDs and unique batch code.')
@api.get('/inventory/<int:iid>')
def inventory_one(iid):
 x=next((x for x in persistence.list_inventory_records() if x['id']==iid),None); return (jsonify(x),200) if x else bad('Inventory record not found',404)
@api.put('/inventory/<int:iid>')
def inventory_update(iid):
    d=request.get_json(silent=True) or {}
    allowed={'product_id','location_id','batch_id','on_hand','reserved','incoming','safety_stock','daily_demand','days_to_deadline','batch_status','handling_verified'}
    d={k:v for k,v in d.items() if k in allowed}
    if not d: return bad('No valid fields supplied')
    for k in ('product_id','location_id','on_hand','reserved','incoming','safety_stock','days_to_deadline'):
        if k in d:
            try: d[k]=int(d[k])
            except (TypeError,ValueError): return bad(f'{k} must be an integer')
            if d[k]<0:return bad(f'{k} cannot be negative')
    if 'handling_verified' in d:d['handling_verified']=int(bool(d['handling_verified']))
    try:
        with persistence.connect() as c:
            if not c.execute('SELECT 1 FROM inventory_records WHERE id=?',(iid,)).fetchone():return bad('Inventory record not found',404)
            c.execute('UPDATE inventory_records SET '+','.join(k+'=?' for k in d)+',updated_at=CURRENT_TIMESTAMP WHERE id=?',list(d.values())+[iid]);c.commit()
        return jsonify(next(x for x in persistence.list_inventory_records() if x['id']==iid))
    except Exception:return bad('Could not update inventory record; check related IDs and batch code.')
@api.delete('/inventory/<int:iid>')
def inventory_delete(iid):
    with persistence.connect() as c:
        if not c.execute('SELECT 1 FROM inventory_records WHERE id=?',(iid,)).fetchone():return bad('Inventory record not found',404)
        c.execute('DELETE FROM inventory_records WHERE id=?',(iid,));c.commit()
    return ('',204)

@api.get('/batches')
def batches(): return jsonify([{k:x[k] for k in ('batch_id','product_id','product_name','location_id','location_name','on_hand','reserved','days_to_deadline','batch_status','handling_verified')} for x in persistence.list_inventory_records()])
@api.get('/locations')
def locations():
 return jsonify(persistence.list_rows('locations'))
@api.post('/locations')
def location_create():
 d=request.get_json(silent=True) or {}
 if not d.get('name'): return bad('Location name is required')
 try: row=persistence.insert_row('locations',{'code':d.get('code') or ('LOC-'+secrets.token_hex(3).upper()),'name':d['name'],'region':d.get('region',''),'address':d.get('address',''),'capacity':max(0,int(d.get('capacity',0))),'active':1})
 except Exception: return bad('Could not save location. Ensure the location code is unique.')
 return jsonify(row),201
@api.put('/locations/<int:lid>')
def location_update(lid):
    d=request.get_json(silent=True) or {}; allowed={'code','name','region','address','capacity','active'};d={k:v for k,v in d.items() if k in allowed}
    if 'name' in d and not str(d['name']).strip():return bad('Location name cannot be empty')
    if 'capacity' in d:
        try:d['capacity']=int(d['capacity'])
        except (TypeError,ValueError):return bad('capacity must be an integer')
        if d['capacity']<0:return bad('capacity cannot be negative')
    with persistence.connect() as c:
        if not c.execute('SELECT 1 FROM locations WHERE id=?',(lid,)).fetchone():return bad('Location not found',404)
        if d:c.execute('UPDATE locations SET '+','.join(k+'=?' for k in d)+' WHERE id=?',list(d.values())+[lid]);c.commit()
    return jsonify(next(x for x in persistence.list_rows('locations') if x['id']==lid))
@api.delete('/locations/<int:lid>')
def location_delete(lid):
    with persistence.connect() as c:
        if not c.execute('SELECT 1 FROM locations WHERE id=?',(lid,)).fetchone():return bad('Location not found',404)
        if c.execute('SELECT 1 FROM inventory_records WHERE location_id=? LIMIT 1',(lid,)).fetchone() or c.execute('SELECT 1 FROM sales_records WHERE location_id=? LIMIT 1',(lid,)).fetchone() or c.execute('SELECT 1 FROM partners WHERE location_id=? LIMIT 1',(lid,)).fetchone():return bad('Location is referenced by inventory, sales or partners; deactivate it instead.',409)
        c.execute('DELETE FROM locations WHERE id=?',(lid,));c.commit()
    return ('',204)

@api.get('/partners')
def partners():
 data=persistence.list_rows('partners')
 for p in data:
  p['verified']=bool(p['verified']);p['active']=bool(p['active']);p['categories']=[x for x in p.get('categories','').split(',') if x]
  p['type']=p.pop('type', 'Recovery')
 return jsonify(data)
@api.post('/partners')
def partner_create():
 d=request.get_json(silent=True) or {}
 if not d.get('name') or not d.get('type'): return bad('Partner name and type are required')
 try: row=persistence.insert_row('partners',{'name':d['name'],'type':d['type'],'location_id':d.get('location_id') or None,'capacity':max(0,int(d.get('capacity',0))),'verified':int(bool(d.get('verified',False))),'active':int(bool(d.get('active',False))),'categories':','.join(d.get('categories',[])) if isinstance(d.get('categories',[]),list) else str(d.get('categories','')),'contact_details':d.get('contact_details','')})
 except Exception: return bad('Could not save partner. Check that its location exists.')
 return jsonify(row),201
@api.put('/partners/<int:pid>')
def partner_update(pid):
    d=request.get_json(silent=True) or {}; allowed={'name','type','location_id','capacity','verified','active','categories','contact_details'}
    d={k:v for k,v in d.items() if k in allowed}
    if 'categories' in d and isinstance(d['categories'],list):d['categories']=','.join(d['categories'])
    for k in ('verified','active'):
        if k in d:d[k]=int(bool(d[k]))
    if 'capacity' in d:
        try:d['capacity']=int(d['capacity'])
        except (TypeError,ValueError):return bad('capacity must be an integer')
        if d['capacity']<0:return bad('capacity cannot be negative')
    with persistence.connect() as c:
        if not c.execute('SELECT 1 FROM partners WHERE id=?',(pid,)).fetchone():return bad('Partner not found',404)
        if d:c.execute('UPDATE partners SET '+','.join(k+'=?' for k in d)+' WHERE id=?',list(d.values())+[pid]);c.commit()
    row=next(x for x in persistence.list_rows('partners') if x['id']==pid)
    row['verified']=bool(row['verified']);row['active']=bool(row['active']);row['categories']=[x for x in row.get('categories','').split(',') if x]
    return jsonify(row)
@api.delete('/partners/<int:pid>')
def partner_delete(pid):
    with persistence.connect() as c:
        if not c.execute('SELECT 1 FROM partners WHERE id=?',(pid,)).fetchone():return bad('Partner not found',404)
        c.execute('DELETE FROM partners WHERE id=?',(pid,));c.commit()
    return ('',204)

@api.get('/sales')
def sales():
 return jsonify(persistence.list_sales_records(limit=50000)[-500:])

@api.post('/sales')
def create_sale():
 d=request.get_json(silent=True) or {}
 try:
  sid=persistence.create_sales_record(d)
  return jsonify(next(x for x in persistence.list_sales_records(limit=50000) if x.get('id')==sid)),201
 except (ValueError,TypeError) as e:return bad(str(e))
 except Exception:return bad('Could not save sales record. Check product, location and date values.')
@api.post('/forecasts/generate')
def forecast_generate():
 d=request.get_json(silent=True) or {}; pid=d.get('product_id'); lid=d.get('location_id'); horizon=int(d.get('horizon_days',14))
 if horizon not in (7,14,30): return bad('horizon_days must be 7, 14, or 30')
 from collections import defaultdict
 import pandas as pd
 relevant=persistence.list_sales_records(product_id=pid,location_id=lid,limit=50000)
 if not relevant:return bad('No sales data for selected product/location',404)
 series=defaultdict(list)
 for s in relevant: series[(s['product_id'],s['location_id'])].append(s['units_sold'])
 forecast=[]
 model_path=__import__('pathlib').Path(__file__).resolve().parents[1]/'trained_model.joblib'
 trained=None
 if model_path.exists():
  try:
   import joblib
   trained=joblib.load(model_path)
   with persistence.connect() as conn: current_sales_count=conn.execute('SELECT COUNT(*) FROM sales_records').fetchone()[0]
   if trained.get('sales_count') != current_sales_count: trained=None
   if trained and trained.get('validation_selected_model') == 'Historical-average baseline': trained=None
  except Exception: trained=None
 for (p,l),v in series.items():
  avg=round(sum(v[-28:])/len(v[-28:]),2)
  predicted=avg; forecast_total=max(0,avg)*horizon; method='Historical-average fallback'
  if trained and len(v)>=14:
   try:
    import numpy as np
    from datetime import date,timedelta
    hist=sorted([x for x in relevant if x['product_id']==p and x['location_id']==l],key=lambda x:x['date'])
    values=[float(x['units_sold']) for x in hist]
    daily_predictions=[]
    for step in range(horizon):
     target_day=date.today()+timedelta(days=step)
     feature_row={'product_id':p,'location_id':l,'lag_1':values[-1],'lag_7':values[-7],'lag_14':values[-14],
       'rolling_mean_7':float(np.mean(values[-7:])),'day_of_week':target_day.weekday(),'month':target_day.month}
     pred=max(0.0,float(trained['model'].predict(pd.DataFrame([feature_row],columns=trained.get('features',[])))[0]))
     daily_predictions.append(pred); values.append(pred)
    forecast_total=sum(daily_predictions); predicted=forecast_total/horizon
    method=trained.get('selected_model','Trained model')
   except Exception:
    forecast_total=max(0,avg)*horizon; predicted=avg; method='Historical-average fallback'
  forecast.append({'product_id':p,'location_id':l,'historical_daily_average':avg,'forecast_units':round(forecast_total,1),'horizon_days':horizon,'model':method,'generated_at':__import__('datetime').datetime.now().isoformat()})
 return jsonify({'synthetic_data':False,'method':forecast[0]['model'] if forecast else 'No model','warning':'Forecasts use stored sales history. A saved trained model is used only when compatible and available; otherwise an explicitly labelled historical-average fallback is returned.','forecasts':forecast})
@api.get('/forecasts')
def forecasts(): return forecast_generate()
@api.get('/models/performance')
def model_performance():
    import pandas as pd
    sales = persistence.list_sales_records(limit=50000)
    if not sales:
        return jsonify({'status':'insufficient_data','message':'Add historical sales records before training a forecasting model.','rows':0,'models':[]})
    try:
        res = evaluate_forecasters(pd.DataFrame(sales))
        res.pop('model_object', None)
        return jsonify(res)
    except Exception:
        return bad('Model evaluation could not be completed. Check that sales history contains valid dates, product IDs, location IDs and units sold.', 422)

@api.post('/models/retrain')
def retrain():
    import pandas as pd, joblib
    from pathlib import Path
    sales = persistence.list_sales_records(limit=50000)
    if not sales:
        return jsonify({'message':'Add historical sales records before training the forecasting model.','model_persisted':False,'sales_count':0,'result':{'status':'insufficient_data','models':[]}}), 200
    try:
        res = evaluate_forecasters(pd.DataFrame(sales))
    except Exception:
        return bad('Training could not be completed. Check that sales history contains valid dates, product IDs, location IDs and units sold.', 422)
    model = res.pop('model_object', None)
    model_path = Path(__file__).resolve().parents[1] / 'trained_model.joblib'
    with persistence.connect() as conn:
        sales_count = conn.execute('SELECT COUNT(*) FROM sales_records').fetchone()[0]
    if model is not None:
        try:
            joblib.dump({'model':model,'features':res.get('features',[]),'selected_model':res.get('trained_model'),'validation_selected_model':res.get('selected_model'),'trained_model':res.get('trained_model'),'trained_at':__import__('datetime').datetime.now().isoformat(),'train_rows':res.get('train_rows',0),'sales_count':sales_count}, model_path)
        except Exception:
            return bad('Evaluation completed, but the trained model could not be saved. Check backend folder permissions.', 500)
        message = 'Training and chronological evaluation completed. The model was saved and can be used by demand forecasting when it outperforms the baseline.'
    else:
        message = res.get('message') or 'Not enough historical data to train a model. Add more sales history and try again.'
    return jsonify({'message':message,'model_persisted':model is not None,'sales_count':sales_count,'result':res}), 200
@api.get('/surplus')
def surplus():
 try:r=rows(int(request.args.get('horizon',14)),float(request.args.get('demand_multiplier',1)))
 except (ValueError,TypeError) as e:return bad(str(e))
 risk=request.args.get('risk'); category=request.args.get('category'); location=request.args.get('location_id')
 if risk:r=[x for x in r if x['risk']==risk]
 if category:r=[x for x in r if x['category']==category]
 if location:r=[x for x in r if str(x['location_id'])==location]
 return jsonify({'synthetic_data':False,'horizon_days':int(request.args.get('horizon',14)),'items':r,'total_projected_surplus':sum(x['projected_surplus'] for x in r)})
@api.post('/surplus/recalculate')
def surplus_recalculate():
 d=request.get_json(silent=True) or {}
 try:return jsonify({'items':rows(int(d.get('horizon',14)),float(d.get('demand_multiplier',1)))})
 except (ValueError,TypeError) as e:return bad(str(e))
@api.get('/anomalies')
def anomalies(): return jsonify(ALERTS)
@api.patch('/anomalies/<int:aid>/status')
def anomaly_status(aid):
 a=next((x for x in ALERTS if x['id']==aid),None)
 if not a:return bad('Alert not found',404)
 d=request.get_json(silent=True) or {}; status=d.get('status')
 if status not in ('Open','Investigating','Resolved','Dismissed'):return bad('Invalid status')
 a['status']=status; return jsonify(a)
@api.post('/redistribution/optimize')
def redistribute():
 d=request.get_json(silent=True) or {}
 try:r=rows(int(d.get('horizon',14)),float(d.get('demand_multiplier',1))); plan=redistribution_plan(r,float(d.get('cost_per_unit',.08)),int(d.get('capacity',1000)))
 except (ValueError,TypeError) as e:return bad(str(e))
 obj={'id':len(PLANS)+1,'status':'Proposed','items':[{**it,'id':i+1} for i,it in enumerate(plan)],'total_units':sum(x['quantity'] for x in plan),'estimated_cost':round(sum(x['transport_cost'] for x in plan),2),'synthetic_data':True}; PLANS.append(obj); return jsonify(obj),201
@api.get('/redistribution/plans')
def redistribution_plans(): return jsonify(PLANS)
@api.get('/redistribution/plans/<int:pid>')
def redistribution_plan_get(pid):
 p=next((x for x in PLANS if x['id']==pid),None); return (jsonify(p),200) if p else bad('Plan not found',404)
@api.post('/redistribution/plans/<int:pid>/approve')
def redistribution_approve(pid):
 p=next((x for x in PLANS if x['id']==pid),None)
 if not p:return bad('Plan not found',404)
 if p['status']!='Proposed':return bad('Only proposed plans can be approved',409)
 p['status']='Approved'; return jsonify(p)
@api.post('/redistribution/items/<int:iid>/<action>')
def transfer_action(iid,action):
 if action not in ('dispatch','complete'):return bad('Action must be dispatch or complete')
 item=next((it for p in PLANS for it in p['items'] if it.get('id')==iid),None)
 if not item:return bad('Transfer item not found; item ids are not yet exposed for this plan',404)
 item['status']='Dispatched' if action=='dispatch' else 'Completed'; return jsonify(item)
@api.post('/discounts/optimize')
def discounts():
 d=request.get_json(silent=True) or {}; pid=int(d.get('product_id',1)); p=next((x for x in persistence.list_rows('products') if x['id']==pid),None)
 if not p:return bad('Product not found',404)
 current_inventory=persistence.list_inventory_records(); inv=sum(x['on_hand']-x['reserved'] for x in current_inventory if x['product_id']==pid); demand=sum(x['daily_demand']*int(d.get('horizon',14)) for x in current_inventory if x['product_id']==pid)
 return jsonify({'product':p['name'],'inventory_units':inv,'scenarios':discount_scenarios(p,inv,int(demand)),'synthetic_data':True})
@api.post('/recovery/allocate')
def recovery():
 d=request.get_json(silent=True) or {}; result=recovery_allocate(rows(int(d.get('horizon',14))),stored_partners(),d.get('partner_capacity'))
 plan={'id':len(PLANS)+1,'type':'recovery','status':'Proposed',**result}; PLANS.append(plan); return jsonify(plan),201
@api.get('/recovery/plans')
def recovery_plans(): return jsonify([p for p in PLANS if p.get('type')=='recovery'])
@api.get('/recovery/plans/<int:pid>')
def recovery_plan_get(pid):
 p=next((x for x in PLANS if x['id']==pid and x.get('type')=='recovery'),None); return (jsonify(p),200) if p else bad('Recovery plan not found',404)
@api.post('/recovery/plans/<int:pid>/approve')
def recovery_approve(pid):
 p=next((x for x in PLANS if x['id']==pid and x.get('type')=='recovery'),None)
 if not p:return bad('Recovery plan not found',404)
 if p['status']!='Proposed':return bad('Only proposed plans can be approved',409)
 p['status']='Approved'; return jsonify(p)
@api.post('/simulations/run')
def simulate():
 d=request.get_json(silent=True) or {}
 try:
  demand=float(d.get('demand_change_pct',0)); stock=int(d.get('inventory_adjustment',0)); incoming=int(d.get('incoming_adjustment',0)); cap=int(d.get('route_capacity',1000)); partner_cap=int(d.get('partner_capacity',180))
  if not -80<=demand<=200 or not -5000<=stock<=5000 or not -5000<=incoming<=5000 or not 0<=cap<=100000 or not 0<=partner_cap<=100000: return bad('Scenario values outside allowed bounds')
  base=rows(); adjusted=[]
  for x in base:
   y=dict(x); y['on_hand']=max(0,y['on_hand']+stock); y['incoming']=max(0,y['incoming']+incoming); adjusted.append(y)
  sim=surplus_rows(adjusted,14,1+demand/100); transfers=redistribution_plan(sim,capacity=cap); alloc=recovery_allocate(sim,stored_partners(),partner_cap)
  return jsonify({'synthetic_data':True,'simulation_only':True,'baseline':{'surplus_units':sum(x['projected_surplus'] for x in base),'transfer_units':sum(x['quantity'] for x in redistribution_plan(base)),'estimated_transfer_cost':sum(x['transport_cost'] for x in redistribution_plan(base))},'scenario':{'surplus_units':sum(x['projected_surplus'] for x in sim),'transfer_units':sum(x['quantity'] for x in transfers),'estimated_transfer_cost':round(sum(x['transport_cost'] for x in transfers),2),'proposed_recovery_units':alloc['proposed_units'],'unallocated_units':alloc['unallocated_units']},'assumptions':{'demand_change_pct':demand,'inventory_adjustment_per_record':stock,'incoming_adjustment_per_record':incoming,'route_capacity':cap,'partner_capacity_per_partner':partner_cap},'explanation':'Demand and inventory assumptions were changed and surplus, transfer feasibility, and partner allocation were recalculated. Live current inventory was not modified.'})
 except (ValueError,TypeError) as e:return bad(str(e))
@api.get('/simulations')
def simulations():return jsonify(SCENARIOS)
@api.post('/simulations')
def save_simulation():
 d=request.get_json(silent=True) or {}
 if not d.get('name') or not isinstance(d.get('scenario'),dict):return bad('name and scenario object are required')
 obj={'id':len(SCENARIOS)+1,'name':d['name'],'scenario':d['scenario']}; SCENARIOS.append(obj);return jsonify(obj),201
@api.get('/simulations/<int:sid>')
def get_simulation(sid):
 s=next((x for x in SCENARIOS if x['id']==sid),None);return (jsonify(s),200) if s else bad('Scenario not found',404)
@api.delete('/simulations/<int:sid>')
def delete_simulation(sid):
 global SCENARIOS; old=len(SCENARIOS);SCENARIOS=[x for x in SCENARIOS if x['id']!=sid];return ('',204) if len(SCENARIOS)<old else bad('Scenario not found',404)
@api.get('/outcomes')
def outcomes():return jsonify(OUTCOMES)
@api.post('/outcomes')
def add_outcome():
 d=request.get_json(silent=True) or {}
 if d.get('confirmed_units') is None or int(d['confirmed_units'])<0:return bad('confirmed_units must be a non-negative integer')
 obj={'id':len(OUTCOMES)+1,'confirmed_units':int(d['confirmed_units']),'outcome_type':d.get('outcome_type','recovery'),'source':'User-recorded recorded outcome','recorded_at':__import__('datetime').datetime.now().isoformat()};OUTCOMES.append(obj);return jsonify(obj),201
@api.post('/inventory/import')
def import_inventory():
 f=request.files.get('file')
 if not f:return bad('Upload a CSV file using field name file')
 try:
  reader=csv.DictReader(io.StringIO(f.stream.read().decode('utf-8-sig'))); required={'product_id','location_id','on_hand','reserved','incoming','safety_stock','daily_demand'}
  if not required.issubset(set(reader.fieldnames or [])):return bad('CSV missing required columns: '+', '.join(sorted(required-set(reader.fieldnames or []))))
  imported=[]
  for i,r in enumerate(reader,2):
   vals={k:float(r[k]) for k in required if k not in ('product_id','location_id')};
   if any(v<0 for v in vals.values()):return bad(f'Row {i}: quantities and demand must be non-negative')
   imported.append(r)
  return jsonify({'validated_rows':len(imported),'imported':False,'message':'CSV validated successfully. CSV validation passed; importing these rows is not enabled.'}),200
 except (UnicodeDecodeError,ValueError,TypeError) as e:return bad(f'Invalid CSV: {e}')
