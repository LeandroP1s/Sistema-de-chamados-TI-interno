import os, io, csv, uuid, json, sqlite3, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from flask import Flask, request, redirect, url_for, session, send_file, abort, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = "troque-essa-chave-em-producao"

# ====== CONFIG ======
HOST_IP = ""
PORT = 5001

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_PATH = os.path.join(BASE_DIR, "chamados.db")

CATEGORIAS = ["Hardware", "Software", "Rede/Internet", "E-mail", "Sistemas", "Impressora", "Acesso", "Outros"]
PRIORIDADES = ["Baixa", "Média", "Alta", "Crítica"]
STATUS = ["Aberto", "Em andamento", "Aguardando usuário", "Resolvido", "Encerrado"]

# SLA em horas por prioridade (você pode ajustar)
SLA_HORAS = {
    "Baixa": 72,
    "Média": 48,
    "Alta": 24,
    "Crítica": 8
}

# ====== VISUAL: fonte melhor ======
# Usa uma “system font stack” moderna (Sego UI no Windows + fallback).
BASE_HTML = """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{{title}}</title>
  <style>
    :root{
      --bg:#0b1220; --card:#0f1b33; --muted:#9fb0d0; --text:#e8eefc;
      --brand:#22c55e; --brand2:#facc15; --danger:#ef4444; --info:#60a5fa;
      --border:#1f2d4d;
    }
    *{
      box-sizing:border-box;
      font-family: "Segoe UI Variable","Segoe UI","Inter",system-ui,-apple-system,Roboto,Ubuntu,Cantarell,"Noto Sans",sans-serif;
    }
    body{margin:0;background:linear-gradient(180deg,#071022 0%, #0b1220 45%, #060b14 100%);color:var(--text)}
    a{color:inherit;text-decoration:none}
    .topbar{position:sticky;top:0;background:rgba(11,18,32,.9);backdrop-filter: blur(10px);
            border-bottom:1px solid var(--border);padding:14px 18px;display:flex;gap:12px;align-items:center;z-index:10}
    .brand{display:flex;align-items:center;gap:10px;font-weight:800;letter-spacing:.2px}
    .dot{width:10px;height:10px;border-radius:50%;background:linear-gradient(45deg,var(--brand),var(--brand2))}
    .nav{margin-left:auto;display:flex;gap:10px;flex-wrap:wrap}
    .nav a{padding:8px 12px;border:1px solid var(--border);border-radius:999px;color:var(--muted)}
    .nav a:hover{border-color:#2b3e66;color:var(--text)}
    .wrap{max-width:1180px;margin:22px auto;padding:0 16px}
    .grid{display:grid;grid-template-columns: 1.25fr .75fr;gap:16px}
    @media(max-width:980px){.grid{grid-template-columns:1fr}}
    .card{background:rgba(15,27,51,.9);border:1px solid var(--border);border-radius:18px;padding:16px;box-shadow:0 10px 35px rgba(0,0,0,.35)}
    .h1{font-size:22px;margin:0 0 10px 0}
    .muted{color:var(--muted)}
    .pill{display:inline-flex;gap:8px;align-items:center;padding:6px 10px;border-radius:999px;border:1px solid var(--border);color:var(--muted);font-size:12px}
    .btn{cursor:pointer;border:1px solid transparent;border-radius:12px;padding:10px 12px;font-weight:700}
    .btn-primary{background:linear-gradient(45deg,var(--brand),#16a34a);color:#04110a}
    .btn-outline{background:transparent;border-color:var(--border);color:var(--text)}
    .btn-danger{background:linear-gradient(45deg,var(--danger),#b91c1c);color:#fff}
    .btn-info{background:linear-gradient(45deg,var(--info),#2563eb);color:#081028}
    .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
    .field{display:flex;flex-direction:column;gap:6px;margin:10px 0}
    input,select,textarea{padding:10px 12px;border-radius:12px;border:1px solid var(--border);background:#0b1730;color:var(--text)}
    textarea{min-height:110px;resize:vertical}
    table{width:100%;border-collapse:collapse;margin-top:10px}
    th,td{border-bottom:1px solid var(--border);padding:10px 8px;text-align:left;vertical-align:top}
    th{color:var(--muted);font-weight:800;font-size:12px;text-transform:uppercase;letter-spacing:.6px}
    .tag{padding:4px 9px;border-radius:999px;border:1px solid var(--border);font-size:12px;color:var(--muted);display:inline-block}
    .msg{padding:10px 12px;border-radius:14px;border:1px solid var(--border);background:#0a1430;margin:12px 0}
    .msg.ok{border-color:rgba(34,197,94,.4)}
    .msg.bad{border-color:rgba(239,68,68,.4)}
    .small{font-size:12px}
    .hr{height:1px;background:var(--border);margin:14px 0}

    /* SLA badges */
    .sla-ok{color:#86efac}
    .sla-warn{color:#fde68a}
    .sla-bad{color:#fca5a5}

    /* Mini chart */
    canvas{width:100%;max-width:100%}
  </style>
</head>
<body>
  <div class="topbar">
    <div class="brand"><span class="dot"></span> Chamados TI • SM Obras</div>
    <div class="nav">
      {% if session.get('user') %}
        <a href="{{url_for('dashboard')}}">Painel</a>
        <a href="{{url_for('abrir_chamado')}}">Abrir chamado</a>
        {% if session.get('role') in ['ti','admin'] %}
          <a href="{{url_for('ti_painel')}}">Painel TI</a>
          <a href="{{url_for('stats')}}">Gráficos</a>
          <a href="{{url_for('exportar_csv')}}">Exportar CSV</a>
        {% endif %}
        <a href="{{url_for('logout')}}">Sair</a>
      {% else %}
        <a href="{{url_for('login')}}">Entrar</a>
      {% endif %}
    </div>
  </div>

  <div class="wrap">
    {% if flash_msg %}
      <div class="msg {{flash_type}}">{{flash_msg}}</div>
    {% endif %}
    {{content|safe}}
  </div>
</body>
</html>
"""

