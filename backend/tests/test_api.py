import sys, os
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SAVORA_DB_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("ADMIN_EMAIL", "admin@savora.local")
    monkeypatch.setenv("ADMIN_PASSWORD", "TestPassword123!")
    app=create_app({"TESTING":True})
    c=app.test_client()
    login=c.post('/api/auth/login',json={"email":"admin@savora.local","password":"TestPassword123!"})
    assert login.status_code==200
    c.environ_base["HTTP_AUTHORIZATION"]="Bearer "+login.json["token"]
    return c

def test_health_and_storage_meta(client):
    assert client.get('/health').status_code==200
    assert client.get('/api/meta').json['storage_mode']=='sqlite'
    assert client.get('/api/meta').json['database_connected'] is True

def test_business_routes_require_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("SAVORA_DB_PATH", str(tmp_path / "auth.sqlite3"))
    c=create_app({"TESTING":True}).test_client()
    assert c.get('/api/products').status_code==401
    assert c.get('/api/meta').status_code==200

def test_surplus_endpoint_returns_items(client):
    r=client.get('/api/surplus?horizon=14')
    assert r.status_code==200 and 'items' in r.json

def test_simulation_does_not_mutate_live_inventory(client):
    before=client.get('/api/inventory').json[0]['on_hand']
    r=client.post('/api/simulations/run',json={'demand_change_pct':50,'inventory_adjustment':50})
    after=client.get('/api/inventory').json[0]['on_hand']
    assert r.status_code==200 and r.json['simulation_only'] is True and before==after

def test_invalid_simulation_rejected(client):
    assert client.post('/api/simulations/run',json={'demand_change_pct':500}).status_code==400

def test_anomaly_status_persists_in_process(client):
    r=client.patch('/api/anomalies/1/status',json={'status':'Investigating'})
    assert r.status_code==200 and r.json['status']=='Investigating'

def test_product_creation_persists_in_sqlite(client):
    r=client.post('/api/products',json={'name':'Persistence Check Product','category':'Snacks','price':12.5,'unit_cost':7.0,'sku':'TEST-PERSISTENCE-CHECK'})
    assert r.status_code==201
    pid=r.json['id']
    assert any(x['id']==pid for x in client.get('/api/products').json)
    assert client.delete(f'/api/products/{pid}').status_code==204

def test_inventory_and_sales_records_are_saved(client):
    x=client.get('/api/inventory').json[0]
    r=client.post('/api/inventory',json={'product_id':x['product_id'],'location_id':x['location_id'],
      'batch_id':'TEST-BATCH-PERSISTENCE','on_hand':20,'reserved':2,'incoming':0,'safety_stock':3,
      'daily_demand':1.5,'days_to_deadline':30,'batch_status':'eligible','handling_verified':True})
    assert r.status_code==201
    assert any(y['batch_id']=='TEST-BATCH-PERSISTENCE' for y in client.get('/api/inventory').json)
    sale=client.post('/api/sales',json={'product_id':x['product_id'],'location_id':x['location_id'],
      'date':'2099-01-01','units_sold':4,'price':12.5})
    assert sale.status_code==201
    assert any(y['date']=='2099-01-01' and y['units_sold']==4 for y in client.get('/api/sales').json)
