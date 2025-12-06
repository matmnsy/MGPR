import os
from flask import Flask, render_template, redirect, url_for, request, session, jsonify
from functools import wraps
import random

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "dev_secret_key")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "dev_password")


# Joueurs (1 à 12)
joueurs = [str(i) for i in range(1, 13)]

# === LISTE DES RÔLES DE BASE ===
base_roles = [
    {
        "name": "Enchanteresse",
        "icon": "role_enchanteresse.png",
        "camp": "le Village",
        "description": (
            "2 pouvoirs à utiliser pendant la nuit : Relique de vie (ressuscite) et Relique de mort (tue)."
        ),
    },
    {
        "name": "Démon",
        "icon": "role_demon.png",
        "camp": "les Démons",
        "description": "Peut éliminer une personne chaque nuit.",
    },
    {
        "name": "Sans visage",
        "icon": "role_sans_visage.png",
        "camp": "le Village",
        "description": "Peut regarder chaque nuit le rôle d’un joueur.",
    },
    {
        "name": "Cartomancienne",
        "icon": "role_cartomancienne.png",
        "camp": "le Village",
        "description": "Demande une info gentil/méchant sur un joueur.",
    },
    {
        "name": "Amant maudit",
        "icon": "role_amant_maudit.png",
        "camp": "le Village",
        "description": "Choisit un couple. Peut en choisir un nouveau si le premier meurt.",
    },
    {
        "name": "Esprit farceur",
        "icon": "role_esprit_farceur.png",
        "camp": "le Village",
        "description": "Peut échanger le rôle de deux joueurs.",
    },
    {
        "name": "Rédempteur",
        "icon": "role_redempteur.png",
        "camp": "le Village",
        "description": "Protège un joueur chaque nuit.",
    },
    {
        "name": "Vagabond",
        "icon": "role_vagabond.png",
        "camp": "le Village",
        "description": "Dort chez quelqu’un chaque nuit. Meurt si cette personne est tuée.",
    },
    {
        "name": "Démon",
        "icon": "role_demon.png",
        "camp": "les Démons",
        "description": "Peut éliminer une personne chaque nuit.",
    },
    {
        "name": "Nécromancien",
        "icon": "role_necromancien.png",
        "camp": "le Village",
        "description": "Peut consulter la personne décédée précédemment.",
    },
    {
        "name": "Exorciste",
        "icon": "role_exorciste.png",
        "camp": "le Village",
        "description": "Donne un vote supplémentaire à quelqu’un.",
    },
    {
        "name": "Démon",
        "icon": "role_demon.png",
        "camp": "les Démons",
        "description": "Peut éliminer une personne chaque nuit.",
    },
]

if len(base_roles) != len(joueurs):
    raise ValueError("Le nombre de rôles doit correspondre au nombre de joueurs.")

# Rôles mélangés
roles = {}

# État du jeu
votes = {j: 0 for j in joueurs}
joueurs_ayant_vote = set()
joueur_vote_pour = {}
admin_started = False
reveal_results = False
eliminated_players = set()

# Couple choisi par l'Amant maudit (contient 0 ou 2 joueurs)
couple_players = set()

# Messages des morts (pour Nécromancien)
# Un message = {"id": int, "author": "2", "text": "...", "revealed": bool}
necro_messages = []
necro_next_id = 1


# -----------------------------------------------------
# UTILITAIRES
# -----------------------------------------------------

def assign_random_roles():
    global roles
    shuffled = base_roles.copy()
    random.shuffle(shuffled)
    roles = {joueurs[i]: shuffled[i] for i in range(len(joueurs))}


def get_lover_partner(player_id: str):
    """Retourne l'autre amoureux si player_id est dans le couple."""
    if player_id in couple_players and len(couple_players) == 2:
        for p in couple_players:
            if p != player_id:
                return p
    return None


