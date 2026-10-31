import os, sqlite3, hashlib, secrets, json
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List

DB=os.getenv("DATABASE_PATH","cave.db")
app=FastAPI(title="Cave de Tibati - Gestion")
def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c
def now(): return datetime.now().isoformat(timespec="seconds")
def hashpin(pin,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+":"+hashlib.pbkdf2_hmac("sha256",pin.encode(),salt.encode(),180000).hex()
def checkpin(pin,stored):
    try:
        salt,h=stored.split(":")
        return secrets.compare_digest(hashlib.pbkdf2_hmac("sha256",pin.encode(),salt.encode(),180000).hex(),h)
    except: return False
def init():
    c=db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS employees(id INTEGER PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, pin_hash TEXT NOT NULL, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, employee_id INTEGER, created TEXT, FOREIGN KEY(employee_id) REFERENCES employees(id));
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT, category TEXT, supplier TEXT, cost REAL DEFAULT 0, price REAL DEFAULT 0, stock REAL DEFAULT 0, alert REAL DEFAULT 5, target REAL DEFAULT 20, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS tables_room(id INTEGER PRIMARY KEY, name TEXT UNIQUE, active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, table_id INTEGER, customer TEXT, status TEXT DEFAULT 'pending', source TEXT DEFAULT 'staff', token TEXT, created TEXT, employee_id INTEGER, paid REAL DEFAULT 0, credit REAL DEFAULT 0, FOREIGN KEY(table_id) REFERENCES tables_room(id));
    CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, qty REAL, unit_price REAL, unit_cost REAL, FOREIGN KEY(order_id) REFERENCES orders(id), FOREIGN KEY(product_id) REFERENCES products(id));
    CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY, order_id INTEGER, amount REAL, method TEXT, created TEXT, employee_id INTEGER);
    CREATE TABLE IF NOT EXISTS credits(id INTEGER PRIMARY KEY, customer TEXT, order_id INTEGER, amount REAL, balance REAL, created TEXT, note TEXT);
    CREATE TABLE IF NOT EXISTS credit_payments(id INTEGER PRIMARY KEY, credit_id INTEGER, amount REAL, created TEXT, employee_id INTEGER);
    CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY, product_id INTEGER, kind TEXT, qty REAL, note TEXT, created TEXT, employee_id INTEGER);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, employee_id INTEGER, action TEXT, details TEXT, created TEXT);
    """)
    if c.execute("SELECT count(*) FROM employees").fetchone()[0]==0:
        c.execute("INSERT INTO employees(name,role,pin_hash) VALUES(?,?,?)",("Administrateur","admin",hashpin("1234")))
    if c.execute("SELECT count(*) FROM products").fetchone()[0]==0:
        try:
            data=json.load(open(os.path.join(os.path.dirname(__file__),"products_seed.json"),encoding="utf-8"))
            for p in data: c.execute("INSERT OR IGNORE INTO products(code,name,category,supplier,cost,price,stock,alert,target) VALUES(?,?,?,?,?,?,?,?,?)",(p["code"],p["name"],p["category"],p["supplier"],p["cost"],p["price"],p["stock"],p["alert"],p["target"]))
        except Exception as e: print("seed products:",e)
    c.commit(); c.close()
init()
def employee(auth):
    c=db(); row=c.execute("SELECT e.* FROM sessions s JOIN employees e ON e.id=s.employee_id WHERE s.token=? AND e.active=1",(auth or "",)).fetchone(); c.close()
    if not row: raise HTTPException(401,"Session invalide. Reconnectez-vous.")
    return row
def log(e,action,details=""):
    c=db(); c.execute("INSERT INTO audit(employee_id,action,details,created) VALUES(?,?,?,?)",(e["id"] if e else None,action,details,now())); c.commit(); c.close()
class Login(BaseModel): pin:str
class EmployeeIn(BaseModel): name:str; role:str="serveur"; pin:str
class ProductIn(BaseModel): code:str; name:str; category:str="Autres"; supplier:str=""; cost:float=0; price:float=0; stock:float=0; alert:float=5; target:float=20
class TableIn(BaseModel): name:str
class ItemIn(BaseModel): product_id:int; qty:float
class OrderIn(BaseModel): table_id:Optional[int]=None; customer:str="Client"; items:List[ItemIn]; source:str="staff"
class PayIn(BaseModel): amount:float; method:str="Espèces"
class CreditPay(BaseModel): amount:float
class MoveIn(BaseModel): product_id:int; qty:float; kind:str="in"; note:str=""
@app.get("/")
def home(): return FileResponse("static/index.html")
@app.post("/api/login")
def login(x:Login):
    c=db(); rows=c.execute("SELECT * FROM employees WHERE active=1").fetchall(); c.close()
    for e in rows:
        if checkpin(x.pin,e["pin_hash"]):
            token=secrets.token_urlsafe(32); c=db(); c.execute("INSERT INTO sessions VALUES(?,?,?)",(token,e["id"],now())); c.commit(); c.close()
            log(e,"CONNEXION","Connexion PIN")
            return {"token":token,"employee":{"id":e["id"],"name":e["name"],"role":e["role"]}}
    raise HTTPException(401,"PIN incorrect")
@app.post("/api/logout")
def logout(authorization:Optional[str]=Header(None)):
    e=employee(authorization); c=db(); c.execute("DELETE FROM sessions WHERE token=?",(authorization,)); c.commit(); c.close(); log(e,"DECONNEXION"); return {"ok":True}
@app.get("/api/dashboard")
def dashboard(authorization:Optional[str]=Header(None)):
    e=employee(authorization); c=db()
    p=c.execute("SELECT count(*) n, sum(CASE WHEN stock<=0 THEN 1 ELSE 0 END) ruptures, sum(CASE WHEN stock>0 AND stock<=alert THEN 1 ELSE 0 END) alertes, sum(stock*cost) valeur FROM products WHERE active=1").fetchone()
    o=c.execute("SELECT count(*) n, coalesce(sum(oi.qty*oi.unit_price),0) total FROM orders o JOIN order_items oi ON oi.order_id=o.id WHERE o.status IN ('pending','served')").fetchone()
    cr=c.execute("SELECT coalesce(sum(balance),0) total FROM credits WHERE balance>0").fetchone()
    c.close(); return {"products":dict(p),"open_orders":dict(o),"credits":cr["total"]}
@app.get("/api/products")
def products(authorization:Optional[str]=Header(None)):
    employee(authorization); c=db(); rows=c.execute("SELECT * FROM products WHERE active=1 ORDER BY category,name").fetchall(); c.close(); return [dict(x) for x in rows]
@app.post("/api/products")
def add_product(x:ProductIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization); c=db()
    try: cur=c.execute("INSERT INTO products(code,name,category,supplier,cost,price,stock,alert,target) VALUES(?,?,?,?,?,?,?,?,?)",(x.code,x.name,x.category,x.supplier,x.cost,x.price,x.stock,x.alert,x.target)); pid=cur.lastrowid
    except sqlite3.IntegrityError: c.close(); raise HTTPException(409,"Code produit déjà utilisé")
    c.commit(); c.close(); log(e,"CREATION_PRODUIT",x.code); return {"id":pid}
@app.post("/api/movement")
def movement(x:MoveIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization)
    if x.qty<=0 or x.kind not in ("in","out","adjust"): raise HTTPException(400,"Mouvement invalide")
    c=db(); p=c.execute("SELECT * FROM products WHERE id=?",(x.product_id,)).fetchone()
    if not p: c.close(); raise HTTPException(404,"Produit introuvable")
    delta=x.qty if x.kind=="in" else (-x.qty if x.kind=="out" else x.qty-p["stock"])
    if p["stock"]+delta<0: c.close(); raise HTTPException(400,"Stock insuffisant")
    c.execute("UPDATE products SET stock=stock+? WHERE id=?",(delta,x.product_id))
    c.execute("INSERT INTO movements(product_id,kind,qty,note,created,employee_id) VALUES(?,?,?,?,?,?)",(x.product_id,x.kind,x.qty,x.note,now(),e["id"]))
    c.commit(); c.close(); log(e,"MOUVEMENT_STOCK",f'{p["code"]} {x.kind} {x.qty}'); return {"ok":True}
@app.get("/api/tables")
def tables(authorization:Optional[str]=Header(None)):
    employee(authorization); c=db(); r=c.execute("SELECT t.*,count(o.id) orders FROM tables_room t LEFT JOIN orders o ON o.table_id=t.id AND o.status IN ('pending','served') WHERE t.active=1 GROUP BY t.id ORDER BY t.id").fetchall(); c.close(); return [dict(x) for x in r]
@app.post("/api/tables")
def add_table(x:TableIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization); c=db()
    try: cur=c.execute("INSERT INTO tables_room(name) VALUES(?)",(x.name,)); tid=cur.lastrowid
    except sqlite3.IntegrityError: c.close(); raise HTTPException(409,"Cette table existe déjà")
    c.commit(); c.close(); log(e,"CREATION_TABLE",x.name); return {"id":tid}
@app.get("/api/orders")
def orders(authorization:Optional[str]=Header(None)):
    employee(authorization); c=db(); rows=c.execute("SELECT o.*,t.name table_name,coalesce(sum(i.qty*i.unit_price),0) total FROM orders o LEFT JOIN tables_room t ON t.id=o.table_id LEFT JOIN order_items i ON i.order_id=o.id WHERE o.status IN ('pending','served') GROUP BY o.id ORDER BY o.created DESC").fetchall()
    out=[]
    for r in rows:
        d=dict(r); d["items"]=[dict(z) for z in c.execute("SELECT i.*,p.name product_name FROM order_items i JOIN products p ON p.id=i.product_id WHERE i.order_id=?",(r["id"],))]; out.append(d)
    c.close(); return out
def create_order(table_id,customer,items,source,token,eid):
    c=db()
    if table_id and not c.execute("SELECT id FROM tables_room WHERE id=? AND active=1",(table_id,)).fetchone(): c.close(); raise HTTPException(404,"Table inconnue")
    if not items: c.close(); raise HTTPException(400,"Commande vide")
    for it in items:
        p=c.execute("SELECT * FROM products WHERE id=? AND active=1",(it.product_id,)).fetchone()
        if not p or it.qty<=0: c.close(); raise HTTPException(400,"Article ou quantité invalide")
        if p["stock"]<it.qty: c.close(); raise HTTPException(400,f'Stock insuffisant pour {p["name"]}')
    cur=c.execute("INSERT INTO orders(table_id,customer,status,source,token,created,employee_id) VALUES(?,?, 'pending',?,?,?,?)",(table_id,customer,source,token,now(),eid)); oid=cur.lastrowid
    for it in items:
        p=c.execute("SELECT * FROM products WHERE id=?",(it.product_id,)).fetchone()
        c.execute("INSERT INTO order_items(order_id,product_id,qty,unit_price,unit_cost) VALUES(?,?,?,?,?)",(oid,it.product_id,it.qty,p["price"],p["cost"]))
        c.execute("UPDATE products SET stock=stock-? WHERE id=?",(it.qty,it.product_id))
        c.execute("INSERT INTO movements(product_id,kind,qty,note,created,employee_id) VALUES(?,?,?,?,?,?)",(it.product_id,"sale",it.qty,f"Commande #{oid}",now(),eid))
    c.commit(); c.close(); return oid
@app.post("/api/orders")
def new_order(x:OrderIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization); oid=create_order(x.table_id,x.customer,x.items,x.source,None,e["id"]); log(e,"COMMANDE_CREEE",f"Commande #{oid}"); return {"id":oid}
@app.post("/api/orders/{oid}/pay")
def pay(oid:int,x:PayIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization); c=db(); o=c.execute("SELECT * FROM orders WHERE id=? AND status IN ('pending','served')",(oid,)).fetchone()
    if not o: c.close(); raise HTTPException(404,"Reçu introuvable")
    total=c.execute("SELECT coalesce(sum(qty*unit_price),0) FROM order_items WHERE order_id=?",(oid,)).fetchone()[0]
    due=total-o["paid"]-o["credit"]
    if x.amount<=0 or x.amount>due+0.001: c.close(); raise HTTPException(400,"Montant invalide")
    c.execute("INSERT INTO payments(order_id,amount,method,created,employee_id) VALUES(?,?,?,?,?)",(oid,x.amount,x.method,now(),e["id"]))
    c.execute("UPDATE orders SET paid=paid+? WHERE id=?",(x.amount,oid))
    left=due-x.amount
    if left<=0.001: c.execute("UPDATE orders SET status='paid' WHERE id=?",(oid,))
    c.commit(); c.close(); log(e,"PAIEMENT",f"Commande #{oid}: {x.amount}"); return {"remaining":max(0,left)}
@app.post("/api/orders/{oid}/credit")
def credit(oid:int,authorization:Optional[str]=Header(None)):
    e=employee(authorization); c=db(); o=c.execute("SELECT * FROM orders WHERE id=? AND status IN ('pending','served')",(oid,)).fetchone()
    if not o: c.close(); raise HTTPException(404,"Reçu introuvable")
    total=c.execute("SELECT coalesce(sum(qty*unit_price),0) FROM order_items WHERE order_id=?",(oid,)).fetchone()[0]
    amount=total-o["paid"]-o["credit"]
    if amount<=0: c.close(); raise HTTPException(400,"Aucun solde à créditer")
    c.execute("INSERT INTO credits(customer,order_id,amount,balance,created,note) VALUES(?,?,?,?,?,?)",(o["customer"],oid,amount,amount,now(),"Ardoise depuis reçu"))
    c.execute("UPDATE orders SET credit=credit+?,status='credit' WHERE id=?",(amount,oid)); c.commit(); c.close(); log(e,"MISE_A_CREDIT",f"Commande #{oid}: {amount}"); return {"credit":amount}
@app.get("/api/credits")
def credits(authorization:Optional[str]=Header(None)):
    employee(authorization); c=db(); r=c.execute("SELECT * FROM credits WHERE balance>0 ORDER BY created DESC").fetchall(); c.close(); return [dict(x) for x in r]
@app.post("/api/credits/{cid}/pay")
def pay_credit(cid:int,x:CreditPay,authorization:Optional[str]=Header(None)):
    e=employee(authorization); c=db(); cr=c.execute("SELECT * FROM credits WHERE id=?",(cid,)).fetchone()
    if not cr: c.close(); raise HTTPException(404,"Ardoise introuvable")
    if x.amount<=0 or x.amount>cr["balance"]: c.close(); raise HTTPException(400,"Montant invalide")
    c.execute("INSERT INTO credit_payments(credit_id,amount,created,employee_id) VALUES(?,?,?,?)",(cid,x.amount,now(),e["id"]))
    c.execute("UPDATE credits SET balance=balance-? WHERE id=?",(x.amount,cid)); c.commit(); c.close(); log(e,"REGLEMENT_ARDOISE",f"Ardoise #{cid}: {x.amount}"); return {"ok":True}
@app.get("/api/receipt/{oid}")
def receipt(oid:int,authorization:Optional[str]=Header(None)):
    employee(authorization); c=db(); o=c.execute("SELECT o.*,t.name table_name FROM orders o LEFT JOIN tables_room t ON t.id=o.table_id WHERE o.id=?",(oid,)).fetchone()
    if not o: c.close(); raise HTTPException(404,"Reçu introuvable")
    items=[dict(x) for x in c.execute("SELECT i.*,p.name product_name FROM order_items i JOIN products p ON p.id=i.product_id WHERE i.order_id=?",(oid,))]
    c.close(); return {"order":dict(o),"items":items,"total":sum(i["qty"]*i["unit_price"] for i in items)}
@app.post("/api/customer/{table_id}/order")
def customer_order(table_id:int,x:OrderIn):
    # Le client passe par le QR/lien propre à la table. La commande reste en attente de validation au comptoir.
    oid=create_order(table_id,x.customer,x.items,"client",None,None)
    return {"id":oid,"message":"Commande transmise. Présentez-vous au comptoir pour confirmation."}
@app.get("/api/public/{table_id}/menu")
def public_menu(table_id:int):
    c=db(); t=c.execute("SELECT * FROM tables_room WHERE id=? AND active=1",(table_id,)).fetchone()
    if not t: c.close(); raise HTTPException(404,"Table inconnue")
    ps=c.execute("SELECT id,name,category,price FROM products WHERE active=1 AND stock>0 ORDER BY category,name").fetchall(); c.close()
    return {"table":dict(t),"products":[dict(x) for x in ps]}
@app.get("/api/audit")
def audit(authorization:Optional[str]=Header(None)):
    e=employee(authorization)
    if e["role"]!="admin": raise HTTPException(403,"Réservé à l'administration")
    c=db(); r=c.execute("SELECT a.*,e.name employee FROM audit a LEFT JOIN employees e ON e.id=a.employee_id ORDER BY a.id DESC LIMIT 300").fetchall(); c.close(); return [dict(x) for x in r]
@app.post("/api/employees")
def add_employee(x:EmployeeIn,authorization:Optional[str]=Header(None)):
    e=employee(authorization)
    if e["role"]!="admin": raise HTTPException(403,"Réservé à l'administration")
    if len(x.pin)<4: raise HTTPException(400,"PIN de 4 chiffres minimum")
    c=db(); cur=c.execute("INSERT INTO employees(name,role,pin_hash) VALUES(?,?,?)",(x.name,x.role,hashpin(x.pin))); c.commit(); c.close(); log(e,"CREATION_EMPLOYE",x.name); return {"id":cur.lastrowid}
app.mount("/static",StaticFiles(directory="static"),name="static")