# ====== HELPERS ======
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def parse_dt(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")

def dt_str(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def render(title, content, flash_msg=None, flash_type="ok"):
    return render_template_string(
        BASE_HTML, title=title, content=content, session=session,
        flash_msg=flash_msg, flash_type=flash_type
    )

def require_login():
    if not session.get("user"):
        return redirect(url_for("login"))
    return None

def require_role(*roles):
    if session.get("role") not in roles:
        abort(403)

def human_role(r):
    return {"admin":"Administrador", "ti":"TI", "user":"Usuário"}.get(r, r)

# ====== EMAIL (SMTP) ======
def smtp_config():
    """
    Configure via variáveis de ambiente:
      SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_TLS ("1" ou "0"),
      MAIL_FROM (ex: ti@prefeitura.gov), MAIL_REPLY_TO (opcional)
    """
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER", "").strip()
    pwd  = os.getenv("SMTP_PASS", "").strip()
    tls  = os.getenv("SMTP_TLS", "1").strip() == "1"
    mail_from = os.getenv("MAIL_FROM", user).strip()
    reply_to = os.getenv("MAIL_REPLY_TO", "").strip()
    enabled = bool(host and user and pwd and mail_from)
    return {
        "enabled": enabled,
        "host": host, "port": port, "user": user, "pwd": pwd, "tls": tls,
        "from": mail_from, "reply_to": reply_to
    }

def send_email(to_list, subject, html_body, text_body=None):
    cfg = smtp_config()
    if not cfg["enabled"]:
        return False

    to_list = [x.strip() for x in (to_list or []) if x and x.strip()]
    if not to_list:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from"]
    msg["To"] = ", ".join(to_list)
    if cfg["reply_to"]:
        msg["Reply-To"] = cfg["reply_to"]

    if not text_body:
        text_body = "Seu cliente de e-mail não suporta HTML."

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as server:
            if cfg["tls"]:
                server.starttls()
            server.login(cfg["user"], cfg["pwd"])
            server.sendmail(cfg["from"], to_list, msg.as_string())
        return True
    except Exception:
        return False

def notify_ticket_event(ticket_id, event_type, extra=None):
    """
    Dispara e-mail ao abrir/atualizar.
    - event_type: "opened", "status", "comment"
    - extra: dict com dados extras (ex: novo_status)
    """
    cfg = smtp_config()
    if not cfg["enabled"]:
        return

    t = db_get_ticket(ticket_id)
    if not t:
        return

    # Quem recebe? (ajuste aqui como quiser)
    # - solicitante (se tiver e-mail cadastrado)
    # - todos TIs/Admins (se tiver e-mail cadastrado)
    solicitante_email = t["solicitante_email"] or ""
    tis = db_list_users_by_roles(["ti", "admin"])
    ti_emails = [u["email"] for u in tis if u.get("email")]

    recipients = []
    # Ao abrir: avisa TI. Ao atualizar: avisa solicitante e TI.
    if event_type == "opened":
        recipients = ti_emails
    else:
        recipients = list(set([solicitante_email] + ti_emails))

    if not recipients:
        return

    subject = ""
    if event_type == "opened":
        subject = f"[Chamados TI] Novo chamado {t['protocolo']}"
    elif event_type == "status":
        subject = f"[Chamados TI] Status atualizado {t['protocolo']}"
    elif event_type == "comment":
        subject = f"[Chamados TI] Novo comentário {t['protocolo']}"
    else:
        subject = f"[Chamados TI] Atualização {t['protocolo']}"

    sla_line = f"SLA: {t['sla_horas']}h | Vence em: {t['due_at'] or '-'}"
    html = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;line-height:1.35">
      <h2 style="margin:0 0 10px 0">Chamado {t['protocolo']}</h2>
      <p style="margin:0 0 6px 0"><b>Título:</b> {t['titulo']}</p>
      <p style="margin:0 0 6px 0"><b>Status:</b> {t['status']} | <b>Prioridade:</b> {t['prioridade']} | <b>Categoria:</b> {t['categoria']}</p>
      <p style="margin:0 0 6px 0"><b>Solicitante:</b> {t['solicitante_nome']} ({t['solicitante_usuario']}) • <b>Setor:</b> {t['solicitante_setor']}</p>
      <p style="margin:0 0 6px 0"><b>Responsável:</b> {t['responsavel'] or '-'} | <b>{sla_line}</b></p>
      <hr/>
      <p><b>Descrição:</b><br/>{(t['descricao'] or '').replace('\\n','<br/>')}</p>
      <p style="color:#555">Acesso: http://{HOST_IP}:{PORT}/chamado/{t['id']}</p>
    </div>
    """
    send_email(recipients, subject, html)

# ====== DATABASE ======
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            nome TEXT,
            setor TEXT,
            email TEXT
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY,
            protocolo TEXT NOT NULL,
            titulo TEXT NOT NULL,
            categoria TEXT NOT NULL,
            prioridade TEXT NOT NULL,
            descricao TEXT NOT NULL,
            patrimonio TEXT,
            status TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL,
            solicitante_usuario TEXT NOT NULL,
            solicitante_nome TEXT,
            solicitante_setor TEXT,
            solicitante_email TEXT,
            responsavel TEXT,

            sla_horas INTEGER NOT NULL,
            due_at TEXT,
            first_response_at TEXT,
            resolved_at TEXT
        );

        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT NOT NULL,
            quando TEXT NOT NULL,
            por TEXT NOT NULL,
            msg TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT NOT NULL,
            quando TEXT NOT NULL,
            por TEXT NOT NULL,
            acao TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT NOT NULL,
            arquivo TEXT NOT NULL,
            nome_original TEXT NOT NULL
        );
        """)
    bootstrap_admin_if_needed()

def bootstrap_admin_if_needed():
    with db() as conn:
        row = conn.execute("SELECT username FROM users WHERE username='admin'").fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users(username,password_hash,role,nome,setor,email) VALUES(?,?,?,?,?,?)",
                ("admin", generate_password_hash("admin123"), "admin", "Administrador", "TI", "")
            )

def db_list_users_by_roles(roles):
    qmarks = ",".join(["?"]*len(roles))
    with db() as conn:
        rows = conn.execute(f"SELECT username,role,nome,setor,email FROM users WHERE role IN ({qmarks})", roles).fetchall()
    return [dict(r) for r in rows]

def gerar_protocolo():
    ano = datetime.now().strftime("%Y")
    with db() as conn:
        rows = conn.execute("SELECT protocolo FROM tickets WHERE protocolo LIKE ?", (f"{ano}-%",)).fetchall()
    seq = 1
    for r in rows:
        p = r["protocolo"]
        try:
            seq = max(seq, int(p.split("-")[1]) + 1)
        except:
            pass
    return f"{ano}-{seq:06d}"

def sla_due(prioridade, created_dt):
    horas = int(SLA_HORAS.get(prioridade, 48))
    return horas, (created_dt + timedelta(hours=horas))

