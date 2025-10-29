from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy import func
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from functools import wraps

app = Flask(__name__)
app.secret_key = "victor123"

# ---------------------------
# CONFIGURAÇÃO DO POSTGRESQL REMOTO (NEON)
# ---------------------------
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_qA72jeXotgFY@ep-broad-sound-a4ymzr4n-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ---------------------------
# LOGIN MANAGER
# ---------------------------
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Faça login para acessar esta página."

# ---------------------------
# MODELOS
# ---------------------------
class Usuario(db.Model, UserMixin):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    cpf = db.Column(db.String(11), unique=True, nullable=False)
    senha = db.Column(db.String(100), nullable=False)
    cnh = db.Column(db.String(20), nullable=True)
    data_admissao = db.Column(db.Date, nullable=True)
    papel = db.Column(db.String(20), nullable=False, default="motorista")  # "admin" ou "motorista"
    ativo = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<Usuario {self.nome}>"


class Veiculo(db.Model):
    __tablename__ = "veiculos"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    placa = db.Column(db.String(7), unique=True, nullable=False)
    quilometragem = db.Column(db.Float, nullable=False)
    ativo = db.Column(db.Boolean, default=True)


class Abastecimento(db.Model):
    __tablename__ = "abastecimentos"
    id = db.Column(db.Integer, primary_key=True)
    litros = db.Column(db.Float, nullable=False)
    valor_total = db.Column(db.Float, nullable=False)
    veiculo_id = db.Column(db.Integer, db.ForeignKey('veiculos.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True)
    data_abastecimento = db.Column(db.Date, nullable=False)
    quilometragem = db.Column(db.Float, nullable=False)

    veiculo = db.relationship("Veiculo", backref=db.backref("abastecimentos", lazy=True))
    usuario = db.relationship("Usuario", backref=db.backref("abastecimentos", lazy=True))
# ---------------------------
# FUNÇÕES DE LOGIN
# ---------------------------
@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

def role_required(papel):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login"))
            if current_user.papel != papel:
                flash("Você não tem permissão para acessar esta página.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

# ---------------------------
# ROTAS
# ---------------------------

@app.route("/")
@login_required
def index():
    return redirect(url_for("login"))

from collections import defaultdict

@app.route("/dashboard_dados/<int:veiculo_id>")
@login_required
def dashboard_dados(veiculo_id):
    veiculo = Veiculo.query.get_or_404(veiculo_id)
    hoje = datetime.now()

    abastecimentos = (
        Abastecimento.query
        .filter_by(veiculo_id=veiculo_id)
        .order_by(Abastecimento.data_abastecimento.asc())
        .all()
    )

    # Calcula consumo (Km/L) de cada abastecimento
    abastecimentos_json = []
    for i, a in enumerate(abastecimentos):
        if i == 0:
            media_km_l = 0
        else:
            km_rodados = a.quilometragem - abastecimentos[i - 1].quilometragem
            media_km_l = round(km_rodados / a.litros, 2) if a.litros > 0 and km_rodados > 0 else 0

        abastecimentos_json.append({
            "data_abastecimento": a.data_abastecimento.strftime("%d/%m/%Y"),
            "data": a.data_abastecimento,
            "litros": a.litros,
            "valor_total": a.valor_total,
            "quilometragem": a.quilometragem,
            "media": media_km_l,
            "motorista": a.usuario.nome if a.usuario else "N/D"
        })

    # Define períodos
    semana_inicio = hoje - timedelta(days=7)
    mes_inicio = hoje - timedelta(days=30)
    ano_inicio = hoje - timedelta(days=365)

    def filtrar(inicio):
        return [a for a in abastecimentos_json if a["data"] >= inicio]

    dados_semana = filtrar(semana_inicio)
    dados_mes = filtrar(mes_inicio)
    dados_ano = filtrar(ano_inicio)

    # Agrupar médias por mês (para o gráfico anual)
    agrupado_mensal = defaultdict(list)
    for a in dados_ano:
        mes_label = a["data"].strftime("%b/%Y")
        if a["media"] > 0:
            agrupado_mensal[mes_label].append(a["media"])

    dados_ano_agrupado = [
        {"mes": m, "media": round(sum(v)/len(v), 2)} for m, v in agrupado_mensal.items()
    ]

    return jsonify({
        "tabela": abastecimentos_json,
        "semana": dados_semana,
        "mes": dados_mes,
        "ano": dados_ano_agrupado
    })



# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None  # variável para armazenar mensagens de erro
    if request.method == "POST":
        cpf = request.form["cpf"]
        senha = request.form["senha"]

        usuario = Usuario.query.filter_by(cpf=cpf).first()

        if usuario and usuario.senha == senha:
            login_user(usuario)
            return redirect(url_for("index"))
        else:
            erro = "CPF ou senha inválidos."  # mensagem enviada ao template

    return render_template("login.html", erro=erro)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ---------- ROTAS RESTRITAS ----------
@app.route("/motoristas", methods=["GET", "POST"])
@login_required
@role_required("admin")
def motoristas():
    if request.method == "POST":
        motorista = Usuario(
            nome=request.form["nome"],
            cpf=request.form["cpf"],
            senha=request.form["senha"],
            cnh=request.form["cnh"],
            data_admissao=datetime.strptime(request.form["data_admissao"], "%Y-%m-%d"),
            papel="motorista"
        )
        db.session.add(motorista)
        db.session.commit()
        flash("Motorista cadastrado com sucesso!", "success")
        return redirect(url_for("motoristas"))

    motoristas_list = Usuario.query.filter_by(papel="motorista").all()
    return render_template("cadastrar_motorista.html", motoristas=motoristas_list)

@app.route("/veiculos", methods=["GET", "POST"])
@login_required
@role_required("admin")
def veiculos():
    if request.method == "POST":
        veiculo = Veiculo(
            nome=request.form["nome"],
            placa=request.form["placa"],
            quilometragem=float(request.form["quilometragem"])
        )
        db.session.add(veiculo)
        db.session.commit()
        flash("Veículo cadastrado com sucesso!", "success")
        return redirect(url_for("veiculos"))

    veiculos_list = Veiculo.query.all()
    return render_template("veiculos.html", veiculos=veiculos_list)

@app.route("/abastecida", methods=["GET", "POST"])
@login_required
def abastecida():
    if current_user.papel not in ["motorista", "admin"]:
        flash("Você não tem permissão para acessar esta página.", "danger")
        return redirect(url_for("index"))

    veiculos = Veiculo.query.filter_by(ativo=True).all()

    if request.method == "POST":
        abastecimento = Abastecimento(
            litros=float(request.form["litros"]),
            valor_total=float(request.form["valor_total"]),
            veiculo_id=int(request.form["veiculo"]),
            quilometragem=float(request.form["quilometragem"]),
            data_abastecimento=datetime.strptime(request.form["data_abastecimento"], "%Y-%m-%d"),
            usuario_id=current_user.id
        )
        db.session.add(abastecimento)
        db.session.commit()
        flash("Abastecida cadastrada com sucesso!", "success")
        return redirect(url_for("abastecida"))

    return render_template("abastecida.html", veiculos=veiculos)


@app.route("/media")
@login_required
@role_required("admin")
def media():
    veiculos = Veiculo.query.filter_by(ativo=True).all()
    return render_template("dashboard.html", veiculos=veiculos)

@app.route("/cadastros")
@login_required
@role_required("admin")
def cadastros():
    motoristas = Usuario.query.filter_by(ativo=True, papel="motorista").all()
    veiculos = Veiculo.query.filter_by(ativo=True).all()
    return render_template("cadastros.html", motoristas=motoristas, veiculos=veiculos)

@app.route("/excluir_registro/<string:tipo>/<int:registro_id>", methods=["POST"])
@login_required
@role_required("admin")
def excluir_registro(tipo, registro_id):
    if tipo == "motorista":
        registro = Usuario.query.get_or_404(registro_id)
    elif tipo == "veiculo":
        registro = Veiculo.query.get_or_404(registro_id)
    else:
        return jsonify({"erro": "Tipo inválido"}), 400

    registro.ativo = False
    db.session.commit()
    return jsonify({"mensagem": f"{tipo.capitalize()} excluído com sucesso!"})



# ---------------------------
# RODA O SERVIDOR
# ---------------------------
if __name__ == "__main__":
    app.run()
