"""Deterministic fictional dataset used only in explicitly labelled starter mode."""
import numpy as np, pandas as pd
from datetime import date, timedelta
RNG = np.random.default_rng(20261015)
CATEGORIES = ['Snacks','Biscuits','Namkeen','Bakery','Packaged Staples']
PRODUCTS = [{'id':i+1,'sku':f'SKU-{i+1:03}','name':n,'category':CATEGORIES[i%5], 'price':float(p),'unit_cost':float(round(p*.58,2)),'unit':'packs','active':True} for i,(n,p) in enumerate([
('Masala Rings',35),('Salted Crisps',30),('Classic Cookies',45),('Butter Biscuits',25),('Spicy Sev',40),('Mini Bhakarwadi',55),('Rusk Toast',35),('Oat Biscuits',60),('Roasted Chana',28),('Cream Crackers',32),('Chilli Chips',20),('Jeera Cookies',38),('Sweet Shankarpali',50),('Banana Chips',45),('Khari Puff',40),('Poha Pack',48),('Upma Mix',42),('Atta Noodles',25),('Multigrain Crackers',65),('Coconut Cookies',55),('Peanut Chikki',30),('Baked Mathri',42),('Wheat Toast',34),('Rice Flour Pack',52),('Corn Puffs',25)])]
LOCATIONS=[{'id':i+1,'name':n,'region':r,'capacity':cap,'active':True} for i,(n,r,cap) in enumerate([('Pune Central DC','West',15000),('Nashik Distribution Hub','West',9500),('Mumbai East Warehouse','West',18000),('Kolhapur Regional Store','South-West',7500),('Nagpur Fulfilment Centre','East',12000),('Aurangabad Distributor','Central',8000)])]
PARTNERS=[{'id':1,'name':'Green Plate Community Kitchen','type':'Community kitchen','location_id':1,'capacity':180,'verified':True,'active':True,'categories':CATEGORIES[:4]}, {'id':2,'name':'Second Harvest Network','type':'Recovery NGO','location_id':3,'capacity':260,'verified':True,'active':True,'categories':['Snacks','Biscuits','Namkeen']}, {'id':3,'name':'Local Food Link (Review required)','type':'Food recovery partner','location_id':4,'capacity':100,'verified':False,'active':True,'categories':['Bakery','Packaged Staples']}]
def get_products(): return [dict(x) for x in PRODUCTS]
def get_locations(): return [dict(x) for x in LOCATIONS]
def get_partners(): return [dict(x) for x in PARTNERS]
def get_inventory():
    out=[]; today=date.today()
    for p in PRODUCTS:
      for l in LOCATIONS:
        qty=int(RNG.integers(80,420)); reserved=int(qty*RNG.uniform(.03,.12)); incoming=int(RNG.choice([0,0,0,40,80])); demand=int(RNG.integers(35,180))
        # deterministic seeded examples with visible risk and opportunity
        if p['id'] in (2,5,13) and l['id']==1: qty*=2
        if p['id'] in (1,7,10) and l['id']==4: demand*=2
        days=int(RNG.choice([5,9,14,21,30,45,60,75,90]))
        out.append({'id':len(out)+1,'product_id':p['id'],'product_name':p['name'],'sku':p['sku'],'category':p['category'],'location_id':l['id'],'location_name':l['name'],'batch_id':f'B-{p["id"]:03}-{l["id"]:02}','on_hand':qty,'reserved':reserved,'incoming':incoming,'safety_stock':int(demand*.2),'daily_demand':round(demand/7,2),'price':p['price'],'unit_cost':p['unit_cost'],'days_to_deadline':days,'batch_status':'eligible' if days>10 else 'requires_review','handling_verified':days>10,'updated_at':date.today().isoformat()})
    return out
INVENTORY=get_inventory()
def get_sales(days=180):
    rows=[]; today=date.today()
    for p in PRODUCTS:
      for l in LOCATIONS:
       base=float(RNG.uniform(8,35))
       for d in range(days):
        dt=today-timedelta(days=days-d)
        season=1+.18*np.sin(d/20)+(.15 if dt.weekday()>=5 else 0)
        units=max(0,int(RNG.poisson(base*season)))
        if p['id']==5 and l['id']==1 and d>days-20: units=max(0,int(units*.3))
        rows.append({'date':dt.isoformat(),'product_id':p['id'],'location_id':l['id'],'units_sold':units,'price':p['price']})
    return rows
SALES=get_sales()