def db_create_ticket(data):
    with db() as conn:
        conn.execute("""
            INSERT INTO tickets(
              id, protocolo, titulo, categoria, prioridade, descricao, patrimonio,
              status, criado_em, atualizado_em,
              solicitante_usuario, solicitante_nome, solicitante_setor, solicitante_email,
              responsavel, sla_horas, due_at, first_response_at, resolved_at
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data["id"], data["protocolo"], data["titulo"], data["categoria"], data["prioridade"],
            data["descricao"], data.get("patrimonio",""),
            data["status"], data["criado_em"], data["atualizado_em"],
            data["solicitante_usuario"], data.get("solicitante_nome",""), data.get("solicitante_setor",""), data.get("solicitante_email",""),
            data.get("responsavel"), data["sla_horas"], data.get("due_at"), data.get("first_response_at"), data.get("resolved_at")
        ))

def db_get_ticket(ticket_id):
    with db() as conn:
        r = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if not r:
            return None
        return dict(r)

def db_list_tickets(filters=None):
    filters = filters or {}
    sql = "SELECT * FROM tickets WHERE 1=1"
    params = []
    if filters.get("status"):
        sql += " AND status=?"; params.append(filters["status"])
    if filters.get("categoria"):
        sql += " AND categoria=?"; params.append(filters["categoria"])
    if filters.get("q"):
        q = f"%{filters['q'].lower()}%"
        sql += " AND (lower(titulo) LIKE ? OR lower(descricao) LIKE ? OR lower(protocolo) LIKE ?)"
        params += [q, q, q]
    sql += " ORDER BY criado_em DESC"
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]

def db_list_my_tickets(username):
    with db() as conn:
        rows = conn.execute("SELECT * FROM tickets WHERE solicitante_usuario=? ORDER BY criado_em DESC", (username,)).fetchall()
    return [dict(r) for r in rows]

def db_list_assigned_tickets(username):
    with db() as conn:
        rows = conn.execute("SELECT * FROM tickets WHERE responsavel=? ORDER BY criado_em DESC", (username,)).fetchall()
    return [dict(r) for r in rows]

def db_list_open_tickets():
    with db() as conn:
        rows = conn.execute("""
            SELECT * FROM tickets
            WHERE status IN ('Aberto','Em andamento','Aguardando usuário')
            ORDER BY criado_em DESC
        """).fetchall()
    return [dict(r) for r in rows]

def db_add_history(ticket_id, por, acao):
    with db() as conn:
        conn.execute("INSERT INTO history(ticket_id,quando,por,acao) VALUES(?,?,?,?)",
                     (ticket_id, now_str(), por, acao))

def db_add_comment(ticket_id, por, msg):
    with db() as conn:
        conn.execute("INSERT INTO comments(ticket_id,quando,por,msg) VALUES(?,?,?,?)",
                     (ticket_id, now_str(), por, msg))

def db_list_comments(ticket_id):
    with db() as conn:
        rows = conn.execute("SELECT quando,por,msg FROM comments WHERE ticket_id=? ORDER BY id ASC", (ticket_id,)).fetchall()
    return [dict(r) for r in rows]

def db_list_history(ticket_id):
    with db() as conn:
        rows = conn.execute("SELECT quando,por,acao FROM history WHERE ticket_id=? ORDER BY id ASC", (ticket_id,)).fetchall()
    return [dict(r) for r in rows]

def db_add_attachment(ticket_id, arquivo, nome_original):
    with db() as conn:
        conn.execute("INSERT INTO attachments(ticket_id,arquivo,nome_original) VALUES(?,?,?)",
                     (ticket_id, arquivo, nome_original))

def db_list_attachments(ticket_id):
    with db() as conn:
        rows = conn.execute("SELECT arquivo,nome_original FROM attachments WHERE ticket_id=? ORDER BY id ASC", (ticket_id,)).fetchall()
    return [dict(r) for r in rows]

def db_update_ticket(ticket_id, **fields):
    if not fields:
        return
    keys = list(fields.keys())
    set_sql = ", ".join([f"{k}=?" for k in keys])
    values = [fields[k] for k in keys]
    values.append(ticket_id)
    with db() as conn:
        conn.execute(f"UPDATE tickets SET {set_sql} WHERE id=?", values)

def db_delete_ticket(ticket_id):
    with db() as conn:
        conn.execute("DELETE FROM attachments WHERE ticket_id=?", (ticket_id,))
        conn.execute("DELETE FROM comments WHERE ticket_id=?", (ticket_id,))
        conn.execute("DELETE FROM history WHERE ticket_id=?", (ticket_id,))
        conn.execute("DELETE FROM tickets WHERE id=?", (ticket_id,))

def db_get_user(username):
    with db() as conn:
        r = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    return dict(r) if r else None

def db_list_users():
    with db() as conn:
        rows = conn.execute("SELECT username,role,nome,setor,email FROM users ORDER BY username").fetchall()
    return [dict(r) for r in rows]

def db_create_user(username, password, role, nome, setor, email):
    with db() as conn:
        conn.execute("""
          INSERT INTO users(username,password_hash,role,nome,setor,email)
          VALUES(?,?,?,?,?,?)
        """, (username, generate_password_hash(password), role, nome, setor, email))

def db_set_password(username, new_password):
    with db() as conn:
        conn.execute("UPDATE users SET password_hash=? WHERE username=?",
                     (generate_password_hash(new_password), username))

def db_delete_user(username):
    with db() as conn:
        conn.execute("DELETE FROM users WHERE username=?", (username,))

def db_user_exists(username):
    with db() as conn:
        r = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
    return bool(r)

# ====== SLA STATUS HELPERS ======
def sla_badge(ticket):
    """
    Retorna (texto, classe) baseado no SLA:
    - Encerrado/Resolvido: ok
    - Se vencido: bad
    - Se faltando <= 25% do tempo: warn
    - senão ok
    """
    st = ticket["status"]
    if st in ["Resolvido","Encerrado"]:
        return ("SLA OK", "sla-ok")

    due = ticket.get("due_at")
    if not due:
        return ("SLA —", "sla-warn")

    now = datetime.now()
    due_dt = parse_dt(due)
    created = parse_dt(ticket["criado_em"])
    total = max((due_dt - created).total_seconds(), 1)
    remaining = (due_dt - now).total_seconds()

    if remaining < 0:
        return ("SLA VENCIDO", "sla-bad")

    if remaining / total <= 0.25:
        return ("SLA PRÓXIMO", "sla-warn")

    return ("SLA OK", "sla-ok")

# ====== ROUTES: AUTH ======
@app.route("/", methods=["GET"])
def index():
    if session.get("user"):
        return redirect(url_for("dashboard"))
    content = f"""
      <div class="grid">
        <div class="card">
          <h1 class="h1">Sistema de Chamados de TI</h1>
          <div class="muted">Secretaria de Obras • Intranet ({HOST_IP})</div>
          <div class="hr"></div>
          <div class="row">
            <a class="btn btn-primary" href="{url_for('login')}">Entrar</a>
          </div>
          <div class="hr"></div>
          <div class="small muted">
            Admin inicial: <b>admin</b> / <b>admin123</b> (troque depois).
          </div>
        </div>
        <div class="card">
          <div class="pill">Recursos</div>
          <div class="hr"></div>
          <ul class="muted">
            <li>SQLite (sem quebrar arquivo JSON)</li>
            <li>SLA automático por prioridade</li>
            <li>Gráficos mensais (sem internet)</li>
            <li>E-mail (SMTP) ao abrir/atualizar</li>
          </ul>
        </div>
      </div>
    """
    return render("Início", content)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        u = db_get_user(username)
        if u and check_password_hash(u["password_hash"], password):
            session["user"] = username
            session["role"] = u.get("role","user")
            session["nome"] = u.get("nome") or username
            session["setor"] = u.get("setor") or ""
            session["email"] = u.get("email") or ""
            return redirect(url_for("dashboard"))
        return render("Entrar", login_form(), flash_msg="Usuário ou senha inválidos.", flash_type="bad")
    return render("Entrar", login_form())

def login_form():
    return f"""
    <div class="grid">
      <div class="card">
        <h1 class="h1">Entrar</h1>
        <form method="post">
          <div class="field">
            <label class="muted">Usuário</label>
            <input name="username" placeholder="ex: leandro.prates" required>
          </div>
          <div class="field">
            <label class="muted">Senha</label>
            <input type="password" name="password" placeholder="••••••••" required>
          </div>
          <div class="row">
            <button class="btn btn-primary" type="submit">Acessar</button>
            <a class="btn btn-outline" href="{url_for('primeiro_acesso')}">Primeiro acesso / Trocar senha</a>
          </div>
        </form>
      </div>
      <div class="card">
        <div class="pill">Dica</div>
        <div class="hr"></div>
        <div class="muted">
          Se você recebeu usuário e senha do TI, use “Primeiro acesso” para definir sua senha.
        </div>
      </div>
    </div>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/primeiro-acesso", methods=["GET","POST"])
def primeiro_acesso():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        senha_atual = request.form.get("senha_atual") or ""
        senha_nova = request.form.get("senha_nova") or ""
        senha_nova2 = request.form.get("senha_nova2") or ""

        if senha_nova != senha_nova2 or len(senha_nova) < 4:
            return render("Primeiro acesso", primeiro_acesso_form(),
                          flash_msg="Senha nova inválida ou não confere (mín. 4 caracteres).", flash_type="bad")

        u = db_get_user(username)
        if not u or not check_password_hash(u["password_hash"], senha_atual):
            return render("Primeiro acesso", primeiro_acesso_form(),
                          flash_msg="Usuário/senha atual inválidos.", flash_type="bad")

        db_set_password(username, senha_nova)
        return render("Primeiro acesso", primeiro_acesso_form(),
                      flash_msg="Senha alterada com sucesso. Agora você já pode entrar.", flash_type="ok")

    return render("Primeiro acesso", primeiro_acesso_form())

def primeiro_acesso_form():
    return f"""
    <div class="card">
      <h1 class="h1">Primeiro acesso / Trocar senha</h1>
      <form method="post">
        <div class="field"><label class="muted">Usuário</label><input name="username" required></div>
        <div class="field"><label class="muted">Senha atual</label><input type="password" name="senha_atual" required></div>
        <div class="field"><label class="muted">Nova senha</label><input type="password" name="senha_nova" required></div>
        <div class="field"><label class="muted">Confirmar nova senha</label><input type="password" name="senha_nova2" required></div>
        <div class="row">
          <button class="btn btn-primary" type="submit">Salvar</button>
          <a class="btn btn-outline" href="{url_for('login')}">Voltar</a>
        </div>
      </form>
    </div>
    """

# ====== DASHBOARD ======
@app.route("/painel")
def dashboard():
    r = require_login()
    if r: return r

    role = session.get("role")
    user = session.get("user")

    if role in ["ti","admin"]:
        meus = db_list_assigned_tickets(user)
        abertos = db_list_open_tickets()
        content = render_ti_dashboard(meus, abertos)
        return render("Painel", content)

    meus = db_list_my_tickets(user)
    content = render_user_dashboard(meus)
    return render("Painel", content)

def render_user_dashboard(meus):
    rows = ""
    for t in meus:
        badge_txt, badge_cls = sla_badge(t)
        rows += f"""
        <tr>
          <td><a href="{url_for('ver_chamado', ticket_id=t['id'])}"><b>{t['protocolo']}</b></a><div class="small muted">{t['criado_em']}</div></td>
          <td>{t['categoria']}<div class="small muted">{t['prioridade']}</div></td>
          <td><span class="tag">{t['status']}</span><div class="small {badge_cls}">{badge_txt}</div></td>
          <td class="muted">{t['titulo']}</td>
        </tr>
        """
    return f"""
    <div class="grid">
      <div class="card">
        <h1 class="h1">Meu painel</h1>
        <div class="muted">Bem-vindo(a), <b>{session.get('nome')}</b> • Perfil: {human_role(session.get('role'))}</div>
        <div class="hr"></div>
        <div class="row">
          <a class="btn btn-primary" href="{url_for('abrir_chamado')}">Abrir novo chamado</a>
        </div>
        <table>
          <thead><tr><th>Protocolo</th><th>Categoria</th><th>Status</th><th>Título</th></tr></thead>
          <tbody>{rows if rows else '<tr><td colspan="4" class="muted">Nenhum chamado ainda.</td></tr>'}</tbody>
        </table>
      </div>
      <div class="card">
        <div class="pill">Dicas rápidas</div>
        <div class="hr"></div>
        <div class="muted">
          Informe o setor, patrimônio (se houver), e detalhe o erro. Se possível, anexe print.
        </div>
      </div>
    </div>
    """

def render_ti_dashboard(meus, abertos):
    def rows_of(lst):
        rows = ""
        for t in lst:
            badge_txt, badge_cls = sla_badge(t)
            rows += f"""
            <tr>
              <td><a href="{url_for('ver_chamado', ticket_id=t['id'])}"><b>{t['protocolo']}</b></a><div class="small muted">{t['criado_em']}</div></td>
              <td class="muted">{t['solicitante_nome']}<div class="small muted">{t['solicitante_setor']}</div></td>
              <td>{t['categoria']}<div class="small muted">{t['prioridade']}</div></td>
              <td><span class="tag">{t['status']}</span><div class="small {badge_cls}">{badge_txt}</div></td>
              <td class="muted">{t['titulo']}</td>
            </tr>
            """
        return rows or '<tr><td colspan="5" class="muted">Nada por aqui.</td></tr>'

    return f"""
    <div class="card">
      <h1 class="h1">Painel TI</h1>
      <div class="muted">Bem-vindo(a), <b>{session.get('nome')}</b> • Perfil: {human_role(session.get('role'))}</div>
      <div class="hr"></div>

      <div class="row">
        <a class="btn btn-primary" href="{url_for('ti_painel')}">Fila completa</a>
        <a class="btn btn-outline" href="{url_for('usuarios')}">Gerenciar usuários</a>
        <a class="btn btn-info" href="{url_for('stats')}">Gráficos (mensal)</a>
        <a class="btn btn-outline" href="{url_for('exportar_pdf_geral')}">Relatório PDF</a>
      </div>

      <div class="hr"></div>
      <h2 class="h1" style="font-size:16px;margin-top:0">Meus atendimentos</h2>
      <table>
        <thead><tr><th>Protocolo</th><th>Solicitante</th><th>Categoria</th><th>Status/SLA</th><th>Título</th></tr></thead>
        <tbody>{rows_of(meus)}</tbody>
      </table>

      <div class="hr"></div>
      <h2 class="h1" style="font-size:16px;margin-top:0">Abertos no sistema</h2>
      <table>
        <thead><tr><th>Protocolo</th><th>Solicitante</th><th>Categoria</th><th>Status/SLA</th><th>Título</th></tr></thead>
        <tbody>{rows_of(abertos)}</tbody>
      </table>
    </div>
    """

# ====== TICKETS ======
@app.route("/abrir", methods=["GET","POST"])
def abrir_chamado():
    r = require_login()
    if r: return r

    if request.method == "POST":
        titulo = (request.form.get("titulo") or "").strip()
        categoria = request.form.get("categoria") or "Outros"
        prioridade = request.form.get("prioridade") or "Média"
        descricao = (request.form.get("descricao") or "").strip()
        patrimonio = (request.form.get("patrimonio") or "").strip()

        if not titulo or not descricao:
            return render("Abrir chamado", abrir_form(),
                          flash_msg="Preencha pelo menos Título e Descrição.", flash_type="bad")

        created_dt = datetime.now()
        sla_h, due_dt = sla_due(prioridade, created_dt)

        ticket_id = uuid.uuid4().hex
        protocolo = gerar_protocolo()

        data = {
            "id": ticket_id,
            "protocolo": protocolo,
            "titulo": titulo,
            "categoria": categoria,
            "prioridade": prioridade,
            "descricao": descricao,
            "patrimonio": patrimonio,
            "status": "Aberto",
            "criado_em": dt_str(created_dt),
            "atualizado_em": dt_str(created_dt),
            "solicitante_usuario": session.get("user"),
            "solicitante_nome": session.get("nome"),
            "solicitante_setor": session.get("setor"),
            "solicitante_email": session.get("email",""),
            "responsavel": None,
            "sla_horas": sla_h,
            "due_at": dt_str(due_dt),
            "first_response_at": None,
            "resolved_at": None,
        }
        db_create_ticket(data)
        db_add_history(ticket_id, session.get("user"), "Chamado aberto")

        # anexos
        if "anexos" in request.files:
            files = request.files.getlist("anexos")
            for f in files:
                if not f or not f.filename:
                    continue
                fname = secure_filename(f.filename)
                ext = os.path.splitext(fname)[1].lower()
                if ext not in [".png",".jpg",".jpeg",".pdf",".doc",".docx",".xls",".xlsx",".txt"]:
                    continue
                new_name = f"{uuid.uuid4().hex}{ext}"
                f.save(os.path.join(UPLOAD_FOLDER, new_name))
                db_add_attachment(ticket_id, new_name, fname)

        # e-mail: novo chamado
        notify_ticket_event(ticket_id, "opened")

        return redirect(url_for("ver_chamado", ticket_id=ticket_id))

    return render("Abrir chamado", abrir_form())

def abrir_form():
    opts_cat = "".join([f"<option>{c}</option>" for c in CATEGORIAS])
    opts_pri = "".join([f"<option>{p}</option>" for p in PRIORIDADES])
    return f"""
    <div class="card">
      <h1 class="h1">Abrir chamado</h1>
      <div class="muted">SLA será calculado automaticamente pela prioridade.</div>
      <div class="hr"></div>
      <form method="post" enctype="multipart/form-data">
        <div class="field">
          <label class="muted">Título</label>
          <input name="titulo" placeholder="Ex: Sem acesso ao sistema X / Impressora não imprime" required>
        </div>

        <div class="row">
          <div class="field" style="flex:1;min-width:220px">
            <label class="muted">Categoria</label>
            <select name="categoria">{opts_cat}</select>
          </div>
          <div class="field" style="flex:1;min-width:220px">
            <label class="muted">Prioridade (define SLA)</label>
            <select name="prioridade">{opts_pri}</select>
            <div class="small muted">Crítica: {SLA_HORAS["Crítica"]}h • Alta: {SLA_HORAS["Alta"]}h • Média: {SLA_HORAS["Média"]}h • Baixa: {SLA_HORAS["Baixa"]}h</div>
          </div>
        </div>

        <div class="field">
          <label class="muted">Patrimônio/Identificação (opcional)</label>
          <input name="patrimonio" placeholder="Ex: PC-12345 / Monitor-9876">
        </div>

        <div class="field">
          <label class="muted">Descrição</label>
          <textarea name="descricao" placeholder="Descreva o problema, mensagem de erro, quando começou, o que já tentou..." required></textarea>
        </div>

        <div class="field">
          <label class="muted">Anexos</label>
          <input type="file" name="anexos" multiple>
          <div class="small muted">Tipos: png, jpg, pdf, doc/docx, xls/xlsx, txt</div>
        </div>

        <div class="row">
          <button class="btn btn-primary" type="submit">Registrar chamado</button>
          <a class="btn btn-outline" href="{url_for('dashboard')}">Cancelar</a>
        </div>
      </form>
    </div>
    """

@app.route("/chamado/<ticket_id>", methods=["GET","POST"])
def ver_chamado(ticket_id):
    r = require_login()
    if r: return r

    t = db_get_ticket(ticket_id)
    if not t:
        abort(404)

    # permissão
    if session.get("role") not in ["ti","admin"] and t["solicitante_usuario"] != session.get("user"):
        abort(403)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "comentar":
            msg = (request.form.get("msg") or "").strip()
            if msg:
                db_add_comment(ticket_id, session.get("user"), msg)
                db_add_history(ticket_id, session.get("user"), "Comentou no chamado")
                db_update_ticket(ticket_id, atualizado_em=now_str())
                notify_ticket_event(ticket_id, "comment")

        elif action == "assumir":
            require_role("ti","admin")
            # primeira resposta (se ainda não tiver)
            if not t.get("first_response_at"):
                db_update_ticket(ticket_id, first_response_at=now_str())
            new_status = "Em andamento" if t["status"] == "Aberto" else t["status"]
            db_update_ticket(ticket_id, responsavel=session.get("user"), status=new_status, atualizado_em=now_str())
            db_add_history(ticket_id, session.get("user"), "Assumiu o chamado")
            notify_ticket_event(ticket_id, "status", {"status": new_status})

        # ✅ NOVO: botão para encerrar rapidamente quando estiver "Em andamento"
        elif action == "encerrar":
            require_role("ti","admin")

            # (opcional) só responsável ou admin pode encerrar
            if t.get("responsavel") and t["responsavel"] != session.get("user") and session.get("role") != "admin":
                abort(403)

            fields = {
                "status": "Encerrado",
                "atualizado_em": now_str(),
            }

            # primeira resposta
            if not t.get("first_response_at"):
                fields["first_response_at"] = now_str()

            # marca encerramento
            if not t.get("resolved_at"):
                fields["resolved_at"] = now_str()

            db_update_ticket(ticket_id, **fields)
            db_add_history(ticket_id, session.get("user"), "Chamado encerrado pelo botão")
            notify_ticket_event(ticket_id, "status", {"status": "Encerrado"})

        elif action == "atualizar_status":
            require_role("ti","admin")

            # ✅ CORREÇÃO: strip() para evitar "Encerrado " / "Em andamento " etc.
            novo = (request.form.get("status") or t["status"]).strip()

            if novo in STATUS:
                fields = {"status": novo, "atualizado_em": now_str()}

                # primeira resposta
                if not t.get("first_response_at") and novo in ["Em andamento","Aguardando usuário","Resolvido","Encerrado"]:
                    fields["first_response_at"] = now_str()

                # resolvido/encerrado
                if novo in ["Resolvido","Encerrado"] and not t.get("resolved_at"):
                    fields["resolved_at"] = now_str()

                db_update_ticket(ticket_id, **fields)
                db_add_history(ticket_id, session.get("user"), f"Status alterado para {novo}")
                notify_ticket_event(ticket_id, "status", {"status": novo})

        elif action == "excluir":
            require_role("admin")
            db_delete_ticket(ticket_id)
            return redirect(url_for("ti_painel"))

        return redirect(url_for("ver_chamado", ticket_id=ticket_id))

    # render
    t = db_get_ticket(ticket_id)  # recarrega
    badge_txt, badge_cls = sla_badge(t)
    anexos = db_list_attachments(ticket_id)
    comentarios = db_list_comments(ticket_id)
    hist = db_list_history(ticket_id)

    anexos_html = "".join([f'<li><a href="{url_for("baixar_anexo", filename=a["arquivo"])}">{a["nome_original"]}</a></li>' for a in anexos]) \
                  if anexos else '<li class="muted">Sem anexos.</li>'

    comentarios_html = ""
    for c in comentarios:
        comentarios_html += f"""
          <div class="msg">
            <div class="small muted">{c["quando"]} • <b>{c["por"]}</b></div>
            <div>{c["msg"]}</div>
          </div>
        """
    if not comentarios_html:
        comentarios_html = '<div class="muted">Sem comentários.</div>'

    hist_html = ""
    for h in hist:
        hist_html += f'<li class="muted"><b>{h["quando"]}</b> • {h["por"]}: {h["acao"]}</li>'

    # controles TI
    ti_controls = ""
    if session.get("role") in ["ti","admin"]:
        opts_status = "".join([f'<option {"selected" if s==t["status"] else ""}>{s}</option>' for s in STATUS])

        btn_assumir = f"""
          <form method="post" style="display:inline">
            <input type="hidden" name="action" value="assumir"/>
            <button class="btn btn-primary" type="submit">Assumir</button>
          </form>
        """ if not t.get("responsavel") else ""

        # ✅ Botão encerrar aparece somente em "Em andamento"
        btn_encerrar = ""
        if (t.get("status") or "").strip() == "Em andamento":
            btn_encerrar = f"""
              <form method="post" style="display:inline" onsubmit="return confirm('Encerrar este chamado?')">
                <input type="hidden" name="action" value="encerrar"/>
                <button class="btn btn-danger" type="submit">Encerrar chamado</button>
              </form>
            """

        btn_excluir = f"""
          <form method="post" style="display:inline" onsubmit="return confirm('Excluir este chamado? (somente admin)')">
            <input type="hidden" name="action" value="excluir"/>
            <button class="btn btn-danger" type="submit">Excluir</button>
          </form>
        """ if session.get("role") == "admin" else ""

        ti_controls = f"""
        <div class="hr"></div>
        <div class="row">
          {btn_assumir}
          {btn_encerrar}
          <form method="post" style="display:inline">
            <input type="hidden" name="action" value="atualizar_status"/>
            <select name="status">{opts_status}</select>
            <button class="btn btn-outline" type="submit">Atualizar status</button>
          </form>
          <a class="btn btn-info" href="{url_for('exportar_pdf_chamado', ticket_id=t['id'])}">PDF do chamado</a>
          {btn_excluir}
        </div>
        """

    content = f"""
    <div class="grid">
      <div class="card">
        <h1 class="h1">Chamado {t["protocolo"]}</h1>
        <div class="row">
          <span class="tag">{t["status"]}</span>
          <span class="tag">{t["categoria"]}</span>
          <span class="tag">Prioridade: {t["prioridade"]}</span>
          <span class="tag">Responsável: {t["responsavel"] or "—"}</span>
          <span class="tag">SLA: {t["sla_horas"]}h</span>
          <span class="tag {badge_cls}">{badge_txt}</span>
        </div>
        <div class="hr"></div>
        <div><b>Título:</b> {t["titulo"]}</div>
        <div class="small muted">Criado em {t["criado_em"]} • Atualizado em {t["atualizado_em"]}</div>
        <div class="small muted">Vencimento SLA: <b>{t["due_at"] or "—"}</b> • 1ª resposta: <b>{t["first_response_at"] or "—"}</b> • Resolvido: <b>{t["resolved_at"] or "—"}</b></div>
        <div class="hr"></div>
        <div><b>Solicitante:</b> {t["solicitante_nome"]} <span class="muted">({t["solicitante_usuario"]})</span></div>
        <div class="muted"><b>Setor:</b> {t["solicitante_setor"] or "—"} • <b>Patrimônio:</b> {t["patrimonio"] or "—"}</div>
        <div class="hr"></div>
        <div><b>Descrição:</b></div>
        <div class="msg">{t["descricao"]}</div>

        {ti_controls}

        <div class="hr"></div>
        <h2 class="h1" style="font-size:16px;margin-top:0">Comentários</h2>
        {comentarios_html}

        <form method="post" class="msg">
          <input type="hidden" name="action" value="comentar"/>
          <div class="field" style="margin:0">
            <label class="muted">Adicionar comentário</label>
            <textarea name="msg" placeholder="Escreva uma atualização, solicitação de informação, solução aplicada..."></textarea>
          </div>
          <div class="row">
            <button class="btn btn-outline" type="submit">Enviar</button>
            <a class="btn btn-outline" href="{url_for('dashboard')}">Voltar</a>
          </div>
        </form>
      </div>

      <div class="card">
        <div class="pill">Anexos</div>
        <div class="hr"></div>
        <ul>{anexos_html}</ul>

        <div class="hr"></div>
        <div class="pill">Histórico</div>
        <div class="hr"></div>
        <ul>{hist_html}</ul>
      </div>
    </div>
    """
    return render("Chamado", content)

@app.route("/uploads/<filename>")
def baixar_anexo(filename):
    r = require_login()
    if r: return r
    path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, as_attachment=True)

