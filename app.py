from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from collections import defaultdict
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from datetime import datetime
from flask import flash
import os

load_dotenv()

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "horizon-dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///horizon.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 280,
    "pool_size": 5,
    "max_overflow": 10,
}

db = SQLAlchemy(app)

# LOGIN MANAGER
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Debes iniciar sesión para continuar."

class Usuario(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    foto = db.Column(db.String(255))
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)  

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

class Movimiento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)  # ingreso, gasto, deuda
    nombre = db.Column(db.String(120), nullable=False)
    categoria = db.Column(db.String(80), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)

class MetaAhorro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    categoria = db.Column(db.String(80), nullable=False)
    objetivo = db.Column(db.Float, nullable=False)
    ahorrado = db.Column(db.Float, default=0)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow) 
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False) 

class Presupuesto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    categoria = db.Column(db.String(80), nullable=False)
    limite = db.Column(db.Float, nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow) 
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False) 
      

@app.route("/")
@login_required
def dashboard():
    tipo_filtro = request.args.get("tipo", "")
    buscar = request.args.get("buscar", "")

    query = Movimiento.query.filter_by(usuario_id=current_user.id)

    if tipo_filtro:
        query = query.filter(Movimiento.tipo == tipo_filtro)

    if buscar:
        query = query.filter(
            db.or_(
                Movimiento.nombre.ilike(f"%{buscar}%"),
                Movimiento.categoria.ilike(f"%{buscar}%")
            )
        )

    movimientos = query.order_by(Movimiento.fecha.desc()).all()
    todos_movimientos = Movimiento.query.filter_by(usuario_id=current_user.id).all()

    ingresos = sum(m.monto for m in todos_movimientos if m.tipo == "ingreso")
    gastos = sum(m.monto for m in todos_movimientos if m.tipo == "gasto")
    deudas = sum(m.monto for m in todos_movimientos if m.tipo == "deuda")

    saldo = ingresos - gastos - deudas
    ahorro_neto = ingresos - gastos

    gastos_por_categoria = {}

    for m in todos_movimientos:
        if m.tipo == "gasto":
            if m.categoria not in gastos_por_categoria:
                gastos_por_categoria[m.categoria] = 0

            gastos_por_categoria[m.categoria] += m.monto

    categorias = list(gastos_por_categoria.keys())
    valores = list(gastos_por_categoria.values())

    insights = []

    if gastos_por_categoria:
        categoria_mayor = max(gastos_por_categoria, key=gastos_por_categoria.get)
        monto_mayor = gastos_por_categoria[categoria_mayor]
        insights.append(f"Tu mayor gasto es en {categoria_mayor} (${monto_mayor:,.0f})")

    if ingresos > 0:
        porcentaje_ahorro = (ahorro_neto / ingresos) * 100
        insights.append(f"Tu ahorro representa el {porcentaje_ahorro:.0f}% de tus ingresos")

    if gastos > ingresos:
        insights.append("⚠️ Estás gastando más de lo que ingresas")

    metas = MetaAhorro.query.filter_by(usuario_id=current_user.id).order_by(MetaAhorro.fecha_creacion.desc()).all()

    presupuestos = Presupuesto.query.filter_by(usuario_id=current_user.id).order_by(Presupuesto.fecha_creacion.desc()).all()

    presupuestos_data = []
    alertas = []

    for p in presupuestos:
        gastado = gastos_por_categoria.get(p.categoria, 0)
        porcentaje = (gastado / p.limite * 100) if p.limite > 0 else 0
        restante = p.limite - gastado

        presupuestos_data.append({
            "id": p.id,
            "categoria": p.categoria,
            "limite": p.limite,
            "gastado": gastado,
            "porcentaje": porcentaje,
            "restante": restante
        })

        # ALERTAS AUTOMÁTICAS
        if porcentaje >= 100:
            alertas.append(f"⚠️ Excediste el presupuesto de {p.categoria} por ${abs(restante):,.0f}")
        elif porcentaje >= 90:
            alertas.append(f"🚨 Ya usaste el {porcentaje:.0f}% del presupuesto de {p.categoria}")
        elif porcentaje >= 80:
            alertas.append(f"⚡ Te queda poco presupuesto en {p.categoria}: ${restante:,.0f}")

    return render_template(
        "dashboard.html",
        movimientos=movimientos,
        metas=metas,
        presupuestos=presupuestos_data,
        alertas=alertas,
        ingresos=ingresos,
        gastos=gastos,
        deudas=deudas,
        saldo=saldo,
        ahorro_neto=ahorro_neto,
        tipo_filtro=tipo_filtro,
        buscar=buscar,
        categorias=categorias,
        valores=valores,
        insights=insights
    )

