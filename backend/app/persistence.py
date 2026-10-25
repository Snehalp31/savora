import os, sqlite3, hashlib, secrets, hmac
from pathlib import Path
from flask import current_app

def db_path():
    configured=os.getenv("SAVORA_DB_PATH")
    return configured or str(Path(__file__).resolve().parents[1] / "savora.sqlite3")

def connect():
    c=sqlite3.connect(db_path()); c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT UNIQUE NOT NULL,full_name TEXT NOT NULL,password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'admin',active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT,sku TEXT UNIQUE NOT NULL,name TEXT NOT NULL,category TEXT NOT NULL,unit TEXT NOT NULL DEFAULT 'packs',price REAL NOT NULL,unit_cost REAL NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS locations(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,region TEXT,address TEXT,capacity INTEGER NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS partners(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,type TEXT NOT NULL,location_id INTEGER,capacity INTEGER NOT NULL DEFAULT 0,verified INTEGER NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 0,categories TEXT NOT NULL DEFAULT '',contact_details TEXT,FOREIGN KEY(location_id) REFERENCES locations(id));
        CREATE TABLE IF NOT EXISTS company_profile(id INTEGER PRIMARY KEY CHECK(id=1),name TEXT NOT NULL,industry TEXT NOT NULL,website TEXT NOT NULL,contact_email TEXT NOT NULL,address TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
        """)
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0]==0:
            email=os.getenv("ADMIN_EMAIL","admin@savora.local").lower()
            password=os.getenv("ADMIN_PASSWORD","ChangeMe123!")
            c.execute("INSERT INTO users(email,full_name,password_hash,role) VALUES(?,?,?,?)",(email,"Savora Administrator",hash_password(password),"admin"))
        if c.execute("SELECT COUNT(*) FROM company_profile").fetchone()[0]==0:
            c.execute("INSERT INTO company_profile VALUES(1,'Savora','Food supply chain','', '', '')")
        c.commit()

def rowdict(row):
    return dict(row) if row else None

def hash_password(password):
    salt=secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,310000)
    return 'pbkdf2_sha256$310000$'+salt.hex()+'$'+digest.hex()

def check_password(password, stored):
    # Migrate the original local SHA-256 hash format after successful login.
    if stored.startswith('pbkdf2_sha256$'):
        try:
            _,iterations,salt,digest=stored.split('$')
            calculated=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),int(iterations)).hex()
            return hmac.compare_digest(calculated,digest)
        except (ValueError,TypeError): return False
    return hmac.compare_digest(hashlib.sha256(password.encode()).hexdigest(),stored)

def verify_login(email,password):
    with connect() as c:
        u=c.execute("SELECT * FROM users WHERE lower(email)=lower(?) AND active=1",(email,)).fetchone()
        if not u or not check_password(password,u["password_hash"]): return None
        if not u["password_hash"].startswith('pbkdf2_sha256$'):
            c.execute("UPDATE users SET password_hash=? WHERE id=?",(hash_password(password),u["id"]))
        token=secrets.token_urlsafe(32)
        c.execute("INSERT INTO sessions(token,user_id) VALUES(?,?)",(token,u["id"])); c.commit()
        return {"token":token,"user":{"id":u["id"],"email":u["email"],"full_name":u["full_name"],"role":u["role"]}}

def current_user(token):
    if not token:return None
    with connect() as c:
        r=c.execute("SELECT users.id,users.email,users.full_name,users.role FROM sessions JOIN users ON users.id=sessions.user_id WHERE token=? AND users.active=1",(token,)).fetchone()
        return rowdict(r)

def logout(token):
    with connect() as c:c.execute("DELETE FROM sessions WHERE token=?",(token,));c.commit()

def list_rows(table):
    if table not in ("products","locations","partners"): raise ValueError("invalid table")
    with connect() as c:return [rowdict(x) for x in c.execute(f"SELECT * FROM {table} ORDER BY id")]

def insert_row(table, values):
    allowed={"products":{"sku","name","category","unit","price","unit_cost","active"},"locations":{"code","name","region","address","capacity","active"},"partners":{"name","type","location_id","capacity","verified","active","categories","contact_details"}}
    if table not in allowed: raise ValueError("invalid table")
    values={k:v for k,v in values.items() if k in allowed[table]}
    cols=list(values)
    with connect() as c:
        cur=c.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",[values[k] for k in cols]); c.commit()
        return rowdict(c.execute(f"SELECT * FROM {table} WHERE id=?",(cur.lastrowid,)).fetchone())

def update_profile(values):
    allowed={"name","industry","website","contact_email","address"}
    values={k:v for k,v in values.items() if k in allowed}
    if not values:return get_profile()
    with connect() as c:
        c.execute("UPDATE company_profile SET "+",".join(f"{k}=?" for k in values)+" WHERE id=1",list(values.values()));c.commit()
    return get_profile()

def get_profile():
    with connect() as c:return rowdict(c.execute("SELECT * FROM company_profile WHERE id=1").fetchone())


def seed_reference_data(products, locations, partners):
    with connect() as c:
        if c.execute("SELECT COUNT(*) FROM products").fetchone()[0]==0:
            for p in products:
                c.execute("INSERT INTO products(id,sku,name,category,unit,price,unit_cost,active) VALUES(?,?,?,?,?,?,?,?)",(p['id'],p['sku'],p['name'],p['category'],p.get('unit','packs'),p['price'],p.get('unit_cost',0),int(bool(p.get('active',True)))))
        if c.execute("SELECT COUNT(*) FROM locations").fetchone()[0]==0:
            for i,l in enumerate(locations,1):
                c.execute("INSERT INTO locations(id,code,name,region,address,capacity,active) VALUES(?,?,?,?,?,?,?)",(l.get('id',i),l.get('code',f'LOC-{i:03}'),l['name'],l.get('region',''),l.get('address',''),int(l.get('capacity',0)),int(bool(l.get('active',True)))))
        if c.execute("SELECT COUNT(*) FROM partners").fetchone()[0]==0:
            for i,p in enumerate(partners,1):
                c.execute("INSERT INTO partners(id,name,type,location_id,capacity,verified,active,categories,contact_details) VALUES(?,?,?,?,?,?,?,?,?)",(p.get('id',i),p['name'],p.get('type','Recovery partner'),p.get('location_id'),int(p.get('capacity',0)),int(bool(p.get('verified',False))),int(bool(p.get('active',False))),','.join(p.get('categories',[])),p.get('contact_details','')))
        c.commit()


def init_operational_tables(inventory_rows, sales_rows):
    """Create persistent inventory and sales tables; seed once for backward-compatible startup."""
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS inventory_records(
          id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL, location_id INTEGER NOT NULL,
          batch_id TEXT NOT NULL UNIQUE, on_hand INTEGER NOT NULL DEFAULT 0, reserved INTEGER NOT NULL DEFAULT 0,
          incoming INTEGER NOT NULL DEFAULT 0, safety_stock INTEGER NOT NULL DEFAULT 0,
          daily_demand REAL NOT NULL DEFAULT 0, days_to_deadline INTEGER NOT NULL DEFAULT 999,
          batch_status TEXT NOT NULL DEFAULT 'requires_review', handling_verified INTEGER NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS sales_records(
          id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL, location_id INTEGER NOT NULL,
          sold_on TEXT NOT NULL, units_sold INTEGER NOT NULL CHECK(units_sold >= 0), unit_price REAL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(product_id, location_id, sold_on));
        """)
        if c.execute("SELECT COUNT(*) FROM inventory_records").fetchone()[0] == 0:
            for x in inventory_rows:
                c.execute("""INSERT INTO inventory_records
                (id,product_id,location_id,batch_id,on_hand,reserved,incoming,safety_stock,daily_demand,days_to_deadline,batch_status,handling_verified,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (x['id'],x['product_id'],x['location_id'],x['batch_id'],x['on_hand'],x['reserved'],x['incoming'],x['safety_stock'],x['daily_demand'],x['days_to_deadline'],x['batch_status'],int(bool(x['handling_verified'])),x.get('updated_at','')))
        if c.execute("SELECT COUNT(*) FROM sales_records").fetchone()[0] == 0:
            for x in sales_rows:
                c.execute("""INSERT OR IGNORE INTO sales_records(product_id,location_id,sold_on,units_sold,unit_price)
                VALUES(?,?,?,?,?)""",(x['product_id'],x['location_id'],x.get('date') or x.get('sold_on'),int(x['units_sold']),x.get('price')))
        c.commit()

def list_inventory_records():
    with connect() as c:
        rows=c.execute("""SELECT i.*,p.name product_name,p.sku,p.category,p.price,p.unit_cost,l.name location_name
        FROM inventory_records i LEFT JOIN products p ON p.id=i.product_id
        LEFT JOIN locations l ON l.id=i.location_id ORDER BY i.id""").fetchall()
        return [dict(r) for r in rows]

def list_sales_records(product_id=None, location_id=None, limit=20000):
    sql="""SELECT s.id,s.product_id,s.location_id,s.sold_on AS date,s.units_sold,s.unit_price AS price
    FROM sales_records s WHERE 1=1"""
    args=[]
    if product_id is not None: sql+=" AND s.product_id=?"; args.append(int(product_id))
    if location_id is not None: sql+=" AND s.location_id=?"; args.append(int(location_id))
    sql+=" ORDER BY s.sold_on LIMIT ?"; args.append(int(limit))
    with connect() as c: return [dict(r) for r in c.execute(sql,args).fetchall()]

def create_inventory_record(data):
    required=('product_id','location_id','batch_id','on_hand')
    if any(data.get(k) is None for k in required): raise ValueError('product_id, location_id, batch_id and on_hand are required')
    ints=('product_id','location_id','on_hand','reserved','incoming','safety_stock','days_to_deadline')
    vals={k:data[k] for k in ints if k in data}
    for k,v in vals.items():
        vals[k]=int(v)
        if vals[k]<0: raise ValueError(f'{k} cannot be negative')
    if vals.get('reserved',0)>vals.get('on_hand',int(data['on_hand'])): raise ValueError('reserved cannot exceed on_hand')
    allowed={'product_id','location_id','batch_id','on_hand','reserved','incoming','safety_stock','daily_demand','days_to_deadline','batch_status','handling_verified'}
    vals={k:data[k] for k in allowed if k in data}
    vals.setdefault('reserved',0); vals.setdefault('incoming',0); vals.setdefault('safety_stock',0); vals.setdefault('daily_demand',0)
    vals.setdefault('days_to_deadline',999); vals.setdefault('batch_status','requires_review'); vals.setdefault('handling_verified',0)
    vals['handling_verified']=int(bool(vals['handling_verified']))
    with connect() as c:
        cur=c.execute(f"INSERT INTO inventory_records ({','.join(vals)}) VALUES ({','.join('?' for _ in vals)})",list(vals.values()))
        c.commit()
        return cur.lastrowid

def create_sales_record(data):
    required=('product_id','location_id','date','units_sold')
    if any(data.get(k) is None for k in required): raise ValueError('product_id, location_id, date and units_sold are required')
    units=int(data['units_sold'])
    if units<0: raise ValueError('units_sold cannot be negative')
    with connect() as c:
        cur=c.execute("INSERT INTO sales_records(product_id,location_id,sold_on,units_sold,unit_price) VALUES(?,?,?,?,?)",
          (int(data['product_id']),int(data['location_id']),str(data['date']),units,data.get('price')))
        c.commit()
        return cur.lastrowid