# ====== TI PANEL ======
@app.route("/ti")
def ti_painel():
    r = require_login()
    if r: return r
    require_role("ti","admin")

    status_f = request.args.get("status") or ""
    cat_f = request.args.get("categoria") or ""
    q = (request.args.get("q") or "").strip()

    tickets = db_list_tickets({"status": status_f, "categoria": cat_f, "q": q})

    opts_status = '<option value="">Todos</option>' + "".join([f'<option value="{s}" {"selected" if s==status_f else ""}>{s}</option>' for s in STATUS])
    opts_cat = '<option value="">Todas</option>' + "".join([f'<option value="{c}" {"selected" if c==cat_f else ""}>{c}</option>' for c in CATEGORIAS])

    rows = ""
    for t in tickets:
        badge_txt, badge_cls = sla_badge(t)
        rows += f"""
        <tr>
          <td><a href="{url_for('ver_chamado', ticket_id=t['id'])}"><b>{t['protocolo']}</b></a><div class="small muted">{t['criado_em']}</div></td>
          <td class="muted">{t['solicitante_nome']}<div class="small muted">{t['solicitante_setor']}</div></td>
          <td>{t['categoria']}<div class="small muted">{t['prioridade']}</div></td>
          <td><span class="tag">{t['status']}</span><div class="small {badge_cls}">{badge_txt}</div></td>
          <td class="muted">{t['titulo']}</td>
        </tr>
        """
    if not rows:
        rows = '<tr><td colspan="5" class="muted">Nenhum resultado.</td></tr>'

    content = f"""
    <div class="card">
      <h1 class="h1">Fila de chamados (TI)</h1>
      <div class="muted">Filtros rápidos e visão completa com SLA.</div>
      <div class="hr"></div>

      <form class="row" method="get">
        <select name="status">{opts_status}</select>
        <select name="categoria">{opts_cat}</select>
        <input name="q" placeholder="Buscar por protocolo, título ou descrição..." value="{q}">
        <button class="btn btn-outline" type="submit">Filtrar</button>
        <a class="btn btn-outline" href="{url_for('ti_painel')}">Limpar</a>
      </form>

      <div class="hr"></div>
      <div class="row">
        <a class="btn btn-info" href="{url_for('stats')}">Gráficos (mensal)</a>
        <a class="btn btn-outline" href="{url_for('exportar_pdf_geral')}">Relatório PDF</a>
        <a class="btn btn-outline" href="{url_for('exportar_csv')}">Exportar CSV</a>
      </div>

      <table>
        <thead><tr><th>Protocolo</th><th>Solicitante</th><th>Categoria</th><th>Status/SLA</th><th>Título</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    """
    return render("Painel TI", content)

