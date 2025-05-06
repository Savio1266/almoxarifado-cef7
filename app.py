from datetime import datetime
import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, send_file
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = 'chave_super_segura'
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ---------- BANCO DE DADOS ----------
def conectar():
    return sqlite3.connect('database.db', timeout=10)

def criar_tabelas():
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            nome TEXT UNIQUE,
                            senha TEXT,
                            aprovado INTEGER DEFAULT 0)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS itens (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            nome TEXT,
                            patrimonio TEXT,
                            modelo TEXT,
                            categoria TEXT,
                            local TEXT,
                            subitens TEXT,
                            quantidade INTEGER,
                            imagem TEXT,
                            descricao TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS historico (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            usuario TEXT,
                            acao TEXT,
                            item TEXT,
                            data TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS movimentacoes (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            item_id INTEGER,
                            tipo TEXT,
                            quantidade INTEGER,
                            motivo TEXT,
                            data TEXT,
                            usuario TEXT)''')
        conn.commit()

# ---------- PROTEÇÃO GLOBAL ----------
@app.before_request
def proteger_rotas():
    rotas_livres = ['index', 'login', 'cadastro', 'static']
    if request.endpoint not in rotas_livres:
        if 'usuario' not in session and not session.get('moderador'):
            return redirect(url_for('login'))

# ---------- FUNÇÕES AUXILIARES DO DASHBOARD ----------
def contar_itens():
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM itens")
        return cursor.fetchone()[0]

def itens_com_estoque_baixo(limite=5):
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM itens WHERE quantidade <= ?", (limite,))
        return cursor.fetchall()

def ultimos_historicos(n=5):
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM historico ORDER BY data DESC LIMIT ?", (n,))
        return cursor.fetchall()

# ---------- USUÁRIOS ----------
def adicionar_usuario(nome, senha):
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO usuarios (nome, senha) VALUES (?, ?)", (nome, senha))
        conn.commit()

def validar_usuario(nome, senha):
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE nome=? AND senha=? AND aprovado=1", (nome, senha))
        return cursor.fetchone()

def usuarios_pendentes():
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome FROM usuarios WHERE aprovado=0")
        return cursor.fetchall()

def usuarios_aprovados():
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome FROM usuarios WHERE aprovado=1 AND nome != 'SAVIO'")
        return cursor.fetchall()

def aprovar_usuario(id):
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE usuarios SET aprovado=1 WHERE id=?", (id,))
        conn.commit()

def rejeitar_usuario(id):
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usuarios WHERE id=?", (id,))
        conn.commit()

def excluir_usuario(id):
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usuarios WHERE id=?", (id,))
        conn.commit()

# ---------- ITENS ----------
def adicionar_item(dados, imagem):
    caminho_img = salvar_imagem(imagem) if imagem else ''
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO itens 
            (nome, patrimonio, modelo, categoria, local, subitens, quantidade, imagem, descricao) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (dados['nome'], dados['patrimonio'], dados['modelo'], dados['categoria'], dados['local'],
             dados['subitens'], dados['quantidade'], caminho_img, dados['descricao']))
        conn.commit()
    registrar_historico(session['usuario'], 'Cadastro', dados['nome'])

def buscar_itens(termo='', categoria='', local=''):
    with conectar() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM itens WHERE 1=1"
        params = []
        if termo:
            query += " AND (nome LIKE ? OR modelo LIKE ? OR patrimonio LIKE ?)"
            termo_like = f'%{termo}%'
            params.extend([termo_like] * 3)
        if categoria:
            query += " AND categoria=?"
            params.append(categoria)
        if local:
            query += " AND local LIKE ?"
            params.append(f'%{local}%')
        cursor.execute(query, params)
        return cursor.fetchall()

def obter_item(id):
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM itens WHERE id=?", (id,))
        return cursor.fetchone()

def editar_item(id, dados, imagem):
    with conectar() as conn:
        cursor = conn.cursor()
        if imagem:
            caminho_img = salvar_imagem(imagem)
            cursor.execute('''UPDATE itens SET nome=?, patrimonio=?, modelo=?, categoria=?, local=?,
                              subitens=?, quantidade=?, imagem=?, descricao=? WHERE id=?''',
                (dados['nome'], dados['patrimonio'], dados['modelo'], dados['categoria'], dados['local'],
                 dados['subitens'], dados['quantidade'], caminho_img, dados['descricao'], id))
        else:
            cursor.execute('''UPDATE itens SET nome=?, patrimonio=?, modelo=?, categoria=?, local=?,
                              subitens=?, quantidade=?, descricao=? WHERE id=?''',
                (dados['nome'], dados['patrimonio'], dados['modelo'], dados['categoria'], dados['local'],
                 dados['subitens'], dados['quantidade'], dados['descricao'], id))
        conn.commit()
    registrar_historico(session['usuario'], 'Edição', dados['nome'])

def excluir_item(id):
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT nome FROM itens WHERE id=?", (id,))
        nome = cursor.fetchone()[0]
        cursor.execute("DELETE FROM itens WHERE id=?", (id,))
        conn.commit()
    registrar_historico(session['usuario'], 'Exclusão', nome)

def salvar_imagem(imagem):
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    nome_arquivo = imagem.filename
    caminho_absoluto = os.path.join(app.config['UPLOAD_FOLDER'], nome_arquivo)
    imagem.save(caminho_absoluto)
    return f"{UPLOAD_FOLDER}/{nome_arquivo}"

# ---------- MOVIMENTAÇÃO ----------
def registrar_movimentacao(item_id, tipo, quantidade, motivo, usuario):
    data = datetime.now().strftime('%Y-%m-%d %H:%M')
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO movimentacoes (item_id, tipo, quantidade, motivo, data, usuario) VALUES (?, ?, ?, ?, ?, ?)",
                       (item_id, tipo, quantidade, motivo, data, usuario))
        if tipo == 'Entrada':
            cursor.execute("UPDATE itens SET quantidade = quantidade + ? WHERE id=?", (quantidade, item_id))
        elif tipo == 'Saída':
            cursor.execute("UPDATE itens SET quantidade = quantidade - ? WHERE id=?", (quantidade, item_id))
        conn.commit()

# ---------- HISTÓRICO ----------
def registrar_historico(usuario, acao, item):
    with conectar() as conn:
        cursor = conn.cursor()
        data = datetime.now().strftime('%Y-%m-%d %H:%M')
        cursor.execute("INSERT INTO historico (usuario, acao, item, data) VALUES (?, ?, ?, ?)",
                       (usuario, acao, item, data))
        conn.commit()

def obter_historico():
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM historico ORDER BY data DESC")
        return cursor.fetchall()

# ---------- EXPORTAÇÃO ----------
class PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 14)
        self.cell(0, 10, "Relatório de Itens do Almoxarifado", border=0, ln=1, align="C")
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Página {self.page_no()}", 0, 0, "C")

def exportar_pdf():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT nome, patrimonio, modelo, categoria, local, subitens, quantidade FROM itens")
    dados = cursor.fetchall()
    conn.close()

    colunas = ["Nome", "Patrimônio", "Modelo", "Categoria", "Local", "Subcomponentes", "Qtd"]
    larguras = [max(len(str(row[i])) for row in dados + [colunas]) * 2.5 for i in range(len(colunas))]

    pdf = PDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.set_fill_color(220, 220, 220)

    for i, col in enumerate(colunas):
        pdf.cell(larguras[i], 10, col, border=1, align="C", fill=True)
    pdf.ln()

    for row in dados:
        for i, dado in enumerate(row):
            pdf.cell(larguras[i], 10, str(dado), border=1)
        pdf.ln()

    caminho = "relatorio_itens.pdf"
    pdf.output(caminho)
    return caminho

# ---------- RESET TOTAL ----------
def limpar_banco():
    with conectar() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usuarios WHERE nome != 'SAVIO'")
        cursor.execute("DELETE FROM itens")
        cursor.execute("DELETE FROM historico")
        conn.commit()
    if os.path.exists(app.config['UPLOAD_FOLDER']):
        for f in os.listdir(app.config['UPLOAD_FOLDER']):
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], f))

# ---------- ROTAS ----------
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nome = request.form['nome']
        senha = request.form['senha']
        if nome == 'SAVIO' and senha == 'Ws396525$':
            session['moderador'] = True
            return redirect(url_for('painel_moderador'))
        elif validar_usuario(nome, senha):
            session['usuario'] = nome
            return redirect(url_for('dashboard'))
        return "Acesso inválido ou não autorizado."
    return render_template('login.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        adicionar_usuario(request.form['nome'], request.form['senha'])
        return "Cadastro aguardando aprovação."
    return render_template('cadastro.html')

@app.route('/dashboard')
def dashboard():
    total = contar_itens()
    baixos = itens_com_estoque_baixo()
    recentes = ultimos_historicos()
    return render_template('dashboard.html', total=total, baixos=baixos, recentes=recentes)

@app.route('/cadastrar_item', methods=['GET', 'POST'])
def cadastrar_item():
    if request.method == 'POST':
        dados = {k: request.form[k] for k in request.form}
        imagem = request.files.get('imagem')
        adicionar_item(dados, imagem)
        return redirect(url_for('dashboard'))
    return render_template('cadastrar_item.html')

@app.route('/buscar_item', methods=['GET', 'POST'])
def buscar_item():
    itens = []
    if request.method == 'POST':
        termo = request.form.get('termo', '')
        categoria = request.form.get('categoria', '')
        local = request.form.get('local', '')
        itens = buscar_itens(termo, categoria, local)
    return render_template('buscar_item.html', itens=itens)

@app.route('/visualizar/<int:id>')
def visualizar(id):
    item = obter_item(id)
    return render_template('visualizar_item.html', item=item)

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    item = obter_item(id)
    if request.method == 'POST':
        dados = {k: request.form[k] for k in request.form}
        imagem = request.files.get('imagem')
        editar_item(id, dados, imagem)
        return redirect(url_for('dashboard'))
    return render_template('editar_item.html', item=item)

@app.route('/excluir/<int:id>')
def excluir(id):
    excluir_item(id)
    return redirect(url_for('dashboard'))

@app.route('/historico')
def historico():
    hist = obter_historico()
    return render_template('historico.html', historico=hist)

@app.route('/exportar')
def exportar():
    caminho = exportar_pdf()
    return send_file(caminho, as_attachment=True)

@app.route('/painel_moderador')
def painel_moderador():
    pendentes = usuarios_pendentes()
    cadastrados = usuarios_aprovados()
    return render_template('moderador.html', pendentes=pendentes, cadastrados=cadastrados)

@app.route('/aprovar/<int:id>')
def aprovar(id):
    aprovar_usuario(id)
    return redirect(url_for('painel_moderador'))

@app.route('/rejeitar/<int:id>')
def rejeitar(id):
    rejeitar_usuario(id)
    return redirect(url_for('painel_moderador'))

@app.route('/excluir_usuario/<int:id>')
def excluir_usuario_route(id):
    excluir_usuario(id)
    return redirect(url_for('painel_moderador'))

@app.route('/entrada/<int:id>', methods=['GET', 'POST'])
def registrar_entrada(id):
    if request.method == 'POST':
        quantidade = int(request.form['quantidade'])
        motivo = request.form['motivo']
        registrar_movimentacao(id, 'Entrada', quantidade, motivo, session['usuario'])
        registrar_historico(session['usuario'], 'Entrada', f'Item ID {id}')
        return redirect(url_for('visualizar', id=id))
    return render_template('movimentacao.html', tipo='Entrada', item_id=id)

@app.route('/saida/<int:id>', methods=['GET', 'POST'])
def registrar_saida(id):
    if request.method == 'POST':
        quantidade = int(request.form['quantidade'])
        motivo = request.form['motivo']
        registrar_movimentacao(id, 'Saída', quantidade, motivo, session['usuario'])
        registrar_historico(session['usuario'], 'Saída', f'Item ID {id}')
        return redirect(url_for('visualizar', id=id))
    return render_template('movimentacao.html', tipo='Saída', item_id=id)

@app.route('/resetar_banco')
def resetar_banco():
    limpar_banco()
    return "Banco de dados limpo."

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    criar_tabelas()
    app.run(debug=True)