def get_necromancer():
    """Retourne le numéro du joueur qui est Nécromancien, ou None."""
    for j, r in roles.items():
        if r["name"] == "Nécromancien":
            return j
    return None


def player_has_last_will(joueur: str) -> bool:
    """True si ce joueur a déjà écrit une dernière volonté."""
    return any(m["author"] == joueur for m in necro_messages)


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper


# -----------------------------------------------------
# ROUTES JOUEURS
# -----------------------------------------------------

@app.route("/")
def select_player():
    return render_template("select_player.html", joueurs=joueurs)


@app.route("/vote/<votant>")
def vote_page(votant):

    if votant not in joueurs:
        return "Joueur inconnu", 404

    if votant in eliminated_players:
        already_sent = player_has_last_will(votant)
        return render_template("eliminated.html", votant=votant, already_sent=already_sent)

    if not admin_started:
        return render_template("welcome.html", votant=votant)

    if votant in joueurs_ayant_vote:

        if reveal_results:
            max_votes = max(votes.values()) if votes else 0
            winners = [j for j, v in votes.items() if v == max_votes]

            # Mapping amoureux pour l'affichage
            lover_map = {}
            if len(couple_players) == 2:
                cp = list(couple_players)
                lover_map[cp[0]] = cp[1]
                lover_map[cp[1]] = cp[0]

            reveal_couple = any(w in couple_players for w in winners)

            return render_template(
                "public_result.html",
                votes=votes,
                winners=winners,
                max_votes=max_votes,
                votant=votant,
                roles=roles,
                joueur_vote_pour=joueur_vote_pour,
                lover_map=lover_map,
                reveal_couple=reveal_couple,
                couple_players=couple_players,
            )

        return render_template("waiting.html", votant=votant, role=None)

    lover_partner = get_lover_partner(votant)

    return render_template(
        "index.html",
        votant=votant,
        joueurs=joueurs,
        eliminated_players=eliminated_players,
        roles=roles,
        lover_partner=lover_partner,
    )


@app.route("/vote/<votant>/<cible>")
def vote(votant, cible):

    if votant not in joueurs or cible not in joueurs:
        return "Joueur inconnu", 404

    if votant in eliminated_players:
        already_sent = player_has_last_will(votant)
        return render_template("eliminated.html", votant=votant, already_sent=already_sent)

    if votant == cible:
        return "Impossible de voter pour vous-même", 400

    if cible in eliminated_players:
        return "Ce joueur est éliminé", 400

    if votant in joueurs_ayant_vote:
        return redirect(url_for("vote_page", votant=votant))

    joueur_vote_pour[votant] = cible
    votes[cible] += 1
    joueurs_ayant_vote.add(votant)

    if reveal_results:
        max_votes = max(votes.values()) if votes else 0
        winners = [j for j, v in votes.items() if v == max_votes]

        lover_map = {}
        if len(couple_players) == 2:
            cp = list(couple_players)
            lover_map[cp[0]] = cp[1]
            lover_map[cp[1]] = cp[0]

        reveal_couple = any(w in couple_players for w in winners)

        return render_template(
            "public_result.html",
            votes=votes,
            winners=winners,
            max_votes=max_votes,
            votant=votant,
            roles=roles,
            joueur_vote_pour=joueur_vote_pour,
            lover_map=lover_map,
            reveal_couple=reveal_couple,
            couple_players=couple_players,
        )

    return render_template("waiting.html", votant=votant, role=None)


@app.route("/role/<votant>")
def view_role(votant):

    if votant not in joueurs:
        return "Joueur inconnu", 404

    role = roles.get(votant)
    if role is None:
        return "Rôle inconnu", 404

    lover_partner = get_lover_partner(votant)

    return render_template(
        "role.html",
        votant=votant,
        role=role,
        lover_partner=lover_partner,
        admin_started=admin_started,
    )