# ====== USERS ======
@app.route("/usuarios", methods=["GET","POST"])
def usuarios():
    r = require_login()
    if r: return r
    require_role("ti","admin")

    if request.method == "POST":
        action = request.form.get("action")

        if action == "criar":
            require_role("admin")
            username = (request.form.get("username") or "").strip()
            nome = (request.form.get("nome") or "").strip()
            setor = (request.form.get("setor") or "").strip()
            email = (request.form.get("email") or "").strip()
            role = request.form.get("role") or "user"
            senha = request.form.get("senha") or ""

            if not username or not senha:
                return render("Usuários", usuarios_page(db_list_users()),
                              flash_msg="Informe usuário e senha.", flash_type="bad")

            if db_user_exists(username):
                return render("Usuários", usuarios_page(db_list_users()),
                              flash_msg="Usuário já existe.", flash_type="bad")

            if role not in ["user","ti","admin"]:
                role = "user"

            db_create_user(username, senha, role, nome or username, setor, email)
            return redirect(url_for("usuarios"))

        if action == "reset_senha":
            require_role("admin")
            username = (request.form.get("username") or "").strip()
            nova = request.form.get("nova") or ""
            if username and len(nova) >= 4 and db_user_exists(username):
                db_set_password(username, nova)
            return redirect(url_for("usuarios"))

        if action == "apagar":
            require_role("admin")
            username = (request.form.get("username") or "").strip()
            if username != "admin" and db_user_exists(username):
                db_delete_user(username)
            return redirect(url_for("usuarios"))

    return render("Usuários", usuarios_page(db_list_users()))

