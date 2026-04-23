import os
import sqlite3
import json
from datetime import datetime
from functools import wraps
from flask import Flask, request, render_template_string, redirect, url_for, flash, session
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

APP_NAME = "ChronoRetraite"
APP_SLOGAN = "Anticipez aujourd’hui, profitez demain"

# ---------- Base de données ----------
def init_db():
    conn = sqlite3.connect('professeurs.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        nom TEXT,
        prenom TEXT,
        metier TEXT,
        criteres TEXT,
        age_retraite INTEGER,
        annee_retraite INTEGER,
        date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute("PRAGMA table_info(predictions)")
    cols = [col[1] for col in c.fetchall()]
    if 'nom' not in cols:
        c.execute("ALTER TABLE predictions ADD COLUMN nom TEXT")
    if 'prenom' not in cols:
        c.execute("ALTER TABLE predictions ADD COLUMN prenom TEXT")
    conn.commit()
    conn.close()

# ---------- Fonctions de calcul (avec santé) ----------
def ajuster_par_sante(age_retraite, sante):
    if sante < 7:
        reduction = (7 - sante) * 0.6
        age_retraite -= reduction
    elif sante > 7:
        augmentation = (sante - 7) * 0.2
        age_retraite += augmentation
    return max(55, min(80, age_retraite))

def calcul_enseignant(data):
    age = data['age_actuel']
    anciennete = data.get('anciennete', 0)
    jours = data.get('jours', 4)
    salles = data.get('salles', 1)
    niveaux = data.get('niveaux', 1)
    sommeil = data.get('sommeil', 7)
    heures_supp = data.get('heures_supp', 0)
    sante = data.get('sante', 7)
    base = 65
    retraite = base - anciennete*0.8 - max(0, jours-4)*0.5 + (sommeil-7)*0.3 - (salles-1)*0.3 - (niveaux-1)*0.3 - (heures_supp//5)*0.5
    retraite = ajuster_par_sante(retraite, sante)
    return max(age+1, min(80, int(round(retraite))))

def calcul_medecin(data):
    age = data['age_actuel']
    gardes = data.get('gardes_nuit', 0)
    heures = data.get('heures_semaine', 40)
    specialite = data.get('specialite', 'generaliste')
    sante = data.get('sante', 7)
    base = 64
    retraite = base - gardes*0.5 - max(0, heures-40)*0.2 - (1 if specialite == 'specialiste' else 0)
    retraite = ajuster_par_sante(retraite, sante)
    return max(age+1, min(70, int(round(retraite))))

def calcul_ingenieur(data):
    age = data['age_actuel']
    secteur = data.get('secteur', 'prive')
    heures = data.get('heures_semaine', 39)
    deplacements = data.get('deplacements', 0)
    sante = data.get('sante', 7)
    base = 64
    retraite = base - max(0, heures-39)*0.3 - deplacements*0.8 + (1 if secteur == 'public' else 0)
    retraite = ajuster_par_sante(retraite, sante)
    return max(age+1, min(68, int(round(retraite))))

def calcul_architecte(data):
    age = data['age_actuel']
    heures = data.get('heures_semaine', 40)
    deplacements = data.get('deplacements', 0)
    stress = data.get('stress', 0)
    sante = data.get('sante', 7)
    base = 63
    retraite = base - max(0, heures-40)*0.2 - deplacements*0.5 - stress*0.7
    retraite = ajuster_par_sante(retraite, sante)
    return max(age+1, min(67, int(round(retraite))))

def calcul_commercant(data):
    age = data['age_actuel']
    type_commerce = data.get('type_commerce', 'boutique')
    sante = data.get('sante', 7)
    if type_commerce == 'boutique':
        heures = data.get('heures_ouvertures', 9)
        stress = data.get('stress', 0)
        retraite = 63 - (heures-9)*0.3 - stress*0.8
    elif type_commerce == 'sauvette':
        heures = data.get('heures_debout', 8)
        soleil = data.get('exposition_soleil', 0)
        retraite = 60 - (heures-8)*0.5 - soleil*0.6
    elif type_commerce == 'taxi':
        heures = data.get('heures_conduite', 8)
        km = data.get('kilometres', 0)
        retraite = 60 - (heures-8)*0.7 - (km//50)*0.5
    elif type_commerce == 'moto':
        heures = data.get('heures_conduite', 6)
        conditions = data.get('conditions', 0)
        retraite = 58 - (heures-6)*0.8 - conditions*1.2
    elif type_commerce == 'restauration':
        heures = data.get('heures_travail', 8)
        manutention = data.get('manutention', 0)
        retraite = 60 - (heures-8)*0.4 - manutention*1.5
    else:
        retraite = 62
    retraite = ajuster_par_sante(retraite, sante)
    return max(age+1, min(75, int(round(retraite))))

def calcul_fonctionnaire(data):
    age = data['age_actuel']
    categorie = data.get('categorie', 'B')
    anciennete = data.get('anciennete', 0)
    sante = data.get('sante', 7)
    base = 62
    ajust = {'A': -1, 'B': 0, 'C': 1}.get(categorie, 0)
    retraite = base + ajust - anciennete*0.3
    retraite = ajuster_par_sante(retraite, sante)
    return max(age+1, min(65, int(round(retraite))))

def calcul_menuiser(data):
    age = data['age_actuel']
    heures = data.get('heures_travail', 8)
    poussiere = data.get('exposition_poussiere', 0)
    charges = data.get('port_charges', 0)
    sante = data.get('sante', 7)
    retraite = 60 - max(0, heures-8)*0.4 - poussiere*0.5 - charges*1
    retraite = ajuster_par_sante(retraite, sante)
    return max(age+1, min(65, int(round(retraite))))

def calcul_macon(data):
    age = data['age_actuel']
    heures = data.get('heures_travail', 8)
    soleil = data.get('exposition_soleil', 0)
    effort = data.get('effort_physique', 0)
    sante = data.get('sante', 7)
    retraite = 58 - max(0, heures-8)*0.5 - soleil*0.7 - effort*0.9
    retraite = ajuster_par_sante(retraite, sante)
    return max(age+1, min(63, int(round(retraite))))

CALCULS = {
    'enseignant': calcul_enseignant,
    'medecin': calcul_medecin,
    'ingenieur': calcul_ingenieur,
    'architecte': calcul_architecte,
    'commercant': calcul_commercant,
    'fonctionnaire': calcul_fonctionnaire,
    'menuisier': calcul_menuiser,
    'macon': calcul_macon
}

# ---------- Champs spécifiques ----------
METIERS_FIELDS = {
    'enseignant': [
        {'name': 'anciennete', 'label': 'Ancienneté (années)', 'type': 'number', 'min': 0, 'max': 60, 'default': 0},
        {'name': 'jours', 'label': 'Jours d\'enseignement par semaine', 'type': 'number', 'min': 1, 'max': 7, 'default': 4},
        {'name': 'salles', 'label': 'Nombre de salles utilisées', 'type': 'number', 'min': 1, 'max': 10, 'default': 1},
        {'name': 'niveaux', 'label': 'Niveaux enseignés (1 à 6)', 'type': 'number', 'min': 1, 'max': 6, 'default': 1},
        {'name': 'sommeil', 'label': 'Heures de sommeil par jour', 'type': 'number', 'step': 0.5, 'min': 0, 'max': 12, 'default': 7},
        {'name': 'heures_supp', 'label': 'Heures supplémentaires / semaine', 'type': 'number', 'min': 0, 'max': 30, 'default': 0}
    ],
    'medecin': [
        {'name': 'gardes_nuit', 'label': 'Gardes de nuit / mois', 'type': 'number', 'min': 0, 'max': 15, 'default': 0},
        {'name': 'heures_semaine', 'label': 'Heures de travail / semaine', 'type': 'number', 'step': 0.5, 'min': 20, 'max': 80, 'default': 40},
        {'name': 'specialite', 'label': 'Spécialité', 'type': 'select', 'options': [('generaliste', 'Généraliste'), ('specialiste', 'Spécialiste')], 'default': 'generaliste'}
    ],
    'ingenieur': [
        {'name': 'secteur', 'label': 'Secteur', 'type': 'select', 'options': [('prive', 'Privé'), ('public', 'Public')], 'default': 'prive'},
        {'name': 'heures_semaine', 'label': 'Heures / semaine', 'type': 'number', 'step': 0.5, 'min': 30, 'max': 60, 'default': 39},
        {'name': 'deplacements', 'label': 'Déplacements (0-2)', 'type': 'number', 'min': 0, 'max': 2, 'default': 0}
    ],
    'architecte': [
        {'name': 'heures_semaine', 'label': 'Heures / semaine', 'type': 'number', 'step': 0.5, 'min': 30, 'max': 70, 'default': 40},
        {'name': 'deplacements', 'label': 'Déplacements (0-2)', 'type': 'number', 'min': 0, 'max': 2, 'default': 0},
        {'name': 'stress', 'label': 'Stress (0-3)', 'type': 'number', 'min': 0, 'max': 3, 'default': 0}
    ],
    'commercant': [
        {'name': 'type_commerce', 'label': 'Type', 'type': 'select', 'options': [('boutique', 'Gérant'), ('sauvette', 'Vendeur à la sauvette'), ('taxi', 'Taximan'), ('moto', 'Motoman'), ('restauration', 'Restauration')], 'default': 'boutique'},
        {'name': 'heures_ouvertures', 'label': 'Heures ouverture/jour', 'type': 'number', 'step': 0.5, 'min': 4, 'max': 16, 'default': 9},
        {'name': 'stress', 'label': 'Stress (0-3)', 'type': 'number', 'min': 0, 'max': 3, 'default': 0},
        {'name': 'heures_debout', 'label': 'Heures debout/jour', 'type': 'number', 'step': 0.5, 'min': 2, 'max': 14, 'default': 8},
        {'name': 'exposition_soleil', 'label': 'Soleil (0-5)', 'type': 'number', 'min': 0, 'max': 5, 'default': 0},
        {'name': 'heures_conduite', 'label': 'Conduite (h/jour)', 'type': 'number', 'step': 0.5, 'min': 2, 'max': 14, 'default': 8},
        {'name': 'kilometres', 'label': 'Km/jour', 'type': 'number', 'min': 0, 'max': 500, 'default': 0},
        {'name': 'conditions', 'label': 'Conditions difficiles (0-3)', 'type': 'number', 'min': 0, 'max': 3, 'default': 0},
        {'name': 'heures_travail', 'label': 'Heures travail/jour', 'type': 'number', 'step': 0.5, 'min': 4, 'max': 14, 'default': 8},
        {'name': 'manutention', 'label': 'Manutention (0-2)', 'type': 'number', 'min': 0, 'max': 2, 'default': 0}
    ],
    'fonctionnaire': [
        {'name': 'categorie', 'label': 'Catégorie', 'type': 'select', 'options': [('A', 'A'), ('B', 'B'), ('C', 'C')], 'default': 'B'},
        {'name': 'anciennete', 'label': 'Ancienneté (années)', 'type': 'number', 'min': 0, 'max': 40, 'default': 0}
    ],
    'menuisier': [
        {'name': 'heures_travail', 'label': 'Heures/jour', 'type': 'number', 'step': 0.5, 'min': 4, 'max': 12, 'default': 8},
        {'name': 'exposition_poussiere', 'label': 'Poussière (0-3)', 'type': 'number', 'min': 0, 'max': 3, 'default': 0},
        {'name': 'port_charges', 'label': 'Charges lourdes (0-2)', 'type': 'number', 'min': 0, 'max': 2, 'default': 0}
    ],
    'macon': [
        {'name': 'heures_travail', 'label': 'Heures/jour', 'type': 'number', 'step': 0.5, 'min': 4, 'max': 12, 'default': 8},
        {'name': 'exposition_soleil', 'label': 'Soleil (0-5)', 'type': 'number', 'min': 0, 'max': 5, 'default': 0},
        {'name': 'effort_physique', 'label': 'Effort (0-3)', 'type': 'number', 'min': 0, 'max': 3, 'default': 0}
    ]
}

METIER_NAMES = {
    'enseignant': 'Enseignant',
    'medecin': 'Médecin',
    'ingenieur': 'Ingénieur',
    'architecte': 'Architecte',
    'commercant': 'Commerçant / Artisan',
    'fonctionnaire': 'Fonctionnaire',
    'menuisier': 'Menuisier',
    'macon': 'Maçon'
}

# ---------- Authentification ----------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            session['username'] = username if username else "Cher collègue"
            flash(f"Connexion réussie. Bienvenue, {session['username']} !", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Mot de passe incorrect", "danger")
    return render_template_string('''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ app_name }} - Connexion</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: 'Inter', sans-serif; background: linear-gradient(135deg, #0D1B2A 0%, #1D4ED8 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 1rem; }
        .card { background: white; border-radius: 2rem; padding: 2rem; width: 100%; max-width: 400px; box-shadow: 0 20px 35px -10px rgba(0,0,0,0.2); }
        .logo { text-align: center; font-size: 3rem; margin-bottom: 1rem; }
        h2 { color: #0D1B2A; text-align: center; margin-bottom: 1.5rem; }
        input { width: 100%; padding: 0.75rem; margin-bottom: 1rem; border: 1px solid #cbd5e1; border-radius: 1rem; font-size: 1rem; }
        button { width: 100%; background: #1D4ED8; color: white; border: none; padding: 0.75rem; border-radius: 1rem; font-weight: 600; cursor: pointer; transition: 0.2s; }
        button:hover { background: #0D1B2A; }
        .footer { text-align: center; margin-top: 1rem; font-size: 0.8rem; color: #64748b; }
    </style>
</head>
<body>
    <div class="card">
        <img src="{{ url_for('static', filename='logo.svg') }}" alt="ChronoRetraite" style="display: block; margin: 0 auto 20px; max-width: 80%; height: auto;">
        <h2>{{ app_name }}</h2>
        <form method="post">
            <input type="text" name="username" placeholder="Votre nom / prénom" required>
            <input type="password" name="password" placeholder="Mot de passe" required>
            <button type="submit">Se connecter</button>
        </form>
        <div class="footer">Mot de passe par défaut : admin123</div>
    </div>
</body>
</html>
    ''', app_name=APP_NAME)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    flash("Déconnecté", "success")
    return redirect(url_for('login'))

# ---------- Tableau de bord ----------
@app.route('/')
@login_required
def dashboard():
    username = session.get('username', 'utilisateur')
    return render_template_string('''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ app_name }} - Tableau de bord</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
            min-height: 100vh;
        }
        .navbar {
            background: rgba(13, 27, 42, 0.95);
            backdrop-filter: blur(10px);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }
        .logo img {
            height: 150px;
            width: auto;
        }
        .nav-links a {
            color: white;
            text-decoration: none;
            margin-left: 1.8rem;
            font-weight: 500;
            transition: 0.2s;
            font-size: 1rem;
        }
        .nav-links a:hover { color: #10B981; transform: translateY(-2px); display: inline-block; }
        .container { max-width: 1300px; margin: 2.5rem auto; padding: 0 1.5rem; }
        .welcome-card {
            background: linear-gradient(145deg, #0D1B2A, #1D4ED8);
            border-radius: 2rem;
            padding: 2.5rem;
            text-align: center;
            margin-bottom: 3rem;
            box-shadow: 0 20px 35px -10px rgba(0,0,0,0.2);
            position: relative;
            overflow: hidden;
        }
        .welcome-card::before {
            content: '';
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
            animation: pulse 8s infinite;
        }
        @keyframes pulse {
            0% { transform: translate(0,0) scale(1); opacity: 0.3; }
            50% { transform: translate(5%,5%) scale(1.1); opacity: 0.1; }
            100% { transform: translate(0,0) scale(1); opacity: 0.3; }
        }
        .welcome-card h1 {
            font-size: 2.4rem;
            margin-bottom: 0.5rem;
            font-weight: 800;
            position: relative;
            z-index: 1;
        }
        .welcome-card p {
            font-size: 1.2rem;
            opacity: 0.9;
            position: relative;
            z-index: 1;
        }
        .cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 2rem;
        }
        .card {
            background: white;
            border-radius: 1.8rem;
            padding: 2rem 1.5rem;
            text-align: center;
            transition: all 0.3s cubic-bezier(0.2, 0.9, 0.4, 1.1);
            box-shadow: 0 10px 20px rgba(0,0,0,0.05);
            text-decoration: none;
            color: inherit;
            display: block;
            backdrop-filter: blur(2px);
            border: 1px solid rgba(255,255,255,0.3);
        }
        .card:hover {
            transform: translateY(-12px);
            box-shadow: 0 25px 40px rgba(0,0,0,0.15);
            border-color: #1D4ED8;
        }
        .card i {
            font-size: 3.5rem;
            color: #1D4ED8;
            margin-bottom: 1.2rem;
            transition: 0.2s;
        }
        .card:hover i {
            transform: scale(1.1);
            color: #10B981;
        }
        .card h3 {
            font-size: 1.6rem;
            margin-bottom: 0.5rem;
            font-weight: 700;
        }
        .card p {
            font-size: 0.95rem;
            color: #4b5563;
            line-height: 1.4;
        }
        footer {
            text-align: center;
            margin-top: 3rem;
            padding: 1.5rem;
            color: #4b5563;
            font-size: 0.85rem;
        }
        @media (max-width: 640px) {
            .navbar { flex-direction: column; gap: 1rem; }
            .nav-links a { margin: 0 0.8rem; }
            .welcome-card h1 { font-size: 1.8rem; }
            .logo img { height: 150px; }
        }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="logo">
            <img src="{{ url_for('static', filename='logo.png') }}" alt="ChronoRetraite">
        </div>
        <div class="nav-links">
            <a href="/logout"><i class="fas fa-sign-out-alt"></i> Déconnexion</a>
        </div>
    </nav>
    <div class="container">
        <div class="welcome-card">
            <h1>Bienvenue sur ChronoRetraite, {{ username }} !</h1>
            <p>Anticipez aujourd’hui, profitez demain.</p>
        </div>
        <div class="cards">
            <a href="/prediction" class="card">
                <i class="fas fa-calculator"></i>
                <h3>Prédiction</h3>
                <p>Calculez votre âge de départ à la retraite avec des critères avancés</p>
            </a>
            <a href="/graphique" class="card">
                <i class="fas fa-chart-bar"></i>
                <h3>Graphique</h3>
                <p>Visualisez la distribution des âges par métier</p>
            </a>
            <a href="/collecte" class="card">
                <i class="fas fa-database"></i>
                <h3>Collecte (Admin)</h3>
                <p>Consultez, modifiez ou supprimez les prédictions</p>
            </a>
            <a href="/stats" class="card">
                <i class="fas fa-chart-line"></i>
                <h3>Statistiques</h3>
                <p>Analysez les indicateurs globaux</p>
            </a>
        </div>
        <footer>© {{ app_name }} - Sécurisé et fiable | Données confidentielles</footer>
    </div>
</body>
</html>
    ''', app_name=APP_NAME, username=username)

# ---------- Page de prédiction ----------
@app.route('/prediction', methods=['GET', 'POST'])
@login_required
def prediction():
    result = None
    metier = request.form.get('metier', 'enseignant')
    
    if request.method == 'POST' and 'change_metier' in request.form:
        metier = request.form['metier']
        return redirect(url_for('prediction', metier=metier))
    
    if request.args.get('metier'):
        metier = request.args.get('metier')
    
    if request.method == 'POST' and 'calculer' in request.form:
        metier = request.form['metier']
        nom = request.form.get('nom', '').strip()
        prenom = request.form.get('prenom', '').strip()
        date_naissance = request.form.get('date_naissance', '')
        age_actuel_str = request.form.get('age_actuel', '').strip()
        debut_activite_str = request.form.get('debut_activite', '').strip()
        statut = request.form.get('statut', '')
        salaire_str = request.form.get('salaire', '').strip()
        sante_str = request.form.get('sante', '7').strip()
        
        if not nom or not prenom:
            flash("Le nom et le prénom sont obligatoires.", "danger")
            return redirect(url_for('prediction', metier=metier))
        if not age_actuel_str:
            flash("L'âge actuel est obligatoire.", "danger")
            return redirect(url_for('prediction', metier=metier))
        try:
            age_actuel = int(age_actuel_str)
        except ValueError:
            flash("Âge actuel invalide.", "danger")
            return redirect(url_for('prediction', metier=metier))
        try:
            sante = int(sante_str)
            if sante < 1: sante = 1
            if sante > 10: sante = 10
        except:
            sante = 7
        
        data = {'age_actuel': age_actuel, 'sante': sante}
        for field in METIERS_FIELDS.get(metier, []):
            name = field['name']
            if name in request.form and request.form[name] != '':
                val = request.form[name]
                if field['type'] == 'number':
                    val = float(val) if '.' in val else int(val)
                data[name] = val
            else:
                data[name] = field.get('default', 0)
        
        if metier in CALCULS:
            age_retraite = CALCULS[metier](data)
        else:
            age_retraite = 65
        
        annee_actuelle = datetime.now().year
        annee_retraite = annee_actuelle + (age_retraite - age_actuel)
        
        conn = sqlite3.connect('professeurs.db')
        c = conn.cursor()
        c.execute('''INSERT INTO predictions (username, nom, prenom, metier, criteres, age_retraite, annee_retraite)
                     VALUES (?,?,?,?,?,?,?)''',
                  (session['username'], nom, prenom, metier, json.dumps(data), age_retraite, annee_retraite))
        conn.commit()
        conn.close()
        
        result = {
            'age': age_retraite,
            'annee': annee_retraite,
            'age_actuel': age_actuel,
            'annees_restantes': age_retraite - age_actuel,
            'metier': METIER_NAMES.get(metier, metier),
            'nom': nom,
            'prenom': prenom,
            'debut_activite': debut_activite_str,
            'statut': statut,
            'salaire': salaire_str,
            'date_naissance': date_naissance,
            'sante': sante
        }
        flash("Prédiction effectuée avec succès !", "success")
    
    specific_fields_html = ''
    for field in METIERS_FIELDS.get(metier, []):
        if field['type'] == 'select':
            options = ''.join(f'<option value="{val}" {"selected" if val == field.get("default", "") else ""}>{label}</option>' for val, label in field['options'])
            specific_fields_html += f'<div class="form-group"><label>{field["label"]}</label><select name="{field["name"]}">{options}</select></div>'
        else:
            attrs = f'type="{field["type"]}" step="{field.get("step", 1)}" min="{field.get("min", 0)}" max="{field.get("max", 100)}"'
            default = field.get('default', '')
            specific_fields_html += f'<div class="form-group"><label>{field["label"]}</label><input {attrs} name="{field["name"]}" value="{default}"></div>'
    
    return render_template_string('''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ app_name }} - Prédiction</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        :root { --primary: #0D1B2A; --secondary: #1D4ED8; --accent: #10B981; --light: #F1F5F9; }
        * { margin:0; padding:0; box-sizing:border-box; }
        body {
            font-family: 'Inter', sans-serif;
            background: linear-gradient(145deg, #F1F5F9 0%, #e6edf4 100%);
            min-height: 100vh;
        }
        .navbar {
            background: rgba(13,27,42,0.95);
            backdrop-filter: blur(10px);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        }
        .logo img {
            height: 100px;
            width: auto;
        }
        .nav-links a {
            color: white;
            text-decoration: none;
            margin-left: 1.8rem;
            font-weight: 500;
            transition: 0.2s;
        }
        .nav-links a:hover { color: var(--accent); }
        .container { max-width: 1400px; margin: 2rem auto; padding: 0 1.5rem; }
        .hero {
            text-align: center;
            margin-bottom: 2.5rem;
        }
        .hero h1 {
            font-size: 2.4rem;
            font-weight: 800;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            margin-bottom: 0.5rem;
        }
        .hero p { font-size: 1.1rem; color: #4b5563; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }
        .card {
            background: white;
            border-radius: 1.8rem;
            padding: 2rem;
            box-shadow: 0 15px 30px rgba(0,0,0,0.05);
            transition: all 0.2s;
            border: 1px solid rgba(0,0,0,0.03);
        }
        .card:hover { box-shadow: 0 20px 35px rgba(0,0,0,0.1); }
        .card h2 {
            font-size: 1.6rem;
            margin-bottom: 1.2rem;
            display: flex;
            align-items: center;
            gap: 0.6rem;
            border-left: 5px solid var(--secondary);
            padding-left: 1rem;
            font-weight: 700;
        }
        .form-group { margin-bottom: 1.2rem; }
        label {
            display: block;
            font-weight: 600;
            margin-bottom: 0.4rem;
            font-size: 0.9rem;
            color: var(--primary);
        }
        input, select {
            width: 100%;
            padding: 0.8rem;
            border: 1px solid #cbd5e1;
            border-radius: 1rem;
            font-size: 0.95rem;
            transition: 0.2s;
            background: #fff;
        }
        input:focus, select:focus {
            outline: none;
            border-color: var(--secondary);
            box-shadow: 0 0 0 3px rgba(29,78,216,0.15);
        }
        button {
            background: var(--secondary);
            color: white;
            border: none;
            padding: 0.8rem;
            border-radius: 1rem;
            font-weight: 700;
            cursor: pointer;
            width: 100%;
            transition: 0.2s;
            font-size: 1rem;
        }
        button:hover { background: var(--primary); transform: translateY(-2px); }
        .btn-secondary { background: #64748b; margin-top: 0.5rem; }
        .result-card {
            background: linear-gradient(145deg, var(--primary), var(--secondary));
            color: white;
        }
        .result-card h2 { color: white; border-left-color: var(--accent); }
        .result-value { font-size: 2.5rem; font-weight: 800; margin: 0.5rem 0; }
        .result-detail {
            background: rgba(255,255,255,0.12);
            border-radius: 1.2rem;
            padding: 1.2rem;
            margin-top: 1rem;
            backdrop-filter: blur(2px);
        }
        .badge {
            display: inline-block;
            background: var(--accent);
            color: white;
            padding: 0.25rem 0.8rem;
            border-radius: 2rem;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .advice-box {
            margin-top: 1.8rem;
            background: #f8fafc;
            border-radius: 1.5rem;
            padding: 1.2rem;
            border-left: 5px solid var(--accent);
        }
        .advice-list {
            display: flex;
            flex-wrap: wrap;
            gap: 0.7rem;
            list-style: none;
            margin-top: 0.8rem;
        }
        .advice-list li {
            background: white;
            padding: 0.4rem 1rem;
            border-radius: 2rem;
            font-size: 0.85rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            font-weight: 500;
        }
        footer {
            text-align: center;
            margin-top: 2rem;
            padding: 1rem;
            color: #64748b;
            font-size: 0.8rem;
        }
        @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="logo">
            <img src="{{ url_for('static', filename='logo.png') }}" alt="ChronoRetraite">
        </div>
        <div class="nav-links">
            <a href="/"><i class="fas fa-home"></i> Accueil</a>
            <a href="/graphique"><i class="fas fa-chart-bar"></i> Graphique</a>
            <a href="/collecte"><i class="fas fa-database"></i> Collecte</a>
            <a href="/stats"><i class="fas fa-chart-line"></i> Stats</a>
            <a href="/logout"><i class="fas fa-sign-out-alt"></i> Déconnexion</a>
        </div>
    </nav>
    <div class="container">
        <div class="hero">
            <h1>PRÉDISEZ VOTRE ÂGE DE DÉPART À LA RETRAITE</h1>
            <p>{{ slogan }}</p>
        </div>
        <div class="grid">
            <div class="card">
                <h2><i class="fas fa-sliders-h"></i> Paramètres</h2>
                <form method="post">
                    <div class="form-group">
                        <label>Métier</label>
                        <select name="metier" id="metier">
                            {% for key, name in metier_names.items() %}
                            <option value="{{ key }}" {% if key == metier %}selected{% endif %}>{{ name }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <button type="submit" name="change_metier" value="1" class="btn-secondary">Charger les champs spécifiques</button>
                    <div style="margin-top: 1.5rem;">
                        <div class="form-group"><label>Nom</label><input type="text" name="nom" value="{{ request.form.nom or '' }}" required></div>
                        <div class="form-group"><label>Prénom</label><input type="text" name="prenom" value="{{ request.form.prenom or '' }}" required></div>
                        <div class="form-group"><label>Date de naissance</label><input type="date" name="date_naissance" value="{{ request.form.date_naissance or '' }}"></div>
                        <div class="form-group"><label>Âge actuel</label><input type="number" name="age_actuel" value="{{ request.form.age_actuel or '' }}" required></div>
                        <div class="form-group"><label>Âge de début d'activité</label><input type="number" name="debut_activite" value="{{ request.form.debut_activite or '' }}"></div>
                        <div class="form-group"><label>Statut professionnel</label><select name="statut"><option>Salarié</option><option>Fonctionnaire</option><option>Indépendant</option></select></div>
                        <div class="form-group"><label>Salaire mensuel actuel (FCFA)</label><input type="number" name="salaire" value="{{ request.form.salaire or '' }}"></div>
                        <div class="form-group">
                            <label>État de santé (1 = très mauvaise, 10 = excellente)</label>
                            <input type="number" name="sante" min="1" max="10" step="1" value="{{ request.form.sante or '7' }}">
                        </div>
                        <hr style="margin: 1rem 0; border-color: #e2e8f0;">
                        <h3 style="font-size: 1.1rem; margin-bottom: 0.8rem; font-weight: 700;">📌 Critères spécifiques au métier</h3>
                        {{ specific_fields|safe }}
                        <button type="submit" name="calculer" value="1">Calculer ma retraite</button>
                    </div>
                </form>
            </div>
            <div>
                <div class="card result-card">
                    <h2><i class="fas fa-chart-simple"></i> Récapitulatif</h2>
                    {% if result %}
                        <div class="result-value">{{ result.age }} ans</div>
                        <div>Année estimée : <strong>{{ result.annee }}</strong></div>
                        <div class="result-detail">
                            <p><strong>Résumé de votre projection</strong></p>
                            <p>{{ result.nom }} {{ result.prenom }}</p>
                            <p>Âge actuel : {{ result.age_actuel }} ans</p>
                            <p>Années restantes : {{ result.annees_restantes }} ans</p>
                            <p>Année de départ estimée : {{ result.annee }}</p>
                            <p>Niveau : <span class="badge">{{ "Bon" if result.age <= 62 else "À améliorer" }}</span></p>
                            <p><small>Métier : {{ result.metier }}</small></p>
                            {% if result.debut_activite %}<p>Âge début activité : {{ result.debut_activite }} ans</p>{% endif %}
                            {% if result.statut %}<p>Statut : {{ result.statut }}</p>{% endif %}
                            {% if result.salaire %}<p>Salaire : {{ result.salaire }} FCFA</p>{% endif %}
                            {% if result.sante %}<p>Santé : {{ result.sante }}/10</p>{% endif %}
                        </div>
                        <div style="background: rgba(255,255,255,0.1); border-radius:1rem; padding:1rem; margin-top:1rem;">
                            <p><strong>Âge de départ : {{ result.age }} ans</strong> ({{ result.annee }})</p>
                        </div>
                    {% else %}
                        <div style="text-align:center; margin-top:2rem;">
                            <i class="fas fa-chart-line fa-4x" style="opacity:0.4;"></i>
                            <p style="margin-top:1rem;">Remplissez le formulaire pour obtenir votre prédiction.</p>
                        </div>
                    {% endif %}
                </div>
                <div class="advice-box">
                    <h3><i class="fas fa-lightbulb"></i> Conseils</h3>
                    <ul class="advice-list">
                        <li>Préparez votre avenir dès aujourd'hui</li>
                        <li>Épargnez régulièrement</li>
                        <li>Investissez intelligemment</li>
                        <li>Restez en bonne santé</li>
                        <li>Informez-vous</li>
                    </ul>
                </div>
                <div class="card" style="margin-top: 1.2rem;">
                    <h2><i class="fas fa-info-circle"></i> À propos</h2>
                    <p>ChronoRetraite utilise des algorithmes avancés pour prédire votre âge de départ à la retraite.</p>
                    <div style="display: flex; gap: 1rem; margin-top: 1rem;">
                        <span><i class="fas fa-lock"></i> Sécurisé</span>
                        <span><i class="fas fa-chart-line"></i> Fiable</span>
                        <span><i class="fas fa-user-secret"></i> Confidentialité</span>
                    </div>
                </div>
            </div>
        </div>
        <footer>© {{ app_name }} - {{ slogan }}</footer>
    </div>
</body>
</html>
    ''', app_name=APP_NAME, slogan=APP_SLOGAN, metier=metier,
          metier_names=METIER_NAMES, specific_fields=specific_fields_html, result=result)

# ---------- Collecte Admin ----------
@app.route('/collecte')
@login_required
def collecte():
    conn = sqlite3.connect('professeurs.db')
    c = conn.cursor()
    c.execute('SELECT id, username, nom, prenom, metier, criteres, age_retraite, date_creation FROM predictions ORDER BY date_creation DESC')
    rows = c.fetchall()
    conn.close()
    data = []
    for row in rows:
        try:
            criteres_dict = json.loads(row[5])
            criteres_str = ', '.join(f"{k}: {v}" for k, v in criteres_dict.items())
        except:
            criteres_str = row[5]
        data.append((row[0], row[1], row[2], row[3], METIER_NAMES.get(row[4], row[4]), criteres_str, row[6], row[7]))
    return render_template_string('''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>{{ app_name }} - Collecte Admin</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        :root { --primary: #0D1B2A; --secondary: #1D4ED8; --light: #F1F5F9; }
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: 'Inter', sans-serif; background: var(--light); }
        .navbar { background: var(--primary); padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
        .logo img { height: 60px; width: auto; }
        .nav-links a { color: white; text-decoration: none; margin-left: 1.5rem; }
        .container { max-width: 1400px; margin: 2rem auto; padding: 0 1rem; }
        .card { background: white; border-radius: 1.5rem; padding: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid #e2e8f0; }
        th { background: var(--light); }
        .badge { background: var(--secondary); color: white; padding: 0.2rem 0.6rem; border-radius: 1rem; font-size: 0.8rem; }
        .btn-edit { background: #f59e0b; color: white; padding: 0.2rem 0.6rem; border-radius: 0.5rem; text-decoration: none; font-size: 0.8rem; }
        .btn-delete { background: #ef4444; color: white; padding: 0.2rem 0.6rem; border-radius: 0.5rem; text-decoration: none; font-size: 0.8rem; }
        .btn-edit:hover { background: #d97706; }
        .btn-delete:hover { background: #dc2626; }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="logo">
            <img src="{{ url_for('static', filename='logo.png') }}" alt="ChronoRetraite">
        </div>
        <div class="nav-links">
            <a href="/">Accueil</a>
            <a href="/prediction">Prédiction</a>
            <a href="/graphique">Graphique</a>
            <a href="/stats">Stats</a>
            <a href="/logout">Déconnexion</a>
        </div>
    </nav>
    <div class="container">
        <div class="card">
            <h2><i class="fas fa-database"></i> Liste des prédictions enregistrées</h2>
            <div style="overflow-x: auto;">
                <table>
                    <thead>
                        <tr><th>ID</th><th>Utilisateur</th><th>Nom</th><th>Prénom</th><th>Métier</th><th>Critères</th><th>Âge retraite</th><th>Date</th><th>Actions</th></tr>
                    </thead>
                    <tbody>
                        {% for row in data %}
                        <tr>
                            <td>{{ row[0] }}</td>
                            <td>{{ row[1] }}</td>
                            <td>{{ row[2] }}</td>
                            <td>{{ row[3] }}</td>
                            <td><span class="badge">{{ row[4] }}</span></td>
                            <td>{{ row[5] }}</td>
                            <td><strong>{{ row[6] }} ans</strong></td>
                            <td>{{ row[7] }}</td>
                            <td>
                                <a href="/modifier/{{ row[0] }}" class="btn-edit"><i class="fas fa-edit"></i> Modifier</a>
                                <a href="/supprimer/{{ row[0] }}" class="btn-delete" onclick="return confirm('Supprimer définitivement cette prédiction ?')"><i class="fas fa-trash-alt"></i> Supprimer</a>
                            </td>
                        </tr>
                        {% else %}
                        <tr><td colspan="9">Aucune prédiction enregistrée. Utilisez le formulaire de prédiction.{% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>
    ''', app_name=APP_NAME, data=data)

# ---------- Modifier ----------
@app.route('/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier(id):
    conn = sqlite3.connect('professeurs.db')
    c = conn.cursor()
    if request.method == 'POST':
        nom = request.form.get('nom', '').strip()
        prenom = request.form.get('prenom', '').strip()
        metier = request.form.get('metier', '')
        age_actuel = int(request.form.get('age_actuel', 0))
        sante = int(request.form.get('sante', 7))
        data = {'age_actuel': age_actuel, 'sante': sante}
        for field in METIERS_FIELDS.get(metier, []):
            name = field['name']
            if name in request.form and request.form[name] != '':
                val = request.form[name]
                if field['type'] == 'number':
                    val = float(val) if '.' in val else int(val)
                data[name] = val
            else:
                data[name] = field.get('default', 0)
        if metier in CALCULS:
            age_retraite = CALCULS[metier](data)
        else:
            age_retraite = 65
        annee_actuelle = datetime.now().year
        annee_retraite = annee_actuelle + (age_retraite - age_actuel)
        c.execute('''UPDATE predictions 
                     SET nom=?, prenom=?, metier=?, criteres=?, age_retraite=?, annee_retraite=?
                     WHERE id=?''',
                  (nom, prenom, metier, json.dumps(data), age_retraite, annee_retraite, id))
        conn.commit()
        conn.close()
        flash("Prédiction modifiée avec succès.", "success")
        return redirect(url_for('collecte'))
    
    c.execute('SELECT id, nom, prenom, metier, criteres, age_retraite FROM predictions WHERE id=?', (id,))
    row = c.fetchone()
    conn.close()
    if not row:
        flash("Prédiction non trouvée.", "danger")
        return redirect(url_for('collecte'))
    criteres = json.loads(row[4])
    age_actuel = criteres.get('age_actuel', 0)
    sante = criteres.get('sante', 7)
    specific_fields_html = ''
    for field in METIERS_FIELDS.get(row[2], []):
        name = field['name']
        value = criteres.get(name, field.get('default', ''))
        if field['type'] == 'select':
            options = ''.join(f'<option value="{val}" {"selected" if val == value else ""}>{label}</option>' for val, label in field['options'])
            specific_fields_html += f'<div class="form-group"><label>{field["label"]}</label><select name="{field["name"]}">{options}</select></div>'
        else:
            attrs = f'type="{field["type"]}" step="{field.get("step", 1)}" min="{field.get("min", 0)}" max="{field.get("max", 100)}"'
            specific_fields_html += f'<div class="form-group"><label>{field["label"]}</label><input {attrs} name="{field["name"]}" value="{value}"></div>'
    
    return render_template_string('''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>Modifier une prédiction</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <style>
        :root { --primary: #0D1B2A; --secondary: #1D4ED8; --accent: #10B981; --light: #F1F5F9; }
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: 'Inter', sans-serif; background: var(--light); padding: 2rem; }
        .container { max-width: 800px; margin: auto; background: white; border-radius: 1.5rem; padding: 2rem; }
        .form-group { margin-bottom: 1rem; }
        label { display: block; font-weight: 600; margin-bottom: 0.3rem; }
        input, select { width: 100%; padding: 0.6rem; border: 1px solid #cbd5e1; border-radius: 0.8rem; }
        button { background: var(--secondary); color: white; border: none; padding: 0.7rem; border-radius: 0.8rem; font-weight: 600; cursor: pointer; width: 100%; }
        .btn-secondary { background: #64748b; margin-top: 0.5rem; }
        .logo-bar { display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }
        .logo-bar img { height: 50px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo-bar">
            <img src="{{ url_for('static', filename='logo.png') }}" alt="ChronoRetraite">
            <h2>Modifier la prédiction</h2>
        </div>
        <form method="post">
            <div class="form-group"><label>Nom</label><input type="text" name="nom" value="{{ row[1] }}" required></div>
            <div class="form-group"><label>Prénom</label><input type="text" name="prenom" value="{{ row[2] }}" required></div>
            <div class="form-group">
                <label>Métier</label>
                <select name="metier">
                    {% for key, name in metier_names.items() %}
                    <option value="{{ key }}" {% if key == row[2] %}selected{% endif %}>{{ name }}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="form-group"><label>Âge actuel</label><input type="number" name="age_actuel" value="{{ age_actuel }}" required></div>
            <div class="form-group"><label>Santé (1-10)</label><input type="number" name="sante" min="1" max="10" value="{{ sante }}"></div>
            <hr>
            <h3>Critères spécifiques au métier</h3>
            {{ specific_fields|safe }}
            <button type="submit">Enregistrer les modifications</button>
            <a href="/collecte" class="btn-secondary" style="display: inline-block; text-align: center; text-decoration: none; margin-top: 0.5rem;">Annuler</a>
        </form>
    </div>
</body>
</html>
    ''', row=row, age_actuel=age_actuel, sante=sante, specific_fields=specific_fields_html, metier_names=METIER_NAMES)

# ---------- Supprimer ----------
@app.route('/supprimer/<int:id>')
@login_required
def supprimer(id):
    conn = sqlite3.connect('professeurs.db')
    c = conn.cursor()
    c.execute('DELETE FROM predictions WHERE id=?', (id,))
    conn.commit()
    conn.close()
    flash("Prédiction supprimée avec succès.", "success")
    return redirect(url_for('collecte'))

# ---------- Graphique ----------
@app.route('/graphique')
@login_required
def graphique():
    conn = sqlite3.connect('professeurs.db')
    c = conn.cursor()
    c.execute('SELECT metier, AVG(age_retraite) as moyenne, COUNT(*) as nb FROM predictions GROUP BY metier ORDER BY moyenne')
    rows = c.fetchall()
    conn.close()
    labels = [METIER_NAMES.get(row[0], row[0]) for row in rows]
    valeurs = [round(row[1], 1) for row in rows]
    return render_template_string('''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>{{ app_name }} - Graphique</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root { --primary: #0D1B2A; --secondary: #1D4ED8; --accent: #10B981; --light: #F1F5F9; }
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: 'Inter', sans-serif; background: var(--light); }
        .navbar { background: var(--primary); padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
        .logo img { height: 60px; width: auto; }
        .nav-links a { color: white; text-decoration: none; margin-left: 1.5rem; font-weight: 500; }
        .container { max-width: 1000px; margin: 2rem auto; padding: 0 1rem; }
        .card { background: white; border-radius: 1.5rem; padding: 2rem; text-align: center; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }
        canvas { max-width: 100%; margin: 1rem 0; }
        .btn { display: inline-block; background: var(--secondary); color: white; padding: 0.5rem 1rem; border-radius: 1rem; text-decoration: none; margin-top: 1rem; }
        footer { text-align: center; margin-top: 2rem; color: #64748b; }
    </style>
</head>
<body>
    <div class="logo">
    <img src="{{ url_for('static', filename='logo.svg') }}" alt="ChronoRetraite" style="height: 90px; width: auto;">
</div>
        <div class="nav-links">
            <a href="/">Accueil</a>
            <a href="/prediction">Prédiction</a>
            <a href="/collecte">Collecte</a>
            <a href="/stats">Stats</a>
            <a href="/logout">Déconnexion</a>
        </div>
    </nav>
    <div class="container">
        <div class="card">
            <h2><i class="fas fa-chart-bar"></i> Âge moyen de retraite par métier</h2>
            {% if labels %}
                <canvas id="ageChart" width="400" height="300"></canvas>
                <p><em>Basé sur les prédictions enregistrées.</em></p>
            {% else %}
                <p>Aucune donnée disponible. Faites d'abord des prédictions.</p>
            {% endif %}
            <a href="/" class="btn">← Retour</a>
        </div>
        <footer>© {{ app_name }} - Visualisation</footer>
    </div>
    {% if labels %}
    <script>
        const ctx = document.getElementById('ageChart').getContext('2d');
        new Chart(ctx, {
            type: 'bar',
            data: { labels: {{ labels|tojson }}, datasets: [{ label: 'Âge moyen (ans)', data: {{ valeurs|tojson }}, backgroundColor: '#1D4ED8', borderRadius: 10 }] },
            options: { responsive: true, plugins: { tooltip: { callbacks: { label: (ctx) => `${ctx.raw} ans` } } }, scales: { y: { min: 50, max: 70, title: { display: true, text: 'Âge' } }, x: { title: { display: true, text: 'Métier' } } } }
        });
    </script>
    {% endif %}
</body>
</html>
    ''', app_name=APP_NAME, labels=labels, valeurs=valeurs)

# ---------- Statistiques ----------
@app.route('/stats')
@login_required
def stats():
    conn = sqlite3.connect('professeurs.db')
    c = conn.cursor()
    c.execute('SELECT metier, COUNT(*), AVG(age_retraite) FROM predictions GROUP BY metier')
    stats_metier = c.fetchall()
    c.execute('SELECT COUNT(*) FROM predictions')
    total = c.fetchone()[0]
    conn.close()
    return render_template_string('''
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>{{ app_name }} - Statistiques</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root { --primary: #0D1B2A; --secondary: #1D4ED8; --light: #F1F5F9; }
        body { font-family: 'Inter', sans-serif; background: var(--light); padding: 2rem; }
        .container { max-width: 800px; margin: auto; background: white; border-radius: 2rem; padding: 2rem; }
        .logo-bar { display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }
        .logo-bar img { height: 60px; }
        .stat-card { background: var(--light); margin: 1rem 0; padding: 1rem; border-radius: 1rem; }
        .btn { display: inline-block; background: var(--secondary); color: white; padding: 0.5rem 1rem; border-radius: 1rem; text-decoration: none; margin-top: 1rem; }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo-bar">
            <img src="{{ url_for('static', filename='logo.png') }}" alt="ChronoRetraite">
            <h1>Statistiques des prédictions</h1>
        </div>
        <p>Total de prédictions : <strong>{{ total }}</strong></p>
        {% for metier, count, avg in stats_metier %}
        <div class="stat-card"><strong>{{ metier_names.get(metier, metier) }}</strong> : {{ count }} prédiction(s), âge moyen : {{ avg|round(1) }} ans</div>
        {% else %}
        <p>Aucune donnée.</p>
        {% endfor %}
        <a href="/" class="btn">← Retour</a>
    </div>
</body>
</html>
    ''', app_name=APP_NAME, total=total, stats_metier=stats_metier, metier_names=METIER_NAMES)

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=DEBUG)
