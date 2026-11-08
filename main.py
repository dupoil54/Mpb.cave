import os, sqlite3, hashlib, secrets, shutil
from datetime import datetime, date
from calendar import monthrange
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
# En production Render, la base doit impérativement être placée sur le disque persistant.
# Le chemin /var/data est le point de montage conseillé pour un Persistent Disk Render.
if os.getenv('DATABASE_PATH'):
    DB=os.path.abspath(os.environ['DATABASE_PATH'])
elif os.path.isdir('/var/data'):
    DB='/var/data/cave.db'
else:
    DB=os.path.join(BASE_DIR,'cave.db')
if os.getenv('RENDER_SERVICE_ID') and not (DB == '/var/data/cave.db' or DB.startswith('/var/data/')):
    raise RuntimeError('Stockage non persistant détecté : configurez un Persistent Disk Render monté sur /var/data et DATABASE_PATH=/var/data/cave.db.')
os.makedirs(os.path.dirname(DB) or '.', exist_ok=True)
BACKUP_DIR=os.path.join(os.path.dirname(DB) or '.', 'backups')
# Migration douce : si l'ancienne base locale existe encore au premier démarrage
# sur le disque persistant, la copier sans écraser une base déjà présente.
LEGACY_DB=os.path.join(BASE_DIR,'cave.db')
if os.path.abspath(DB) != os.path.abspath(LEGACY_DB) and not os.path.exists(DB) and os.path.isfile(LEGACY_DB):
    try:
        old_conn=sqlite3.connect(LEGACY_DB,timeout=30)
        new_conn=sqlite3.connect(DB,timeout=30)
        try: old_conn.backup(new_conn)
        finally: new_conn.close(); old_conn.close()
    except Exception as exc:
        raise RuntimeError(f'Impossible de migrer automatiquement l’ancienne base vers le disque persistant : {exc}')
app=FastAPI(title='Cave de Tibati - Gestion')
ROLES={'admin':'Administrateur','shareholder':'Actionnaire','service':'Service','cashier':'Caisse'}
ALL={'admin','shareholder'}
def db():
    c=sqlite3.connect(DB, timeout=30)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=30000')
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA synchronous=FULL')
    return c