def usuarios_page(users):
    role = session.get("role")
    rows = ""
    for info in users:
        rows += f"""
        <tr>
          <td><b>{info["username"]}</b></td>
          <td class="muted">{info.get("nome","")}</td>
          <td class="muted">{info.get("setor","")}</td>
          <td class="muted">{info.get("email","")}</td>
          <td><span class="tag">{human_role(info.get("role","user"))}</span></td>
        </tr>
        """

    admin_forms = ""
    if role == "admin":
        admin_forms = f"""
        <div class="hr"></div>
        <h2 class="h1" style="font-size:16px;margin-top:0">Criar usuário</h2>
        <form method="post" class="msg">
          <input type="hidden" name="action" value="criar"/>
          <div class="row">
            <input name="username" placeholder="usuario.login" required>
            <input name="nome" placeholder="Nome completo">
            <input name="setor" placeholder="Setor">
            <input name="email" placeholder="E-mail (opcional)">
            <select name="role">
              <option value="user">Usuário</option>
              <option value="ti">TI</option>
              <option value="admin">Administrador</option>
            </select>
            <input name="senha" placeholder="Senha inicial" required>
            <button class="btn btn-primary" type="submit">Criar</button>
          </div>
          <div class="small muted">Se quiser e-mail ao usuário, cadastre o e-mail dele aqui.</div>
        </form>

        <h2 class="h1" style="font-size:16px;margin-top:0">Resetar senha</h2>
        <form method="post" class="msg">
          <input type="hidden" name="action" value="reset_senha"/>
          <div class="row">
            <input name="username" placeholder="usuario.login" required>
            <input name="nova" placeholder="Nova senha (mín. 4)" required>
            <button class="btn btn-outline" type="submit">Resetar</button>
          </div>
        </form>

        <h2 class="h1" style="font-size:16px;margin-top:0">Apagar usuário</h2>
        <form method="post" class="msg" onsubmit="return confirm('Apagar usuário?')">
          <input type="hidden" name="action" value="apagar"/>
          <div class="row">
            <input name="username" placeholder="usuario.login" required>
            <button class="btn btn-danger" type="submit">Apagar</button>
          </div>
          <div class="small muted">Obs: o usuário <b>admin</b> não pode ser apagado.</div>
        </form>
        """

    smtp_on = "ATIVO" if smtp_config()["enabled"] else "DESLIGADO (configure variáveis SMTP)"
    return f"""
    <div class="card">
      <h1 class="h1">Usuários</h1>
      <div class="muted">E-mail automático: <b>{smtp_on}</b></div>
      <div class="hr"></div>
      <table>
        <thead><tr><th>Usuário</th><th>Nome</th><th>Setor</th><th>E-mail</th><th>Perfil</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
      {admin_forms}
    </div>
    """

