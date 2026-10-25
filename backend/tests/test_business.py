import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.business import surplus_rows,redistribution_plan,recovery_allocate,discount_scenarios

def sample(**kw):
 x={'id':1,'product_id':1,'product_name':'starter Snack','category':'Snacks','location_id':1,'location_name':'A','batch_id':'B1','on_hand':100,'reserved':10,'incoming':20,'safety_stock':10,'daily_demand':5,'price':30,'unit_cost':15,'days_to_deadline':30,'batch_status':'eligible','handling_verified':True};x.update(kw);return x

def test_surplus_calculation_includes_incoming_reservations_and_buffer():
 r=surplus_rows([sample()],10)[0]
 assert r['available']==110 and r['expected_demand']==50 and r['projected_surplus']==50

def test_zero_inventory_no_surplus():
 r=surplus_rows([sample(on_hand=0,reserved=0,incoming=0,daily_demand=0)],7)[0]
 assert r['projected_surplus']==0

def test_invalid_negative_quantity_rejected():
 try:surplus_rows([sample(reserved=-1)],14)
 except ValueError:pass
 else:assert False,'negative quantity should fail'

def test_review_batch_is_not_eligible_for_recovery():
 x=sample(batch_status='requires_review',handling_verified=False)
 result=recovery_allocate(surplus_rows([x],7),[{'id':1,'name':'Partner','capacity':100,'verified':True,'active':True,'categories':['Snacks']}])
 assert result['allocations'][0]['status']=='Requires Review'

def test_recovery_respects_partner_capacity():
 x=sample(on_hand=300,reserved=0,incoming=0,daily_demand=1,safety_stock=0)
 result=recovery_allocate(surplus_rows([x],7),[{'id':1,'name':'Partner','capacity':10,'verified':True,'active':True,'categories':['Snacks']}])
 assert sum(a['quantity'] for a in result['allocations'] if a['status']=='Proposed')<=10

def test_redistribution_respects_route_capacity():
 src=sample(projected_surplus=100)
 dst=sample(id=2,location_id=2,location_name='B',on_hand=0,daily_demand=10,projected_surplus=0,expected_demand=50)
 plan=redistribution_plan([src,dst],capacity=5)
 assert sum(x['quantity'] for x in plan)<=5

def test_discount_scenarios_respect_margin_floor():
 p={'price':30,'unit_cost':25}
 rows=discount_scenarios(p,100,40,min_margin=.1)
 assert all(r['selling_price']>=27 for r in rows)