def now(): return datetime.now().isoformat(timespec='seconds')
def hashpin(pin,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.pbkdf2_hmac('sha256',pin.encode(),salt.encode(),180000).hex()
def checkpin(pin,stored):
    try:
        salt,h=stored.split(':'); return secrets.compare_digest(hashlib.pbkdf2_hmac('sha256',pin.encode(),salt.encode(),180000).hex(),h)
    except Exception: return False
def cols(c,table): return {r['name'] for r in c.execute(f'PRAGMA table_info({table})')}
def init():
    c=db(); c.executescript('''
    CREATE TABLE IF NOT EXISTS employees(id INTEGER PRIMARY KEY,name TEXT NOT NULL,role TEXT NOT NULL,pin_hash TEXT NOT NULL,active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,employee_id INTEGER,created TEXT,FOREIGN KEY(employee_id) REFERENCES employees(id));
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,code TEXT UNIQUE,name TEXT,category TEXT,supplier TEXT,cost REAL DEFAULT 0,price REAL DEFAULT 0,stock REAL DEFAULT 0,alert REAL DEFAULT 5,target REAL DEFAULT 20,active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS tables_room(id INTEGER PRIMARY KEY,name TEXT UNIQUE,active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,table_id INTEGER,customer TEXT,status TEXT DEFAULT 'pending',source TEXT DEFAULT 'staff',token TEXT,created TEXT,employee_id INTEGER,paid REAL DEFAULT 0,credit REAL DEFAULT 0,FOREIGN KEY(table_id) REFERENCES tables_room(id));
    CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY,order_id INTEGER,product_id INTEGER,qty REAL,unit_price REAL,unit_cost REAL,category TEXT DEFAULT 'Autres',FOREIGN KEY(order_id) REFERENCES orders(id),FOREIGN KEY(product_id) REFERENCES products(id));
    CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY,order_id INTEGER,amount REAL,method TEXT,created TEXT,employee_id INTEGER);
    CREATE TABLE IF NOT EXISTS credits(id INTEGER PRIMARY KEY,customer TEXT,order_id INTEGER,amount REAL,balance REAL,created TEXT,note TEXT);
    CREATE TABLE IF NOT EXISTS credit_payments(id INTEGER PRIMARY KEY,credit_id INTEGER,amount REAL,created TEXT,employee_id INTEGER);
    CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY,product_id INTEGER,kind TEXT,qty REAL,note TEXT,created TEXT,employee_id INTEGER);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,employee_id INTEGER,action TEXT,details TEXT,created TEXT);
    CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY,value TEXT);
    CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY,employee_id INTEGER,day TEXT,status TEXT DEFAULT 'present',approved INTEGER DEFAULT 0,approved_by INTEGER,created TEXT,UNIQUE(employee_id,day));
    CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY,label TEXT,amount REAL,category TEXT,day TEXT,note TEXT,employee_id INTEGER,created TEXT);
    ''')
    # migrations non destructives
    # Conserver la catégorie au moment de la vente : les anciens rapports restent exacts
    # même si le nom ou la catégorie de l'article est modifié ultérieurement.
    if 'category' not in cols(c,'order_items'):
        c.execute("ALTER TABLE order_items ADD COLUMN category TEXT DEFAULT 'Autres'")
        c.execute("UPDATE order_items SET category=COALESCE((SELECT NULLIF(p.category,'') FROM products p WHERE p.id=order_items.product_id),'Autres')")
    ec=cols(c,'employees')
    if 'pin_changed' not in ec: c.execute('ALTER TABLE employees ADD COLUMN pin_changed INTEGER DEFAULT 0')
    if 'monthly_salary' not in ec: c.execute('ALTER TABLE employees ADD COLUMN monthly_salary REAL DEFAULT 0')
    # Normalise les anciens intitulés de poste de la version précédente.
    c.execute("UPDATE employees SET role='service' WHERE lower(role) IN ('serveur','serveuse','service')")
    c.execute("UPDATE employees SET role='cashier' WHERE lower(role) IN ('caisse','caissier','caissiere','cashier')")
    c.execute("UPDATE employees SET role='shareholder' WHERE lower(role) IN ('actionnaire','shareholder')")
    c.execute("UPDATE employees SET role='admin' WHERE lower(role) IN ('administrateur','admin')")
    if c.execute('SELECT count(*) FROM employees').fetchone()[0]==0:
        c.execute('INSERT INTO employees(name,role,pin_hash,pin_changed) VALUES(?,?,?,0)',('Administrateur','admin',hashpin('1234')))
    marker=c.execute("SELECT value FROM app_settings WHERE key='manual_stock_mode_v1'").fetchone()
    if not marker:
        c.execute('UPDATE products SET active=0,stock=0')
        c.execute("INSERT INTO app_settings(key,value) VALUES('manual_stock_mode_v1','1')")
    c.commit(); c.close()
init()
def employee(auth):
    c=db(); row=c.execute('SELECT e.* FROM sessions s JOIN employees e ON e.id=s.employee_id WHERE s.token=? AND e.active=1',(auth or '',)).fetchone(); c.close()
    if not row: raise HTTPException(401,'Session invalide. Reconnectez-vous.')
    return row
def allow(e,*roles):
    if e['role'] not in roles: raise HTTPException(403,'Vous ne disposez pas de l’autorisation nécessaire.')
def admin_or_share(e): allow(e,'admin','shareholder')
def log(e,action,details=''):
    c=db(); c.execute('INSERT INTO audit(employee_id,action,details,created) VALUES(?,?,?,?)',(e['id'] if e else None,action,details,now())); c.commit(); c.close()
class Login(BaseModel): pin:str; role:str
class PinChange(BaseModel): old_pin:str; new_pin:str
class EmployeeIn(BaseModel): name:str; role:str; pin:str; monthly_salary:float=0
class EmployeeUpdate(BaseModel): name:Optional[str]=None; role:Optional[str]=None; monthly_salary:Optional[float]=None; active:Optional[bool]=None; new_pin:Optional[str]=None
class ProductIn(BaseModel): name:str; stock:float; code:Optional[str]=None; category:str='Autres'; supplier:str=''; cost:float=0; price:float=0; alert:float=5; target:float=20
class TableIn(BaseModel): name:str
class ItemIn(BaseModel): product_id:int; qty:float
class OrderIn(BaseModel): table_id:Optional[int]=None; customer:str='Client'; items:List[ItemIn]; source:str='staff'
class PayIn(BaseModel): amount:float; method:str='Espèces'
class CreditPay(BaseModel): amount:float
class MoveIn(BaseModel): product_id:int; qty:float; kind:str='in'; note:str=''
class AttendanceIn(BaseModel): employee_id:int; day:str; status:str='present'
class ExpenseIn(BaseModel): label:str; amount:float; category:str='Autres'; day:str; note:str=''
@app.get('/')
def home(): return FileResponse(os.path.join(BASE_DIR,'static','index.html'))
@app.get('/api/roles')
def roles(): return [{'key':k,'label':v} for k,v in ROLES.items()]
@app.post('/api/login')
def login(x:Login):
    if x.role not in ROLES: raise HTTPException(400,'Poste invalide')
    c=db(); rows=c.execute('SELECT * FROM employees WHERE active=1 AND role=?',(x.role,)).fetchall()
    for e in rows:
        if checkpin(x.pin,e['pin_hash']):
            token=secrets.token_urlsafe(32); c.execute('INSERT INTO sessions VALUES(?,?,?)',(token,e['id'],now())); c.commit(); c.close(); log(e,'CONNEXION','Connexion PIN')
            return {'token':token,'must_change_pin':not bool(e['pin_changed']),'employee':{'id':e['id'],'name':e['name'],'role':e['role'],'monthly_salary':e['monthly_salary']}}
    c.close(); raise HTTPException(401,'PIN incorrect pour ce poste')
@app.get('/api/me')
def current_user(authorization:Optional[str]=Header(None)):
    e=employee(authorization); return {'employee':{'id':e['id'],'name':e['name'],'role':e['role'],'monthly_salary':e['monthly_salary']},'must_change_pin':not bool(e['pin_changed'])}
@app.post('/api/change-pin')
def change_pin(x:PinChange,authorization:Optional[str]=Header(None)):
    e=employee(authorization)
    if not checkpin(x.old_pin,e['pin_hash']): raise HTTPException(400,'Ancien PIN incorrect')
    if len(x.new_pin)<4 or not x.new_pin.isdigit(): raise HTTPException(400,'Le nouveau PIN doit contenir au moins 4 chiffres')
    c=db(); c.execute('UPDATE employees SET pin_hash=?,pin_changed=1 WHERE id=?',(hashpin(x.new_pin),e['id'])); c.commit(); c.close(); log(e,'CHANGEMENT_PIN'); return {'ok':True}
@app.post('/api/logout')
def logout(authorization:Optional[str]=Header(None)):
    e=employee(authorization); c=db(); c.execute('DELETE FROM sessions WHERE token=?',(authorization,)); c.commit(); c.close(); log(e,'DECONNEXION'); return {'ok':True}
@app.get('/api/dashboard')
def dashboard(authorization:Optional[str]=Header(None)):
    e=employee(authorization); c=db(); p=c.execute('SELECT count(*) n,sum(CASE WHEN stock<=0 THEN 1 ELSE 0 END) ruptures,sum(CASE WHEN stock>0 AND stock<=alert THEN 1 ELSE 0 END) alertes,sum(stock*cost) valeur FROM products WHERE active=1').fetchone()
    o=c.execute("SELECT count(*) n,coalesce(sum((SELECT sum(qty*unit_price) FROM order_items i WHERE i.order_id=o.id)),0) total FROM orders o WHERE o.status IN ('pending','served')").fetchone(); cr=c.execute('SELECT coalesce(sum(balance),0) total FROM credits WHERE balance>0').fetchone(); c.close()
    if e['role'] not in ALL:
        return {'open_orders':dict(o),'credits':cr['total'] if e['role']=='cashier' else 0,'role':e['role']}
    return {'products':dict(p),'open_orders':dict(o),'credits':cr['total'],'role':e['role']}
@app.get('/api/order-products')
def order_products(authorization:Optional[str]=Header(None)):
    employee(authorization); c=db(); r=c.execute('SELECT id,name,category,price,stock FROM products WHERE active=1 ORDER BY category,name').fetchall(); c.close(); return [dict(x) for x in r]
@app.get('/api/products')
def products(authorization:Optional[str]=Header(None)):
    e=employee(authorization); allow(e,'admin','shareholder'); c=db(); r=c.execute('SELECT * FROM products WHERE active=1 ORDER BY category,name').fetchall(); c.close(); return [dict(x) for x in r]
@app.post('/api/products')
def add_product(x:ProductIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e); name=x.name.strip()
    if not name or x.stock<0 or x.cost<0 or x.price<0: raise HTTPException(400,'Vérifie le libellé, la quantité et les prix.')
    code=(x.code or '').strip() or ('ART-'+secrets.token_hex(3).upper()); c=db()
    try:
        cur=c.execute('INSERT INTO products(code,name,category,supplier,cost,price,stock,alert,target) VALUES(?,?,?,?,?,?,?,?,?)',(code,name,x.category.strip() or 'Autres',x.supplier.strip(),x.cost,x.price,x.stock,x.alert,x.target)); pid=cur.lastrowid
        if x.stock>0: c.execute('INSERT INTO movements(product_id,kind,qty,note,created,employee_id) VALUES(?,?,?,?,?,?)',(pid,'in',x.stock,'Stock initial',now(),e['id']))
    except sqlite3.IntegrityError: c.close(); raise HTTPException(409,'Code article déjà utilisé')
    c.commit(); c.close(); log(e,'CREATION_ARTICLE',name); return {'id':pid,'code':code}
@app.patch('/api/products/{pid}')
def update_product(pid:int,x:dict,authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e); name=str(x.get('name','')).strip()
    if not name: raise HTTPException(400,'Libellé obligatoire')
    c=db(); cur=c.execute('UPDATE products SET name=? WHERE id=? AND active=1',(name,pid)); c.commit(); c.close()
    if not cur.rowcount: raise HTTPException(404,'Article introuvable')
    log(e,'MODIFICATION_ARTICLE',name); return {'ok':True}
@app.delete('/api/products/{pid}')
def archive_product(pid:int,authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e); c=db(); cur=c.execute('UPDATE products SET active=0 WHERE id=? AND active=1',(pid,)); c.commit(); c.close()
    if not cur.rowcount: raise HTTPException(404,'Article introuvable')
    log(e,'ARCHIVAGE_ARTICLE',str(pid)); return {'ok':True}
@app.post('/api/movement')
def movement(x:MoveIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e)
    if x.qty<=0 or x.kind not in ('in','out','adjust'): raise HTTPException(400,'Mouvement invalide')
    c=db(); p=c.execute('SELECT * FROM products WHERE id=? AND active=1',(x.product_id,)).fetchone()
    if not p: c.close(); raise HTTPException(404,'Produit introuvable')
    delta=x.qty if x.kind=='in' else (-x.qty if x.kind=='out' else x.qty-p['stock'])
    if p['stock']+delta<0: c.close(); raise HTTPException(400,'Stock insuffisant')
    c.execute('UPDATE products SET stock=stock+? WHERE id=?',(delta,x.product_id)); c.execute('INSERT INTO movements(product_id,kind,qty,note,created,employee_id) VALUES(?,?,?,?,?,?)',(x.product_id,x.kind,x.qty,x.note,now(),e['id'])); c.commit(); c.close(); log(e,'MOUVEMENT_STOCK',f"{p['name']} {x.kind} {x.qty}"); return {'ok':True}
@app.get('/api/tables')
def tables(authorization:Optional[str]=Header(None)):
    employee(authorization); c=db(); r=c.execute("SELECT t.*,count(o.id) orders FROM tables_room t LEFT JOIN orders o ON o.table_id=t.id AND o.status IN ('pending','served') WHERE t.active=1 GROUP BY t.id ORDER BY t.id").fetchall(); c.close(); return [dict(x) for x in r]
@app.post('/api/tables')
def add_table(x:TableIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization); allow(e,'admin','shareholder','service','cashier'); c=db()
    try: cur=c.execute('INSERT INTO tables_room(name) VALUES(?)',(x.name.strip(),)); tid=cur.lastrowid
    except sqlite3.IntegrityError: c.close(); raise HTTPException(409,'Cette table existe déjà')
    c.commit(); c.close(); log(e,'CREATION_TABLE',x.name); return {'id':tid}
def create_order(table_id,customer,items,source,token,eid):
    c=db()
    if table_id and not c.execute('SELECT id FROM tables_room WHERE id=? AND active=1',(table_id,)).fetchone(): c.close(); raise HTTPException(404,'Table inconnue')
    if not items: c.close(); raise HTTPException(400,'Commande vide')
    for it in items:
        p=c.execute('SELECT * FROM products WHERE id=? AND active=1',(it.product_id,)).fetchone()
        if not p or it.qty<=0: c.close(); raise HTTPException(400,'Article ou quantité invalide')
        if p['stock']<it.qty: c.close(); raise HTTPException(400,f"Stock insuffisant pour {p['name']}")
    cur=c.execute("INSERT INTO orders(table_id,customer,status,source,token,created,employee_id) VALUES(?,?, 'pending',?,?,?,?)",(table_id,customer,source,token,now(),eid)); oid=cur.lastrowid
    for it in items:
        p=c.execute('SELECT * FROM products WHERE id=?',(it.product_id,)).fetchone(); c.execute('INSERT INTO order_items(order_id,product_id,qty,unit_price,unit_cost,category) VALUES(?,?,?,?,?,?)',(oid,it.product_id,it.qty,p['price'],p['cost'],p['category'] or 'Autres')); c.execute('UPDATE products SET stock=stock-? WHERE id=?',(it.qty,it.product_id)); c.execute('INSERT INTO movements(product_id,kind,qty,note,created,employee_id) VALUES(?,?,?,?,?,?)',(it.product_id,'sale',it.qty,f'Commande #{oid}',now(),eid))
    c.commit(); c.close(); return oid
@app.post('/api/orders')
def new_order(x:OrderIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization); allow(e,'admin','shareholder','service','cashier'); oid=create_order(x.table_id,x.customer,x.items,x.source,None,e['id']); log(e,'COMMANDE_CREEE',f'Commande #{oid}'); return {'id':oid}
@app.get('/api/orders')
def orders(authorization:Optional[str]=Header(None)):
    employee(authorization); c=db(); rows=c.execute("SELECT o.*,t.name table_name,coalesce(sum(i.qty*i.unit_price),0) total FROM orders o LEFT JOIN tables_room t ON t.id=o.table_id LEFT JOIN order_items i ON i.order_id=o.id WHERE o.status IN ('pending','served') GROUP BY o.id ORDER BY o.created DESC").fetchall(); out=[]
    for r in rows:
        d=dict(r); d['items']=[dict(z) for z in c.execute('SELECT i.*,p.name product_name FROM order_items i JOIN products p ON p.id=i.product_id WHERE i.order_id=?',(r['id'],))]; out.append(d)
    c.close(); return out
@app.patch('/api/orders/{oid}')
def edit_order(oid:int,x:OrderIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization); allow(e,'admin','shareholder','service','cashier'); c=db(); o=c.execute("SELECT * FROM orders WHERE id=? AND status IN ('pending','served')",(oid,)).fetchone()
    if not o: c.close(); raise HTTPException(404,'Reçu non modifiable ou introuvable')
    if o['paid']>0 or o['credit']>0: c.close(); raise HTTPException(400,'Un reçu déjà partiellement réglé ne peut plus être modifié.')
    old=c.execute('SELECT * FROM order_items WHERE order_id=?',(oid,)).fetchall()
    for it in old: c.execute('UPDATE products SET stock=stock+? WHERE id=?',(it['qty'],it['product_id']))
    for it in x.items:
        p=c.execute('SELECT * FROM products WHERE id=? AND active=1',(it.product_id,)).fetchone()
        if not p or it.qty<=0 or p['stock']<it.qty:
            for oldit in old: c.execute('UPDATE products SET stock=stock-? WHERE id=?',(oldit['qty'],oldit['product_id']))
            c.commit(); c.close(); raise HTTPException(400,'Article invalide ou stock insuffisant')
    c.execute('DELETE FROM order_items WHERE order_id=?',(oid,))
    for it in x.items:
        p=c.execute('SELECT * FROM products WHERE id=?',(it.product_id,)).fetchone(); c.execute('INSERT INTO order_items(order_id,product_id,qty,unit_price,unit_cost,category) VALUES(?,?,?,?,?,?)',(oid,it.product_id,it.qty,p['price'],p['cost'],p['category'] or 'Autres')); c.execute('UPDATE products SET stock=stock-? WHERE id=?',(it.qty,it.product_id))
    c.execute('UPDATE orders SET customer=? WHERE id=?',(x.customer,oid)); c.commit(); c.close(); log(e,'MODIFICATION_RECU',f'Commande #{oid}'); return {'ok':True}
@app.post('/api/orders/{oid}/pay')
def pay(oid:int,x:PayIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization); allow(e,'admin','shareholder','cashier'); c=db(); o=c.execute("SELECT * FROM orders WHERE id=? AND status IN ('pending','served')",(oid,)).fetchone()
    if not o: c.close(); raise HTTPException(404,'Reçu introuvable')
    total=c.execute('SELECT coalesce(sum(qty*unit_price),0) FROM order_items WHERE order_id=?',(oid,)).fetchone()[0]; due=total-o['paid']-o['credit']
    if x.amount<=0 or x.amount>due+0.001: c.close(); raise HTTPException(400,'Montant invalide')
    c.execute('INSERT INTO payments(order_id,amount,method,created,employee_id) VALUES(?,?,?,?,?)',(oid,x.amount,x.method,now(),e['id'])); c.execute('UPDATE orders SET paid=paid+? WHERE id=?',(x.amount,oid)); left=due-x.amount
    if left<=0.001: c.execute("UPDATE orders SET status='paid' WHERE id=?",(oid,))
    c.commit(); c.close(); log(e,'PAIEMENT',f'Commande #{oid}: {x.amount}'); return {'remaining':max(0,left)}
@app.post('/api/orders/{oid}/credit')
def credit(oid:int,authorization:Optional[str]=Header(None)):
    e=employee(authorization); allow(e,'admin','shareholder','cashier'); c=db(); o=c.execute("SELECT * FROM orders WHERE id=? AND status IN ('pending','served')",(oid,)).fetchone()
    if not o: c.close(); raise HTTPException(404,'Reçu introuvable')
    total=c.execute('SELECT coalesce(sum(qty*unit_price),0) FROM order_items WHERE order_id=?',(oid,)).fetchone()[0]; amount=total-o['paid']-o['credit']
    if amount<=0: c.close(); raise HTTPException(400,'Aucun solde à créditer')
    c.execute('INSERT INTO credits(customer,order_id,amount,balance,created,note) VALUES(?,?,?,?,?,?)',(o['customer'],oid,amount,amount,now(),'Ardoise depuis reçu')); c.execute("UPDATE orders SET credit=credit+?,status='credit' WHERE id=?",(amount,oid)); c.commit(); c.close(); log(e,'MISE_A_CREDIT',f'Commande #{oid}: {amount}'); return {'credit':amount}
@app.get('/api/credits')
def credits(authorization:Optional[str]=Header(None)):
    e=employee(authorization); allow(e,'admin','shareholder','cashier'); c=db(); r=c.execute('SELECT * FROM credits WHERE balance>0 ORDER BY created DESC').fetchall(); c.close(); return [dict(x) for x in r]
@app.post('/api/credits/{cid}/pay')
def pay_credit(cid:int,x:CreditPay,authorization:Optional[str]=Header(None)):
    e=employee(authorization); allow(e,'admin','shareholder','cashier'); c=db(); cr=c.execute('SELECT * FROM credits WHERE id=?',(cid,)).fetchone()
    if not cr: c.close(); raise HTTPException(404,'Ardoise introuvable')
    if x.amount<=0 or x.amount>cr['balance']: c.close(); raise HTTPException(400,'Montant invalide')
    c.execute('INSERT INTO credit_payments(credit_id,amount,created,employee_id) VALUES(?,?,?,?)',(cid,x.amount,now(),e['id'])); c.execute('UPDATE credits SET balance=balance-? WHERE id=?',(x.amount,cid)); c.commit(); c.close(); log(e,'REGLEMENT_ARDOISE',f'Ardoise #{cid}: {x.amount}'); return {'ok':True}
@app.get('/api/receipt/{oid}')
def receipt(oid:int,authorization:Optional[str]=Header(None)):
    employee(authorization); c=db(); o=c.execute('SELECT o.*,t.name table_name FROM orders o LEFT JOIN tables_room t ON t.id=o.table_id WHERE o.id=?',(oid,)).fetchone()
    if not o: c.close(); raise HTTPException(404,'Reçu introuvable')
    items=[dict(x) for x in c.execute("SELECT i.*,COALESCE(p.name,'Article archivé') product_name FROM order_items i LEFT JOIN products p ON p.id=i.product_id WHERE i.order_id=?",(oid,))]; c.close(); return {'order':dict(o),'items':items,'total':sum(i['qty']*i['unit_price'] for i in items)}
@app.post('/api/customer/{table_id}/order')
def customer_order(table_id:int,x:OrderIn):
    oid=create_order(table_id,x.customer,x.items,'client',None,None); return {'id':oid,'message':'Commande transmise à la caisse.'}
@app.get('/api/public/{table_id}/menu')
def public_menu(table_id:int):
    c=db(); t=c.execute('SELECT * FROM tables_room WHERE id=? AND active=1',(table_id,)).fetchone()
    if not t: c.close(); raise HTTPException(404,'Table inconnue')
    ps=c.execute('SELECT id,name,category,price FROM products WHERE active=1 AND stock>0 ORDER BY category,name').fetchall(); c.close(); return {'table':dict(t),'products':[dict(x) for x in ps]}
@app.get('/api/employees')
def list_employees(authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e); c=db(); r=c.execute('SELECT id,name,role,active,monthly_salary,pin_changed FROM employees ORDER BY name').fetchall(); c.close(); return [dict(x) for x in r]
@app.post('/api/employees')
def add_employee(x:EmployeeIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e)
    if x.role not in ROLES: raise HTTPException(400,'Poste invalide')
    if len(x.pin)<4 or not x.pin.isdigit(): raise HTTPException(400,'PIN initial : 4 chiffres minimum')
    c=db(); cur=c.execute('INSERT INTO employees(name,role,pin_hash,pin_changed,monthly_salary) VALUES(?,?,?,?,?)',(x.name.strip(),x.role,hashpin(x.pin),0,max(0,x.monthly_salary))); c.commit(); c.close(); log(e,'CREATION_EMPLOYE',x.name); return {'id':cur.lastrowid}
@app.patch('/api/employees/{eid}')
def update_employee(eid:int,x:EmployeeUpdate,authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e); c=db(); emp=c.execute('SELECT * FROM employees WHERE id=?',(eid,)).fetchone()
    if not emp: c.close(); raise HTTPException(404,'Employé introuvable')
    if x.name is not None: c.execute('UPDATE employees SET name=? WHERE id=?',(x.name.strip(),eid))
    if x.role is not None:
        if x.role not in ROLES: c.close(); raise HTTPException(400,'Poste invalide')
        c.execute('UPDATE employees SET role=? WHERE id=?',(x.role,eid))
    if x.monthly_salary is not None: c.execute('UPDATE employees SET monthly_salary=? WHERE id=?',(max(0,x.monthly_salary),eid))
    if x.active is not None: c.execute('UPDATE employees SET active=? WHERE id=?',(int(x.active),eid))
    if x.new_pin:
        if len(x.new_pin)<4 or not x.new_pin.isdigit(): c.close(); raise HTTPException(400,'PIN invalide')
        c.execute('UPDATE employees SET pin_hash=?,pin_changed=0 WHERE id=?',(hashpin(x.new_pin),eid))
    c.commit(); c.close(); log(e,'MODIFICATION_EMPLOYE',f'Employé #{eid}'); return {'ok':True}
@app.post('/api/attendance')
def attendance(x:AttendanceIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e)
    if x.status not in ('present','absent'): raise HTTPException(400,'Statut invalide')
    c=db(); emp=c.execute('SELECT id FROM employees WHERE id=? AND active=1',(x.employee_id,)).fetchone()
    if not emp: c.close(); raise HTTPException(404,'Employé introuvable')
    c.execute('INSERT INTO attendance(employee_id,day,status,approved,approved_by,created) VALUES(?,?,?,1,?,?) ON CONFLICT(employee_id,day) DO UPDATE SET status=excluded.status,approved=1,approved_by=excluded.approved_by',(x.employee_id,x.day,x.status,e['id'],now())); c.commit(); c.close(); log(e,'PRESENCE_VALIDEE',f"{x.employee_id} {x.day} {x.status}"); return {'ok':True}
@app.get('/api/attendance')
def list_attendance(month:str,authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e); c=db(); r=c.execute("SELECT a.*,e.name employee_name FROM attendance a JOIN employees e ON e.id=a.employee_id WHERE substr(a.day,1,7)=? ORDER BY a.day DESC,e.name",(month,)).fetchall(); c.close(); return [dict(x) for x in r]
@app.get('/api/payroll')
def payroll(month:str,authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e); y,m=map(int,month.split('-')); days=monthrange(y,m)[1]; c=db(); emps=c.execute('SELECT id,name,monthly_salary FROM employees WHERE active=1 ORDER BY name').fetchall(); out=[]
    for emp in emps:
        absences=c.execute("SELECT count(*) FROM attendance WHERE employee_id=? AND substr(day,1,7)=? AND status='absent' AND approved=1",(emp['id'],month)).fetchone()[0]
        salary=emp['monthly_salary'] or 0; deduction=salary/days*absences; out.append({'employee_id':emp['id'],'name':emp['name'],'monthly_salary':salary,'approved_absences':absences,'deduction':round(deduction,2),'net':round(max(0,salary-deduction),2)})
    c.close(); return {'month':month,'days_in_month':days,'employees':out}
@app.post('/api/expenses')
def add_expense(x:ExpenseIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e)
    if x.amount<=0 or not x.label.strip(): raise HTTPException(400,'Libellé et montant obligatoires')
    c=db(); cur=c.execute('INSERT INTO expenses(label,amount,category,day,note,employee_id,created) VALUES(?,?,?,?,?,?,?)',(x.label.strip(),x.amount,x.category,x.day,x.note,e['id'],now())); c.commit(); c.close(); log(e,'CHARGE_ENREGISTREE',f'{x.label}: {x.amount}'); return {'id':cur.lastrowid}
@app.get('/api/expenses')
def list_expenses(month:Optional[str]=None,authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e); c=db(); q='SELECT * FROM expenses'; args=[]
    if month: q+=' WHERE substr(day,1,7)=?'; args=[month]
    r=c.execute(q+' ORDER BY day DESC,id DESC',args).fetchall(); c.close(); return [dict(x) for x in r]
@app.get('/api/orders/history')
def paid_order_history(period:str='day',anchor:Optional[str]=None,authorization:Optional[str]=Header(None)):
    e=employee(authorization); allow(e,'admin','shareholder','cashier','service')
    anchor=anchor or date.today().isoformat()
    if period=='day': start=end=anchor
    elif period=='week':
        d=date.fromisoformat(anchor); start=(d-__import__('datetime').timedelta(days=d.weekday())).isoformat(); end=(date.fromisoformat(start)+__import__('datetime').timedelta(days=6)).isoformat()
    elif period=='month': start=anchor[:7]+'-01'; end=anchor[:7]+'-'+str(monthrange(int(anchor[:4]),int(anchor[5:7]))[1])
    elif period=='year': start=anchor[:4]+'-01-01'; end=anchor[:4]+'-12-31'
    else: raise HTTPException(400,'Période invalide')
    c=db()
    rows=c.execute("""SELECT o.*,t.name table_name,
        (SELECT COALESCE(SUM(i.qty*i.unit_price),0) FROM order_items i WHERE i.order_id=o.id) total,
        (SELECT MAX(p.created) FROM payments p WHERE p.order_id=o.id) paid_at,
        (SELECT COALESCE(SUM(p.amount),0) FROM payments p WHERE p.order_id=o.id) paid_total
        FROM orders o LEFT JOIN tables_room t ON t.id=o.table_id
        WHERE o.status='paid'
        AND substr((SELECT MAX(p.created) FROM payments p WHERE p.order_id=o.id),1,10) BETWEEN ? AND ?
        ORDER BY paid_at DESC""",(start,end)).fetchall()
    out=[]
    for row in rows:
        item_rows=c.execute("SELECT i.*,COALESCE(p.name,'Article archivé') product_name FROM order_items i LEFT JOIN products p ON p.id=i.product_id WHERE i.order_id=? ORDER BY i.id",(row['id'],)).fetchall()
        d=dict(row); d['items']=[dict(x) for x in item_rows]; out.append(d)
    summary={'receipts':len(out),'sales':sum(x['total'] for x in out),'cost':sum(sum(i['qty']*i['unit_cost'] for i in x['items']) for x in out)}
    c.close()
    summary['gross_profit']=summary['sales']-summary['cost']
    return {'period':period,'start':start,'end':end,'summary':summary,'receipts':out}

@app.get('/api/reports')
def reports(period:str='day',anchor:Optional[str]=None,authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e); anchor=anchor or date.today().isoformat()
    if period=='day': start=end=anchor
    elif period=='week':
        d=date.fromisoformat(anchor); start=(d.replace(day=d.day)-__import__('datetime').timedelta(days=d.weekday())).isoformat(); end=(date.fromisoformat(start)+__import__('datetime').timedelta(days=6)).isoformat()
    elif period=='month': start=anchor[:7]+'-01'; end=anchor[:7]+'-'+str(monthrange(int(anchor[:4]),int(anchor[5:7]))[1])
    elif period=='year': start=anchor[:4]+'-01-01'; end=anchor[:4]+'-12-31'
    else: raise HTTPException(400,'Période invalide')
    c=db()
    sales=c.execute("SELECT coalesce(sum(i.qty*i.unit_price),0) sales FROM order_items i JOIN orders o ON o.id=i.order_id WHERE o.status IN ('paid','credit') AND substr(o.created,1,10) BETWEEN ? AND ?",(start,end)).fetchone()['sales']
    cost=c.execute("SELECT coalesce(sum(i.qty*i.unit_cost),0) cost FROM order_items i JOIN orders o ON o.id=i.order_id WHERE o.status IN ('paid','credit') AND substr(o.created,1,10) BETWEEN ? AND ?",(start,end)).fetchone()['cost']
    expenses=c.execute('SELECT coalesce(sum(amount),0) total FROM expenses WHERE day BETWEEN ? AND ?',(start,end)).fetchone()['total']
    count=c.execute("SELECT count(*) n FROM orders WHERE status IN ('paid','credit') AND substr(created,1,10) BETWEEN ? AND ?",(start,end)).fetchone()['n']
    categories=c.execute("SELECT COALESCE(NULLIF(i.category,''),'Autres') category, COALESCE(SUM(i.qty*i.unit_price),0) sales, COALESCE(SUM(i.qty*i.unit_cost),0) cost, COALESCE(SUM(i.qty*(i.unit_price-i.unit_cost)),0) gross_profit, COALESCE(SUM(i.qty),0) quantity FROM order_items i JOIN orders o ON o.id=i.order_id WHERE o.status IN ('paid','credit') AND substr(o.created,1,10) BETWEEN ? AND ? GROUP BY COALESCE(NULLIF(i.category,''),'Autres') ORDER BY cost DESC",(start,end)).fetchall()
    c.close()
    gross=sales-cost
    return {'period':period,'start':start,'end':end,'sales':sales,'cost_of_goods':cost,'gross_profit':gross,'expenses':expenses,'net_estimate':gross-expenses,'orders':count,'by_category':[dict(x) for x in categories]}
@app.get('/api/audit')
def audit(authorization:Optional[str]=Header(None)):
    e=employee(authorization); allow(e,'admin','shareholder','cashier'); c=db(); r=c.execute('SELECT a.*,e.name employee FROM audit a LEFT JOIN employees e ON e.id=a.employee_id ORDER BY a.id DESC LIMIT 300').fetchall(); c.close(); return [dict(x) for x in r]

@app.get('/api/admin/storage-status')
def storage_status(authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e)
    c=db()
    counts={}
    for table in ('employees','products','tables_room','orders','order_items','payments','credits','movements','audit','attendance','expenses'):
        counts[table]=c.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
    c.close()
    size=os.path.getsize(DB) if os.path.exists(DB) else 0
    return {'database_file':os.path.basename(DB),'database_size_bytes':size,'persistent_path':DB.startswith('/var/data/'),'tables':counts,'backup_directory':BACKUP_DIR}

@app.post('/api/admin/backup')
def create_backup(authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e)
    os.makedirs(BACKUP_DIR,exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    target=os.path.join(BACKUP_DIR,f'cave_tibati_{stamp}.db')
    src=sqlite3.connect(DB,timeout=30); dst=sqlite3.connect(target)
    try: src.backup(dst)
    finally: dst.close(); src.close()
    log(e,'SAUVEGARDE_BASE',os.path.basename(target))
    return {'ok':True,'file':os.path.basename(target),'size_bytes':os.path.getsize(target)}

@app.get('/api/admin/backup/{filename}')
def download_backup(filename:str,authorization:Optional[str]=Header(None)):
    e=employee(authorization); admin_or_share(e)
    if not filename.startswith('cave_tibati_') or not filename.endswith('.db') or '/' in filename or '\\' in filename:
        raise HTTPException(400,'Nom de sauvegarde invalide')
    target=os.path.join(BACKUP_DIR,filename)
    if not os.path.isfile(target): raise HTTPException(404,'Sauvegarde introuvable')
    from fastapi.responses import FileResponse as DownloadResponse
    return DownloadResponse(target,filename=filename,media_type='application/octet-stream')

app.mount('/static',StaticFiles(directory=os.path.join(BASE_DIR,'static')),name='static')