# ====== EXPORT CSV/PDF ======
@app.route("/exportar/csv")
def exportar_csv():
    r = require_login()
    if r: return r
    require_role("ti","admin")

    tickets = db_list_tickets()

    output = io.StringIO()
    w = csv.writer(output, delimiter=";")
    w.writerow([
        "protocolo","criado_em","atualizado_em","status","categoria","prioridade",
        "titulo","solicitante","setor","responsavel","patrimonio",
        "sla_horas","due_at","first_response_at","resolved_at"
    ])
    for t in tickets:
        w.writerow([
            t.get("protocolo"), t.get("criado_em"), t.get("atualizado_em"),
            t.get("status"), t.get("categoria"), t.get("prioridade"),
            t.get("titulo"), t.get("solicitante_nome"), t.get("solicitante_setor"),
            t.get("responsavel") or "", t.get("patrimonio") or "",
            t.get("sla_horas"), t.get("due_at") or "", t.get("first_response_at") or "", t.get("resolved_at") or ""
        ])

    mem = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name="chamados_ti.csv", mimetype="text/csv")

def pdf_header(pdf, title):
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 8, title, ln=1)
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 6, f"Gerado em: {now_str()}", ln=1)
    pdf.ln(2)

@app.route("/exportar/pdf")
def exportar_pdf_geral():
    r = require_login()
    if r: return r
    require_role("ti","admin")

    tickets = db_list_tickets()

    pdf = FPDF()
    pdf.add_page()
    pdf_header(pdf, "Relatorio - Chamados TI (SM Obras)")

    pdf.set_font("Arial", "B", 10)
    pdf.cell(35, 7, "Protocolo", 1)
    pdf.cell(25, 7, "Status", 1)
    pdf.cell(28, 7, "Categoria", 1)
    pdf.cell(22, 7, "Prior.", 1)
    pdf.cell(80, 7, "Titulo", 1, ln=1)

    pdf.set_font("Arial", "", 9)
    for t in tickets[:300]:
        pdf.cell(35, 7, str(t.get("protocolo",""))[:14], 1)
        pdf.cell(25, 7, str(t.get("status",""))[:12], 1)
        pdf.cell(28, 7, str(t.get("categoria",""))[:14], 1)
        pdf.cell(22, 7, str(t.get("prioridade",""))[:10], 1)
        titulo = (t.get("titulo","") or "")[:45]
        pdf.cell(80, 7, titulo, 1, ln=1)

    data = pdf.output(dest="S").encode("latin1")
    mem = io.BytesIO(data)
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name="relatorio_chamados.pdf", mimetype="application/pdf")

@app.route("/chamado/<ticket_id>/pdf")
def exportar_pdf_chamado(ticket_id):
    r = require_login()
    if r: return r

    t = db_get_ticket(ticket_id)
    if not t:
        abort(404)

    if session.get("role") not in ["ti","admin"] and t["solicitante_usuario"] != session.get("user"):
        abort(403)

    pdf = FPDF()
    pdf.add_page()
    pdf_header(pdf, f"Chamado {t['protocolo']}")

    pdf.set_font("Arial","B",11)
    pdf.multi_cell(0, 6, f"Titulo: {t.get('titulo','')}")
    pdf.set_font("Arial","",10)
    pdf.cell(0, 6, f"Status: {t.get('status','')} | Categoria: {t.get('categoria','')} | Prioridade: {t.get('prioridade','')}", ln=1)
    pdf.cell(0, 6, f"SLA: {t.get('sla_horas')}h | Vence em: {t.get('due_at') or '-'}", ln=1)
    pdf.cell(0, 6, f"Criado: {t.get('criado_em','')} | Atualizado: {t.get('atualizado_em','')}", ln=1)
    pdf.cell(0, 6, f"Solicitante: {t.get('solicitante_nome','')} ({t.get('solicitante_usuario','')})", ln=1)
    pdf.cell(0, 6, f"Setor: {t.get('solicitante_setor','')} | Responsavel: {t.get('responsavel') or '-'}", ln=1)
    pdf.cell(0, 6, f"Patrimonio: {t.get('patrimonio') or '-'}", ln=1)
    pdf.ln(2)

    pdf.set_font("Arial","B",11)
    pdf.cell(0, 7, "Descricao:", ln=1)
    pdf.set_font("Arial","",10)
    pdf.multi_cell(0, 6, t.get("descricao",""))

    pdf.ln(2)
    pdf.set_font("Arial","B",11)
    pdf.cell(0, 7, "Comentarios:", ln=1)
    pdf.set_font("Arial","",9)
    comments = db_list_comments(ticket_id)
    if not comments:
        pdf.multi_cell(0, 6, "Sem comentarios.")
    else:
        for c in comments[-30:]:
            pdf.multi_cell(0, 6, f"- {c['quando']} • {c['por']}: {c['msg']}")

    data = pdf.output(dest="S").encode("latin1")
    mem = io.BytesIO(data)
    mem.seek(0)
    return send_file(mem, as_attachment=True, download_name=f"chamado_{t['protocolo']}.pdf", mimetype="application/pdf")