@app.route("/api/status")
def api_status():

    votant = request.args.get("votant")

    return jsonify({
        "reveal": reveal_results,
        "all_voted": len(joueurs_ayant_vote) == len(joueurs),
        "eliminated": votant in eliminated_players if votant else False,
        "admin_started": admin_started,
    })


# -----------------------------------------------------
# PAGE LISTE DES RÔLES
# -----------------------------------------------------

@app.route("/roles")
def roles_list():
    unique_by_name = {}
    for r in base_roles:
        unique_by_name.setdefault(r["name"], r)

    previous_url = request.referrer or url_for("select_player")

    return render_template("roles_list.html", roles=list(unique_by_name.values()), previous_url=previous_url)


# -----------------------------------------------------
# RESET
# -----------------------------------------------------

def reset_all():
    global votes, joueurs_ayant_vote, joueur_vote_pour, admin_started, reveal_results
    global eliminated_players, couple_players, necro_messages, necro_next_id

    votes = {j: 0 for j in joueurs}
    joueurs_ayant_vote.clear()
    joueur_vote_pour.clear()
    eliminated_players.clear()
    couple_players.clear()

    necro_messages.clear()
    necro_next_id = 1

    admin_started = False
    reveal_results = False
    assign_random_roles()


def reset_round_keep_eliminated():
    global votes, joueurs_ayant_vote, joueur_vote_pour, admin_started, reveal_results
    # On NE touche PAS à necro_messages / necro_next_id ici

    votes = {j: 0 for j in joueurs}
    joueurs_ayant_vote.clear()
    joueur_vote_pour.clear()
    admin_started = False
    reveal_results = False


@app.route("/reset")
def reset():
    votant = request.args.get("votant")
    reset_all()

    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    if votant in joueurs:
        return redirect(url_for("vote_page", votant=votant))

    return redirect(url_for("select_player"))


# -----------------------------------------------------
# ADMIN
# -----------------------------------------------------