@app.route("/nuevo", methods=["POST"])
@login_required
def nuevo_movimiento():
    tipo = request.form.get("tipo")
    nombre = request.form.get("nombre")
    categoria = request.form.get("categoria")
    monto = request.form.get("monto")

    if not tipo or not nombre or not categoria or not monto:
        return redirect(url_for("dashboard"))

    movimiento = Movimiento(
        tipo=tipo,
        nombre=nombre,
        categoria=categoria,
        monto=float(monto),
        usuario_id=current_user.id
    )

    db.session.add(movimiento)
    db.session.commit()
    flash("Movimiento guardado correctamente", "success")

    return redirect(url_for("dashboard"))

@app.route("/nueva-meta", methods=["POST"])
@login_required
def nueva_meta():
    nombre = request.form.get("nombre")
    categoria = request.form.get("categoria")
    objetivo = request.form.get("objetivo")
    ahorrado = request.form.get("ahorrado", 0)

    if not nombre or not categoria or not objetivo:
        return redirect(url_for("dashboard"))

    meta = MetaAhorro(
        nombre=nombre,
        categoria=categoria,
        objetivo=float(objetivo),
        ahorrado=float(ahorrado or 0),
        usuario_id=current_user.id
    )

    db.session.add(meta)
    db.session.commit()
    flash("Meta creada correctamente", "success")

    return redirect(url_for("dashboard")) 

@app.route("/nuevo-presupuesto", methods=["POST"])
@login_required
def nuevo_presupuesto():
    categoria = request.form.get("categoria")
    limite = request.form.get("limite")

    if not categoria or not limite:
        return redirect(url_for("dashboard"))

    presupuesto = Presupuesto(
        categoria=categoria,
        limite=float(limite),
        usuario_id=current_user.id
    )

    db.session.add(presupuesto)
    db.session.commit()
    flash("Presupuesto creado correctamente", "success")

    return redirect(url_for("dashboard"))


@app.route("/abonar-meta/<int:id>", methods=["POST"])
@login_required
def abonar_meta(id):
    meta = MetaAhorro.query.filter_by(id=id, usuario_id=current_user.id).first_or_404()

    abono = request.form.get("abono")

    if abono:
        meta.ahorrado += float(abono)
        db.session.commit()
        flash("Meta actualizada correctamente", "success")

    return redirect(url_for("dashboard"))


@app.route("/eliminar/<int:id>", methods=["POST"])
@login_required
def eliminar_movimiento(id):
    movimiento = Movimiento.query.filter_by(id=id, usuario_id=current_user.id).first_or_404()

    db.session.delete(movimiento)
    db.session.commit()
    flash("Eliminado correctamente", "danger")

    return redirect(url_for("dashboard"))

@app.route("/eliminar-meta/<int:id>", methods=["POST"])
@login_required
def eliminar_meta(id):
    meta = MetaAhorro.query.filter_by(id=id, usuario_id=current_user.id).first_or_404()

    db.session.delete(meta)
    db.session.commit()
    flash("Eliminado correctamente", "danger")

    return redirect(url_for("dashboard"))


@app.cli.command("crear-db")
def crear_db():
    db.create_all()
    print("Base de datos creada correctamente.")

@app.route("/eliminar-presupuesto/<int:id>", methods=["POST"])
@login_required
def eliminar_presupuesto(id):
    presupuesto = Presupuesto.query.filter_by(id=id, usuario_id=current_user.id).first_or_404()

    db.session.delete(presupuesto)
    db.session.commit()
    flash("Eliminado correctamente", "danger")

    return redirect(url_for("dashboard"))    

@app.route("/movimientos")
@login_required
def movimientos_page():
    movimientos = Movimiento.query.filter_by(usuario_id=current_user.id).order_by(Movimiento.fecha.desc()).all()

    return render_template(
        "movimientos.html",
        movimientos=movimientos
    )


@app.route("/presupuestos")
@login_required
def presupuestos_page():
    presupuestos = Presupuesto.query.filter_by(usuario_id=current_user.id).order_by(Presupuesto.fecha_creacion.desc()).all()

    return render_template(
        "presupuestos.html",
        presupuestos=presupuestos
    )