# ====== STATS (GRÁFICOS MENSAIS) ======
def stats_monthly_last_12():
    """
    Retorna dados dos últimos 12 meses:
    - abertos por mês
    - resolvidos/encerrados por mês
    - vencidos (SLA vencido) por mês
    """
    now = datetime.now()
    months = []
    for i in range(11, -1, -1):
        m = (now.replace(day=1) - timedelta(days=1)).replace(day=1)  # mês anterior base
        # melhor: iterar por offset controlado
    # Vamos fazer robusto:
    months = []
    y, m = now.year, now.month
    for _ in range(12):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months = list(reversed(months))

    labels = [f"{y}-{m:02d}" for (y,m) in months]
    opened = [0]*12
    closed = [0]*12
    overdue = [0]*12

    with db() as conn:
        # abertos
        rows = conn.execute("SELECT criado_em, status, due_at FROM tickets").fetchall()
    for r in rows:
        created = parse_dt(r["criado_em"])
        key = f"{created.year}-{created.month:02d}"
        if key in labels:
            opened[labels.index(key)] += 1

        # encerrados/resolvidos (resolved_at)
        # se não tiver resolved_at mas status fechado, usa atualizado_em
        # (garante algo no gráfico)
        # -> aqui simplificado: resolved_at se existir.
        # para o fechamento, tentamos pegar resolved_at do ticket via query melhor:
    with db() as conn:
        rows2 = conn.execute("SELECT resolved_at, status, updated_at as atualizado_em FROM (SELECT resolved_at, status, atualizado_em as updated_at FROM tickets)").fetchall()
    for r in rows2:
        if r["resolved_at"]:
            dt = parse_dt(r["resolved_at"])
            key = f"{dt.year}-{dt.month:02d}"
            if key in labels:
                closed[labels.index(key)] += 1
        else:
            # se status fechado, conta no mês do atualizado_em
            if r["status"] in ["Resolvido","Encerrado"]:
                dt = parse_dt(r["atualizado_em"])
                key = f"{dt.year}-{dt.month:02d}"
                if key in labels:
                    closed[labels.index(key)] += 1

    # vencidos: ainda abertos e due_at < agora
    now_dt = datetime.now()
    with db() as conn:
        rows3 = conn.execute("SELECT criado_em, status, due_at FROM tickets").fetchall()
    for r in rows3:
        if r["status"] in ["Resolvido","Encerrado"]:
            continue
        if not r["due_at"]:
            continue
        due = parse_dt(r["due_at"])
        if due < now_dt:
            created = parse_dt(r["criado_em"])
            key = f"{created.year}-{created.month:02d}"
            if key in labels:
                overdue[labels.index(key)] += 1

    return labels, opened, closed, overdue

@app.route("/stats")
def stats():
    r = require_login()
    if r: return r
    require_role("ti","admin")

    labels, opened, closed, overdue = stats_monthly_last_12()

    # gráfico sem libs: canvas + JS simples
    # desenha 3 séries em barras empilhadas lado a lado (bem básico e funcional)
    data = {
        "labels": labels,
        "opened": opened,
        "closed": closed,
        "overdue": overdue
    }
    data_json = json.dumps(data)

    # também mostra tabela de apoio
    rows = ""
    for i, lab in enumerate(labels):
        rows += f"<tr><td><b>{lab}</b></td><td>{opened[i]}</td><td>{closed[i]}</td><td>{overdue[i]}</td></tr>"

    content = f"""
    <div class="grid">
      <div class="card">
        <h1 class="h1">Gráficos mensais (últimos 12 meses)</h1>
        <div class="muted">Abertos vs Fechados vs SLA Vencido (abertos)</div>
        <div class="hr"></div>
        <canvas id="chart" height="280"></canvas>
        <div class="small muted">Dica: se quiser, dá para separar por categoria depois.</div>
      </div>
      <div class="card">
        <div class="pill">Tabela</div>
        <div class="hr"></div>
        <table>
          <thead><tr><th>Mês</th><th>Abertos</th><th>Fechados</th><th>Vencidos</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </div>

    <script>
      const payload = {data_json};
      const canvas = document.getElementById("chart");
      const ctx = canvas.getContext("2d");

      function maxVal(arrs){{
        let m = 0;
        arrs.forEach(a => a.forEach(v => m = Math.max(m, v)));
        return m || 1;
      }}

      function draw(){{
        const w = canvas.width = canvas.clientWidth;
        const h = canvas.height = canvas.height; // mantém height
        ctx.clearRect(0,0,w,h);

        const padL = 46, padR = 14, padT = 12, padB = 44;
        const chartW = w - padL - padR;
        const chartH = h - padT - padB;

        const labels = payload.labels;
        const opened = payload.opened;
        const closed = payload.closed;
        const overdue = payload.overdue;

        const ymax = maxVal([opened, closed, overdue]);
        const ticks = 5;

        // grid + eixo y
        ctx.globalAlpha = 1;
        ctx.font = "12px Segoe UI, Arial";
        ctx.fillStyle = "rgba(159,176,208,.9)";
        ctx.strokeStyle = "rgba(31,45,77,.9)";

        for(let i=0;i<=ticks;i++){{
          const y = padT + (chartH * i / ticks);
          ctx.beginPath();
          ctx.moveTo(padL, y);
          ctx.lineTo(w - padR, y);
          ctx.stroke();
          const val = Math.round(ymax * (1 - i/ticks));
          ctx.fillText(val.toString(), 8, y+4);
        }}

        // barras (3 por mês)
        const n = labels.length;
        const gap = 10;
        const groupW = (chartW / n);
        const barW = Math.max(6, (groupW - gap) / 3);

        function bar(x, v, idx){{
          const bh = (v / ymax) * chartH;
          const y = padT + chartH - bh;
          // cores fixas para diferenciar (não depende de lib)
          const colors = ["#22c55e", "#60a5fa", "#ef4444"]; // abertos, fechados, vencidos
          ctx.fillStyle = colors[idx];
          ctx.globalAlpha = 0.9;
          ctx.fillRect(x, y, barW, bh);
          ctx.globalAlpha = 1;
        }}

        for(let i=0;i<n;i++){{
          const gx = padL + i * groupW + gap/2;
          bar(gx + 0*(barW), opened[i], 0);
          bar(gx + 1*(barW), closed[i], 1);
          bar(gx + 2*(barW), overdue[i], 2);

          // rótulo (mês) - mostra a cada 2 meses pra não embolar
          if(i % 2 === 0){{
            ctx.fillStyle = "rgba(159,176,208,.9)";
            ctx.save();
            ctx.translate(gx + barW, padT + chartH + 18);
            ctx.rotate(-0.35);
            ctx.fillText(labels[i], 0, 0);
            ctx.restore();
          }}
        }}

        // legenda
        const lx = padL, ly = h - 16;
        ctx.fillStyle = "#22c55e"; ctx.fillRect(lx, ly-10, 10, 10);
        ctx.fillStyle = "rgba(232,238,252,.9)"; ctx.fillText("Abertos", lx+14, ly-1);
        ctx.fillStyle = "#60a5fa"; ctx.fillRect(lx+90, ly-10, 10, 10);
        ctx.fillStyle = "rgba(232,238,252,.9)"; ctx.fillText("Fechados", lx+104, ly-1);
        ctx.fillStyle = "#ef4444"; ctx.fillRect(lx+190, ly-10, 10, 10);
        ctx.fillStyle = "rgba(232,238,252,.9)"; ctx.fillText("Vencidos", lx+204, ly-1);
      }}

      draw();
      window.addEventListener("resize", draw);
    </script>
    """
    return render("Gráficos", content)

# ====== EXPORT PDF ROUTE ALIAS ======
@app.route("/exportar/pdf_geral")
def exportar_pdf_geral_alias():
    return exportar_pdf_geral()

# ====== USERS ROUTE ALIAS ======
@app.route("/users")
def usuarios_alias():
    return usuarios()

# ====== RUN INIT DB ======
init_db()

if __name__ == "__main__":
    app.run(host=HOST_IP, port=PORT, debug=True)