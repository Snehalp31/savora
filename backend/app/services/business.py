from datetime import date

def surplus_rows(inventory, horizon=14, demand_multiplier=1.0):
    if not 1 <= int(horizon) <= 90: raise ValueError('horizon must be between 1 and 90 days')
    result=[]
    for x in inventory:
        vals=[x.get(k,0) for k in ('on_hand','reserved','incoming','safety_stock','daily_demand')]
        if any(float(v)<0 for v in vals): raise ValueError('Inventory quantities and demand cannot be negative')
        available=max(0,int(x['on_hand']-x['reserved']+x['incoming']))
        demand=max(0,round(float(x['daily_demand'])*horizon*demand_multiplier))
        closing=available-demand
        surplus=max(0,closing-int(x['safety_stock']))
        days=int(x.get('days_to_deadline',999))
        if x.get('batch_status')!='eligible' or not x.get('handling_verified',False): risk='Requires review'
        elif surplus and days<=7: risk='Critical'
        elif surplus and days<=14: risk='High'
        elif surplus and surplus>=max(30,available*.25): risk='Moderate'
        elif surplus: risk='Low'
        else: risk='No projected surplus'
        result.append({**x,'horizon_days':int(horizon),'available':available,'expected_demand':demand,'projected_closing':closing,'projected_surplus':surplus,'risk':risk,'calculation':f'{x["on_hand"]} on hand − {x["reserved"]} reserved + {x["incoming"]} incoming − {demand} expected demand − {x["safety_stock"]} safety stock = {surplus} projected surplus units (floored at zero)'})
    return result

def redistribution_plan(rows, transport_cost_per_unit=0.08, capacity=1000):
    # Transparent greedy feasible plan: no source below safety stock; only eligible batches.
    sources=[]; needs=[]
    for x in rows:
        avail=max(0,int(x['on_hand']-x['reserved']-x['safety_stock']))
        need=max(0,int(x['expected_demand']-(x['on_hand']-x['reserved'])))
        if x.get('batch_status')=='eligible' and x.get('handling_verified'):
            if x.get('projected_surplus',0)>0: sources.append((x, min(avail,int(x['projected_surplus']))))
            if need: needs.append((x,need))
    plan=[]; remaining_capacity=int(capacity)
    for dst,need in needs:
      for src,available in sources:
        if src['product_id']!=dst['product_id'] or src['location_id']==dst['location_id'] or available<=0 or remaining_capacity<=0: continue
        q=min(need,available,remaining_capacity)
        if q<=0: continue
        plan.append({'source_location':src['location_name'],'destination_location':dst['location_name'],'product':src['product_name'],'batch_id':src['batch_id'],'quantity':q,'transport_cost':round(q*float(transport_cost_per_unit),2),'transit_days':2,'destination_need':need,'source_remaining':src['on_hand']-src['reserved']-q,'deadline_days':src['days_to_deadline'],'status':'Proposed','reason':f'{src["location_name"]} has {available} releasable surplus units; {dst["location_name"]} has projected demand for this product.'})
        sources[sources.index((src,available))]=(src,available-q); need-=q; remaining_capacity-=q
        if need<=0 or remaining_capacity<=0: break
    return plan

def discount_scenarios(product, inventory_units, demand_units, discount_steps=(0,5,10,15,20,25,30), elasticity=1.4, min_margin=0.12):
    price=float(product['price']); cost=float(product.get('unit_cost') or 0); rows=[]
    for d in discount_steps:
        selling=price*(1-d/100)
        if cost and selling < cost*(1+min_margin): continue
        # Explicit scenario curve, not a trained price elasticity model.
        expected=min(int(inventory_units),max(0,round(demand_units*(1+elasticity*d/100))))
        rows.append({'discount_pct':d,'selling_price':round(selling,2),'expected_units_sold':expected,'expected_revenue':round(selling*expected,2),'estimated_contribution':round((selling-cost)*expected,2) if cost else None,'expected_remaining':max(0,int(inventory_units)-expected),'method':'Configurable scenario model; not trained price-response ML'})
    return rows

def recovery_allocate(rows, partners, capacity_override=None):
    allocations=[]; remaining_by_partner={p['id']:int(capacity_override if capacity_override is not None else p['capacity']) for p in partners if p.get('active')}
    for x in sorted(rows,key=lambda a:(a.get('days_to_deadline',999),-a.get('projected_surplus',0))):
        q=int(x.get('projected_surplus',0))
        if q<=0: continue
        if x.get('batch_status')!='eligible' or not x.get('handling_verified'):
            allocations.append({'product':x['product_name'],'location':x['location_name'],'batch_id':x['batch_id'],'quantity':q,'channel':'Unallocated','status':'Requires Review','reason':'Batch eligibility or handling information is missing/unverified.'}); continue
        left=q
        for p in partners:
            if not p.get('active') or not p.get('verified') or x['category'] not in p.get('categories',[]): continue
            cap=remaining_by_partner.get(p['id'],0); take=min(left,cap)
            if take:
                allocations.append({'product':x['product_name'],'location':x['location_name'],'batch_id':x['batch_id'],'quantity':take,'channel':'Donation / recovery','partner':p['name'],'status':'Proposed','reason':'Eligible category and verified partner with available capacity.'})
                remaining_by_partner[p['id']]-=take; left-=take
            if left<=0: break
        if left: allocations.append({'product':x['product_name'],'location':x['location_name'],'batch_id':x['batch_id'],'quantity':left,'channel':'Unallocated','status':'Unallocated','reason':'No eligible partner capacity remains; no unsafe fallback is assumed.'})
    return {'allocations':allocations,'partner_capacity_remaining':remaining_by_partner,'proposed_units':sum(a['quantity'] for a in allocations if a['status']=='Proposed'),'unallocated_units':sum(a['quantity'] for a in allocations if a['channel']=='Unallocated')}