@app.route("/admin/result")
@admin_required
def admin_result():
    """Page récapitulant les votes détaillés côté admin."""
    max_votes = max(votes.values()) if votes else 0
    winners = [j for j, v in votes.items() if v == max_votes]

    return render_template(
        "admin_result.html",
        votes=votes,
        winners=winners,
        max_votes=max_votes,
        roles=roles,
        joueur_vote_pour=joueur_vote_pour
    )


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error=True)
    return render_template("admin_login.html", error=False)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("select_player"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():

    total_voters = len(joueurs_ayant_vote)
    all_voted = (total_voters == len(joueurs))

    # Pour surligner le/les joueurs les plus votés après Reveal
    top_voted_players = []
    max_votes_value = 0
    if votes:
        max_votes_value = max(votes.values())
        top_voted_players = [j for j, v in votes.items() if v == max_votes_value]

    return render_template(
        "admin_dashboard.html",
        joueurs=joueurs,
        votes=votes,
        joueurs_ayant_vote=joueurs_ayant_vote,
        admin_started=admin_started,
        reveal_results=reveal_results,
        all_voted=all_voted,
        status=[(j, j in joueurs_ayant_vote) for j in joueurs],
        eliminated_players=eliminated_players,
        roles=roles,
        couple_players=couple_players,
        total_voters=total_voters,
        top_voted_players=top_voted_players,
        max_votes=max_votes_value,
    )


@app.route("/admin/start")
@admin_required
def admin_start():
    global admin_started
    admin_started = True
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reveal")
@admin_required
def admin_reveal():
    global reveal_results
    reveal_results = True
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/next_night")
@admin_required
def admin_next_night():
    reset_round_keep_eliminated()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/eliminate/<joueur>")
@admin_required
def admin_eliminate(joueur):
    if joueur in joueurs:
        eliminated_players.add(joueur)
    return redirect(url_for("admin_dashboard"))


# -----------------------------------------------------
# ADMIN : CHOIX DU COUPLE
# -----------------------------------------------------

@app.route("/admin/couple", methods=["GET", "POST"])
@admin_required
def admin_couple():
    global couple_players

    if request.method == "POST":
        selected = request.form.getlist("couple")
        if len(selected) == 2 and all(j in joueurs for j in selected):
            couple_players = set(selected)
        return redirect(url_for("admin_dashboard"))

    return render_template(
        "admin_couple.html",
        joueurs=joueurs,
        couple_players=couple_players,
        roles=roles
    )


# -----------------------------------------------------
# ADMIN : VUE DES MESSAGES DES MORTS
# -----------------------------------------------------

@app.route("/admin/necro_chat")
@admin_required
def admin_necro_chat():
    necro_id = get_necromancer()

    # dernier message par auteur (ou unique)
    messages_by_author = {}
    for m in necro_messages:
        messages_by_author[m["author"]] = m

    return render_template(
        "admin_necro_chat.html",
        necro_id=necro_id,
        eliminated_players=eliminated_players,
        messages_by_author=messages_by_author,
        roles=roles,
    )


@app.route("/admin/necro_reveal/<int:msg_id>")
@admin_required
def admin_necro_reveal(msg_id):
    """Marque un message comme révélé au Nécromancien."""
    for m in necro_messages:
        if m["id"] == msg_id:
            m["revealed"] = True
            break
    return redirect(url_for("admin_necro_chat"))


# -----------------------------------------------------
# ADMIN : ESPRIT FARCEUR (échange de rôles)
# -----------------------------------------------------

@app.route("/admin/esprit_farceur", methods=["GET", "POST"])
@admin_required
def admin_esprit_farceur():
    global roles

    message = None
    error = None

    if request.method == "POST":
        j1 = request.form.get("joueur1")
        j2 = request.form.get("joueur2")

        if not j1 or not j2:
            error = "Vous devez choisir deux joueurs."
        elif j1 == j2:
            error = "Les deux joueurs doivent être différents."
        elif j1 not in joueurs or j2 not in joueurs:
            error = "Joueur inconnu."
        else:
            # échange des rôles
            roles[j1], roles[j2] = roles[j2], roles[j1]
            message = f"Les rôles de Joueur {j1} et Joueur {j2} ont été échangés."

    return render_template(
        "admin_esprit_farceur.html",
        joueurs=joueurs,
        roles=roles,
        message=message,
        error=error,
    )


# -----------------------------------------------------
# JOUEUR MORT : PAGE DE RÉDACTION DU MESSAGE
# -----------------------------------------------------

@app.route("/dead_message/<joueur>", methods=["GET", "POST"])
def dead_message(joueur):
    global necro_messages, necro_next_id

    if joueur not in joueurs:
        return "Joueur inconnu", 404

    # Doit être éliminé
    if joueur not in eliminated_players:
        return redirect(url_for("vote_page", votant=joueur))

    # Un seul message par joueur
    already_sent = any(m["author"] == joueur for m in necro_messages)

    if request.method == "POST" and not already_sent:
        text = request.form.get("message", "").strip()
        if text:
            necro_messages.append({
                "id": necro_next_id,
                "author": joueur,
                "text": text,
                "revealed": False,
            })
            necro_next_id += 1

        return redirect(url_for("vote_page", votant=joueur))

    return render_template(
        "dead_message.html",
        joueur=joueur,
        already_sent=already_sent,
    )


# -----------------------------------------------------
# NÉCROMANCIEN : VUE DES MESSAGES RÉVÉLÉS
# -----------------------------------------------------

@app.route("/necro_chat/<joueur>")
def necro_chat(joueur):
    necro_id = get_necromancer()

    if necro_id is None or joueur != necro_id:
        return "Accès réservé au Nécromancien.", 403

    visible_messages = [m for m in necro_messages if m["revealed"]]

    return render_template(
        "necro_chat.html",
        joueur=joueur,
        messages=visible_messages,
    )


# -----------------------------------------------------
# DÉMARRAGE
# -----------------------------------------------------

assign_random_roles()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