@app.route("/metas")
@login_required
def metas_page():
    metas = MetaAhorro.query.filter_by(usuario_id=current_user.id).order_by(MetaAhorro.fecha_creacion.desc()).all()

    return render_template(
        "metas.html",
        metas=metas
    )


@app.route("/reportes")
@login_required
def reportes_page():

    todos_movimientos = Movimiento.query.filter_by(usuario_id=current_user.id).all()

    gastos_por_categoria = {}

    for m in todos_movimientos:
        if m.tipo == "gasto":

            if m.categoria not in gastos_por_categoria:
                gastos_por_categoria[m.categoria] = 0

            gastos_por_categoria[m.categoria] += m.monto

    categorias = list(gastos_por_categoria.keys())
    valores = list(gastos_por_categoria.values())

    return render_template(
        "reportes.html",
        categorias=categorias,
        valores=valores
    )


@app.route("/ajustes")
@login_required
def ajustes_page():
    return render_template("ajustes.html")

@app.route("/editar-movimiento/<int:id>", methods=["POST"])
@login_required
def editar_movimiento(id):
    movimiento = Movimiento.query.filter_by(id=id, usuario_id=current_user.id).first_or_404()

    tipo = request.form.get("tipo")
    nombre = request.form.get("nombre")
    categoria = request.form.get("categoria")
    monto = request.form.get("monto")

    if tipo and nombre and categoria and monto:
        movimiento.tipo = tipo
        movimiento.nombre = nombre
        movimiento.categoria = categoria
        movimiento.monto = float(monto)

        db.session.commit()
        flash("Movimiento actualizado correctamente", "success")

    return redirect(url_for("dashboard"))    

@app.route("/editar-meta/<int:id>", methods=["POST"])
@login_required
def editar_meta(id):

    meta = MetaAhorro.query.filter_by(id=id, usuario_id=current_user.id).first_or_404()

    nombre = request.form.get("nombre")
    categoria = request.form.get("categoria")
    objetivo = request.form.get("objetivo")
    ahorrado = request.form.get("ahorrado")

    if nombre and categoria and objetivo and ahorrado:

        meta.nombre = nombre
        meta.categoria = categoria
        meta.objetivo = float(objetivo)
        meta.ahorrado = float(ahorrado)

        db.session.commit()

        flash("Meta actualizada correctamente", "success")

    return redirect(url_for("dashboard"))

@app.route("/editar-presupuesto/<int:id>", methods=["POST"])
@login_required
def editar_presupuesto(id):

    presupuesto = Presupuesto.query.filter_by(id=id, usuario_id=current_user.id).first_or_404()

    categoria = request.form.get("categoria")
    limite = request.form.get("limite")

    if categoria and limite:

        presupuesto.categoria = categoria
        presupuesto.limite = float(limite)

        db.session.commit()

        flash("Presupuesto actualizado correctamente", "success")

    return redirect(url_for("dashboard"))

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form.get("nombre")
        email = request.form.get("email")
        password = request.form.get("password")

        if not nombre or not email or not password:
            flash("Todos los campos son obligatorios", "danger")
            return redirect(url_for("registro"))

        existe = Usuario.query.filter_by(email=email).first()

        if existe:
            flash("Ese correo ya está registrado", "danger")
            return redirect(url_for("registro"))

        usuario = Usuario(
            nombre=nombre,
            email=email,
            password=generate_password_hash(password)
        )

        db.session.add(usuario)
        db.session.commit()

        flash("Cuenta creada correctamente", "success")
        return redirect(url_for("login"))

    return render_template("registro.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        usuario = Usuario.query.filter_by(email=email).first()

        if not usuario or not check_password_hash(usuario.password, password):
            flash("Correo o contraseña incorrectos", "danger")
            return redirect(url_for("login"))

        login_user(usuario)

        flash("Bienvenido a Horizon 360", "success")

        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():

    logout_user()

    flash("Sesión cerrada correctamente", "success")

    return redirect(url_for("login"))

@app.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():

    if request.method == "POST":

        nombre = request.form.get("nombre")

        if nombre:
            current_user.nombre = nombre

        foto = request.files.get("foto")

        if foto and foto.filename:

            filename = secure_filename(foto.filename)

            path = os.path.join("static/uploads", filename)

            foto.save(path)

            current_user.foto = filename

        db.session.commit()

        flash("Perfil actualizado", "success")

        return redirect(url_for("perfil"))

    return render_template("perfil.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)