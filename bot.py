#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import random
import asyncio
import json
import os
import logging
import sys
import signal
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configuration du logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Récupérer le token
BOT_TOKEN = "8134429333:AAHkJKvi3_JM6Ipa23DoCg8F4fk4liKfDyQ"
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN non défini!")
    sys.exit(1)

# Port pour le serveur HTTP
PORT = int(os.environ.get("PORT", 10000))
# ============ VOTRE CODE EXISTANT ============

# Configuration du bot
STARTING_MONEY = int(os.environ.get("STARTING_MONEY", 500000))
MAX_BRAQUAGE_PLAYERS = int(os.environ.get("MAX_BRAQUAGE_PLAYERS", 6))
BRAQUAGE_SUCCESS_RATE = float(os.environ.get("BRAQUAGE_SUCCESS_RATE", 0.70))
BRAQUAGE_WIN_MULTIPLIER = int(os.environ.get("BRAQUAGE_WIN_MULTIPLIER", 2))
BRAQUAGE_LOSE_MULTIPLIER = int(os.environ.get("BRAQUAGE_LOSE_MULTIPLIER", 2))
ROB_SUCCESS_RATE = float(os.environ.get("ROB_SUCCESS_RATE", 0.15))
ROB_PENALTY = int(os.environ.get("ROB_PENALTY", 1000000))
COURSE_WAIT_TIME = int(os.environ.get("COURSE_WAIT_TIME", 180))
BRAQUAGE_WAIT_TIME = int(os.environ.get("BRAQUAGE_WAIT_TIME", 180))
MAX_COURSE_PLAYERS = int(os.environ.get("MAX_COURSE_PLAYERS", 10))

# Taux de réussite des braquages
BRAQUAGE_SUCCESS_RATES = {
    1: float(os.environ.get("RATE_1", 0.05)),
    2: float(os.environ.get("RATE_2", 0.10)),
    3: float(os.environ.get("RATE_3", 0.20)),
    4: float(os.environ.get("RATE_4", 0.45)),
    5: float(os.environ.get("RATE_5", 0.65)),
    6: float(os.environ.get("RATE_6", 0.80)),
}

COURSE_HORSES = {
    1: {"name": "Éclair Noir", "emoji": "🐎", "color": "⚫", "speed": "🔥"},
    2: {"name": "Tornade Blanche", "emoji": "🐎", "color": "⚪", "speed": "💨"},
    3: {"name": "Foudre Rouge", "emoji": "🐎", "color": "🔴", "speed": "⚡"},
    4: {"name": "Vent d'Argent", "emoji": "🐎", "color": "⚪", "speed": "💫"},
    5: {"name": "Tempête Bleue", "emoji": "🐎", "color": "🔵", "speed": "🌊"}
}

# ============ BASE DE DONNÉES ============

class Database:
    """Gestion de la base de données avec sauvegarde sur disque"""
    
    def __init__(self, filename: str = "game_data.json"):
        self.filename = filename
        self.players: Dict[str, Dict[str, Any]] = {}
        self.rob_penalties: Dict[int, int] = {}
        self.load()
    
    def load(self) -> None:
        """Charge les données"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.players = data.get('players', {})
                logger.info(f"✅ Données chargées: {len(self.players)} joueurs")
            else:
                logger.info("📂 Nouvelle base de données créée")
                self.players = {}
        except Exception as e:
            logger.error(f"❌ Erreur chargement: {e}")
            self.players = {}
    
    def save(self) -> None:
        """Sauvegarde les données"""
        try:
            # Sur Render, sauvegarder dans /tmp pour la persistance
            save_path = self.filename
            if os.environ.get("RENDER"):
                save_path = f"/tmp/{self.filename}"
            
            data = {
                'players': self.players,
                'last_save': datetime.now().isoformat()
            }
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde: {e}")
    
    # ... (gardez le reste de la classe Database identique)
    # Ajoutez toutes les méthodes de la classe Database ici
    # (get_player, transfer_to_bank, transfer_from_bank, etc.)

# ============ FONCTIONS UTILITAIRES ============

    def get_player(self, user_id: int, username: str = "", first_name: str = "") -> Dict[str, Any]:
        """Récupère ou crée un joueur"""
        user_id_str = str(user_id)
        if user_id_str not in self.players:
            self.players[user_id_str] = {
                'cash': STARTING_MONEY,
                'bank': 0,
                'username': username or f"user_{user_id}",
                'first_name': first_name or f"Joueur_{user_id}",
                'total_earned': 0,
                'total_lost': 0,
                'braquages_won': 0,
                'braquages_lost': 0,
                'robs_successful': 0,
                'robs_failed': 0,
                'courses_won': 0,
                'courses_lost': 0,
                'casino_won': 0,
                'casino_lost': 0,
                'created_at': datetime.now().isoformat()
            }
            self.save()
        else:
            if username:
                self.players[user_id_str]['username'] = username
            if first_name:
                self.players[user_id_str]['first_name'] = first_name
        
        return self.players[user_id_str]
    
    def transfer_to_bank(self, user_id: int, amount: int) -> bool:
        """Transfère de l'argent du cash vers la banque"""
        player = self.get_player(user_id)
        if player['cash'] >= amount:
            player['cash'] -= amount
            player['bank'] += amount
            self.save()
            return True
        return False
    
    def transfer_from_bank(self, user_id: int, amount: int) -> bool:
        """Transfère de l'argent de la banque vers le cash"""
        player = self.get_player(user_id)
        if player['bank'] >= amount:
            player['bank'] -= amount
            player['cash'] += amount
            self.save()
            return True
        return False
    
    def add_money(self, user_id: int, amount: int) -> None:
        """Ajoute de l'argent à un joueur"""
        player = self.get_player(user_id)
        player['cash'] += amount
        if amount > 0:
            player['total_earned'] += amount
        self.save()
    
    def remove_money(self, user_id: int, amount: int) -> bool:
        """Retire de l'argent d'un joueur"""
        player = self.get_player(user_id)
        if player['cash'] >= amount:
            player['cash'] -= amount
            player['total_lost'] += amount
            self.save()
            return True
        return False
    
    def get_leaderboard(self, limit: int = 20) -> List[Tuple[int, str, int]]:
        """Retourne le classement des joueurs"""
        players_list = []
        for user_id_str, data in self.players.items():
            total = data['cash'] + data['bank']
            name = data.get('first_name', data.get('username', 'Inconnu'))
            players_list.append((int(user_id_str), name, total))
        
        players_list.sort(key=lambda x: x[2], reverse=True)
        return players_list[:limit]
    
    def add_rob_penalty(self, user_id: int) -> None:
        """Ajoute une pénalité de vol"""
        self.rob_penalties[user_id] = ROB_PENALTY
    
    def remove_rob_penalty(self, user_id: int) -> bool:
        """Retire la pénalité de vol"""
        if user_id in self.rob_penalties:
            del self.rob_penalties[user_id]
            return True
        return False
    
    def has_rob_penalty(self, user_id: int) -> bool:
        """Vérifie si un joueur a une pénalité"""
        return user_id in self.rob_penalties
    
    def get_rob_penalty(self, user_id: int) -> int:
        """Retourne le montant de la pénalité"""
        return self.rob_penalties.get(user_id, 0)

# Initialisation de la base de données
db = Database()

# ============ GESTIONNAIRES ============

class BraquageManager:
    """Gestionnaire des braquages"""
    
    def __init__(self):
        self.active_braquages: Dict[int, Dict[str, Any]] = {}
        self.braquage_tasks: Dict[int, asyncio.Task] = {}
    
    def create_braquage(self, chat_id: int, creator_id: int, amount: int) -> Dict[str, Any]:
        """Crée un nouveau braquage"""
        braquage = {
            'chat_id': chat_id,
            'creator_id': creator_id,
            'players': {creator_id: amount},
            'total_pot': amount,
            'created_at': datetime.now(),
            'status': 'waiting',
            'expires_at': datetime.now() + timedelta(seconds=BRAQUAGE_WAIT_TIME)
        }
        self.active_braquages[chat_id] = braquage
        return braquage
    
    def join_braquage(self, chat_id: int, user_id: int, amount: int) -> Tuple[bool, str]:
        """Ajoute un joueur à un braquage"""
        if chat_id not in self.active_braquages:
            return False, "❌ Aucun braquage en cours!"
        
        braquage = self.active_braquages[chat_id]
        
        if braquage['status'] != 'waiting':
            return False, "❌ Ce braquage n'accepte plus de joueurs!"
        
        if user_id in braquage['players']:
            return False, "❌ Vous êtes déjà dans ce braquage!"
        
        if len(braquage['players']) >= MAX_BRAQUAGE_PLAYERS:
            return False, f"❌ Le braquage est complet ({MAX_BRAQUAGE_PLAYERS} joueurs max)!"
        
        braquage['players'][user_id] = amount
        braquage['total_pot'] += amount
        
        # Mettre à jour le taux de réussite
        num_players = len(braquage['players'])
        braquage['success_rate'] = BRAQUAGE_SUCCESS_RATES.get(num_players, 0.70)
        
        return True, f"✅ Vous avez rejoint le braquage avec {amount:,} €!"
    
    def get_success_rate(self, num_players: int) -> float:
        """Retourne le taux de réussite selon le nombre de joueurs"""
        return BRAQUAGE_SUCCESS_RATES.get(num_players, 0.70)
    
    def execute_braquage(self, chat_id: int) -> Tuple[bool, Dict[int, int]]:
        """Exécute un braquage"""
        if chat_id not in self.active_braquages:
            return False, {}
        
        braquage = self.active_braquages[chat_id]
        num_players = len(braquage['players'])
        
        # Obtenir le taux de réussite selon le nombre de joueurs
        success_rate = self.get_success_rate(num_players)
        success = random.random() < success_rate
        
        results = {}
        
        for user_id, amount in braquage['players'].items():
            if success:
                gain = amount * BRAQUAGE_WIN_MULTIPLIER
                results[user_id] = gain
                player = db.get_player(user_id)
                player['braquages_won'] += 1
                db.add_money(user_id, gain)
            else:
                loss = amount * BRAQUAGE_LOSE_MULTIPLIER
                results[user_id] = -loss
                player = db.get_player(user_id)
                player['braquages_lost'] += 1
                current_cash = player['cash']
                actual_loss = min(loss, current_cash)
                db.remove_money(user_id, actual_loss)
        
        # Nettoyer
        del self.active_braquages[chat_id]
        if chat_id in self.braquage_tasks:
            del self.braquage_tasks[chat_id]
        
        return success, results    
    async def start_braquage_timer(self, chat_id: int, context) -> None:
        """Démarre le timer du braquage (3 minutes)"""
        await asyncio.sleep(BRAQUAGE_WAIT_TIME)
        
        if chat_id not in self.active_braquages:
            return
        
        braquage = self.active_braquages[chat_id]
        num_players = len(braquage['players'])
        
        # Vérifier si le braquage est déjà en cours d'exécution
        if braquage['status'] != 'waiting':
            return
        
        braquage['status'] = 'executing'
        
        # Envoyer un message de début d'exécution
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"⏰ *LE BRAGUAGE COMMENCE!*\n\n"
                    f"👥 Participants: {num_players} joueur(s)\n"
                    f"💰 Pot total: {braquage['total_pot']:,} €\n"
                    f"📊 Chances de réussite: {braquage.get('success_rate', self.get_success_rate(num_players))*100:.0f}%\n\n"
                    f"🎲 *Lancement en cours...*"
                ),
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Erreur message début braquage: {e}")
        
        # Petite pause pour le suspense
        await asyncio.sleep(2)
        
        # Exécuter le braquage
        success, results = self.execute_braquage(chat_id)
        
        if not results:
            return
        
        # Construire le message de résultat
        result_text = (
            f"╔══════════════════════════════╗\n"
            f"║   🎯 *RÉSULTAT DU BRAQUAGE* 🎯   ║\n"
            f"╚══════════════════════════════╝\n\n"
        )
        
        if success:
            result_text += (
                f"✅ *BRAQUAGE RÉUSSI!* 🎉\n"
                f"🎊 Les participants repartent avec le butin!\n\n"
            )
        else:
            result_text += (
                f"❌ *BRAQUAGE ÉCHOUÉ!* 💀\n"
                f"🚔 La police était au rendez-vous...\n\n"
            )
        
        result_text += (
            f"👥 Participants: {num_players}/{MAX_BRAQUAGE_PLAYERS}\n"
            f"💰 Pot total: {braquage['total_pot']:,} €\n"
            f"📊 Taux de réussite: {self.get_success_rate(num_players)*100:.0f}%\n\n"
            f"{'─' * 30}\n\n"
        )
        
        for user_id, amount in results.items():
            try:
                user_info = await context.bot.get_chat(user_id)
                name = user_info.first_name
            except:
                name = f"Joueur {user_id}"
            
            if amount > 0:
                result_text += f"✅ *{name}*: +{amount:,} € 💰\n"
            else:
                result_text += f"❌ *{name}*: {amount:,} € 💸\n"
        
        # Ajouter un conseil selon le nombre de joueurs
        if num_players < 4 and not success:
            result_text += f"\n💡 *Conseil:* Plus il y a de joueurs, plus les chances de réussite augmentent!\n"
            result_text += f"👥 4 joueurs: 45% | 5 joueurs: 65% | 6 joueurs: 80%"
        elif success and num_players >= 4:
            result_text += f"\n💪 *Le travail d'équipe paie!*"
        
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=result_text,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Erreur envoi résultat braquage: {e}")
    
    def cancel_braquage(self, chat_id: int, user_id: int) -> Tuple[bool, str]:
        """Annule un braquage (seulement le créateur)"""
        if chat_id not in self.active_braquages:
            return False, "❌ Aucun braquage en cours!"
        
        braquage = self.active_braquages[chat_id]
        
        if braquage['creator_id'] != user_id:
            return False, "❌ Seul le créateur du braquage peut l'annuler!"
        
        # Annuler le timer
        if chat_id in self.braquage_tasks:
            self.braquage_tasks[chat_id].cancel()
            del self.braquage_tasks[chat_id]
        
        # Rembourser tous les joueurs
        num_players = len(braquage['players'])
        for player_id, amount in braquage['players'].items():
            db.add_money(player_id, amount)
        
        del self.active_braquages[chat_id]
        return True, f"✅ Braquage annulé! {num_players} joueur(s) remboursé(s)."
    
    def get_braquage(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Retourne un braquage"""
        return self.active_braquages.get(chat_id)
        
class CourseManager:
    """Gestionnaire des courses de chevaux"""
    
    def __init__(self):
        self.active_courses: Dict[int, Dict[str, Any]] = {}
        self.race_tasks: Dict[int, asyncio.Task] = {}
    
    def create_course(self, chat_id: int, creator_id: int) -> Dict[str, Any]:
        """Crée une nouvelle course"""
        course = {
            'chat_id': chat_id,
            'creator_id': creator_id,
            'players': {},
            'horses': COURSE_HORSES.copy(),
            'created_at': datetime.now(),
            'status': 'waiting',
            'total_pot': 0
        }
        self.active_courses[chat_id] = course
        return course
    
    def place_bet(self, chat_id: int, user_id: int, horse_num: int, amount: int) -> Tuple[bool, str]:
        """Place un pari sur un cheval"""
        if chat_id not in self.active_courses:
            return False, "❌ Aucune course en cours!"
        
        course = self.active_courses[chat_id]
        
        if horse_num not in course['horses']:
            return False, "❌ Numéro de cheval invalide!"
        
        if user_id in course['players']:
            return False, "❌ Vous avez déjà misé!"
        
        if len(course['players']) >= MAX_COURSE_PLAYERS:
            return False, f"❌ Course complète ({MAX_COURSE_PLAYERS} joueurs max)!"
        
        course['players'][user_id] = {
            'horse': horse_num,
            'bet': amount
        }
        course['total_pot'] += amount
        
        return True, f"✅ Misé {amount:,} € sur {course['horses'][horse_num]['name']}!"
    
    async def start_race(self, chat_id: int, context) -> None:
        """Démarre la course après le temps d'attente"""
        await asyncio.sleep(COURSE_WAIT_TIME)
        
        if chat_id not in self.active_courses:
            return
        
        course = self.active_courses[chat_id]
        
        if not course['players']:
            del self.active_courses[chat_id]
            return
        
        # Déterminer le cheval gagnant
        winning_horse = random.choice(list(course['horses'].keys()))
        winning_info = course['horses'][winning_horse]
        
        # Calculer les gains
        total_pot = course['total_pot']
        winners = []
        
        for user_id, data in course['players'].items():
            if data['horse'] == winning_horse:
                winners.append(user_id)
        
        # Distribuer les gains
        if winners:
            win_amount = total_pot // len(winners)
            for winner_id in winners:
                db.add_money(winner_id, win_amount)
                player = db.get_player(winner_id)
                player['courses_won'] += 1
        
        # Mettre à jour les stats des perdants
        for user_id, data in course['players'].items():
            if user_id not in winners:
                player = db.get_player(user_id)
                player['courses_lost'] += 1
        
        # Message de résultat
        result_text = (
            f"🏇 *RÉSULTATS DE LA COURSE* 🏇\n\n"
            f"{'═' * 30}\n"
            f"🏆 *VAINQUEUR* 🏆\n"
            f"{winning_info['emoji']} {winning_info['name']} {winning_info['speed']}\n"
            f"{'═' * 30}\n\n"
            f"💰 *Pot total:* {total_pot:,} €\n\n"
            f"📊 *Résultats:*\n"
        )
        
        for user_id, data in course['players'].items():
            try:
                user_info = await context.bot.get_chat(user_id)
                name = user_info.first_name
            except:
                name = f"Joueur {user_id}"
            
            horse_info = course['horses'][data['horse']]
            
            if user_id in winners:
                result_text += f"✅ {name}: +{win_amount:,} € ({horse_info['name']})\n"
            else:
                result_text += f"❌ {name}: -{data['bet']:,} € ({horse_info['name']})\n"
        
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=result_text,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Erreur envoi résultat course: {e}")
        
        # Nettoyer
        del self.active_courses[chat_id]
        if chat_id in self.race_tasks:
            del self.race_tasks[chat_id]
    
    def cancel_course(self, chat_id: int, user_id: int) -> Tuple[bool, str]:
        """Annule une course"""
        if chat_id not in self.active_courses:
            return False, "❌ Aucune course en cours!"
        
        course = self.active_courses[chat_id]
        
        if course['creator_id'] != user_id:
            return False, "❌ Seul le créateur peut annuler la course!"
        
        # Rembourser les joueurs
        for player_id, data in course['players'].items():
            db.add_money(player_id, data['bet'])
        
        # Annuler le timer
        if chat_id in self.race_tasks:
            self.race_tasks[chat_id].cancel()
            del self.race_tasks[chat_id]
        
        del self.active_courses[chat_id]
        return True, "✅ Course annulée! Tous les joueurs ont été remboursés."

# Instances des gestionnaires
braquage_manager = BraquageManager()
course_manager = CourseManager()

# ============ FONCTIONS UTILITAIRES ============

def create_progress_bar(value: float, max_value: float = 1.0, length: int = 10) -> str:
    """Crée une barre de progression stylée"""
    filled = int((value / max_value) * length)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}]"

def get_rank_emoji(position: int) -> str:
    """Retourne l'emoji correspondant au rang"""
    if position == 1:
        return "👑"
    elif position == 2:
        return "🥇"
    elif position == 3:
        return "🥈"
    elif position <= 5:
        return "💎"
    elif position <= 10:
        return "⭐"
    else:
        return "📊"

# ============ COMMANDES DE BASE ============

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Commande de démarrage avec style"""
    try:
        user = update.effective_user
        
        if not user:
            logger.error("User is None in cmd_start")
            return
        
        # Créer ou récupérer le joueur
        player = db.get_player(
            user.id,
            user.username or f"user_{user.id}",
            user.first_name or f"Joueur_{user.id}"
        )
        
        # Message de bienvenue stylé
        welcome_text = (
            f"╔══════════════════════════════╗\n"
            f"║   🎭 *BRAQUAGE BOT* 🎭   ║\n"
            f"╚══════════════════════════════╝\n\n"
            f"👤 *Bienvenue {user.first_name}!*\n\n"
            f"💰 *Capital de départ:*\n"
            f"   └─ {STARTING_MONEY:,} € en liquide\n\n"
            f"📋 *Commandes essentielles:*\n"
            f"   💰 /acc - Votre compte\n"
            f"   🏦 /bank - Votre banque\n"
            f"   🔫 /braquage - Braquages\n"
            f"   🕵️ /rob - Vols\n"
            f"   🏇 /course - Courses\n"
            f"   🎰 /casino - Casino\n"
            f"   🏆 /classement - Top joueurs\n\n"
            f"📚 /help - Guide complet"
        )
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN
        )
        
        logger.info(f"✅ User {user.id} ({user.first_name}) a démarré le bot")
        
    except Exception as e:
        logger.error(f"❌ Erreur dans cmd_start: {e}")
        # Message de fallback simple
        try:
            await update.message.reply_text(
                f"🎭 Bienvenue {update.effective_user.first_name}!\n\n"
                f"💰 Vous avez reçu {STARTING_MONEY:,} €\n\n"
                f"Tapez /help pour voir les commandes"
            )
        except:
            logger.error("Impossible d'envoyer le message de fallback")
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Aide détaillée"""
    help_text = (
        "📚 GUIDE COMPLET 📚\n\n"
        "💰 FINANCES\n"
        "/acc - Voir votre argent liquide\n"
        "/bank <montant> - Déposer en banque\n"
        "/retrait <montant> - Retirer de la banque\n\n"
        "🔫 BRAQUAGES\n"
        "/braquage <mise> - Lancer/rejoindre\n"
        "• 6 joueurs max\n"
        "• 70% réussite\n"
        "• Gain: x2 | Perte: x2\n\n"
        "🕵️ VOLS\n"
        "/rob (répondre à un message) - Voler\n"
        "• 15% réussite\n"
        "• Amende: 1 000 000 €\n\n"
        "🏇 COURSES\n"
        "/course - Lancer une course\n"
        "/cheval <numéro> <mise> - Miser (1 a 5)\n"
        "/annuler_course - Annuler la course\n"
        "• 5 chevaux\n"
        "• 10 joueurs max\n"
        "• 3 min d'attente\n\n"
        "🎰 CASINO\n"
        "/roulette <mise> <rouge/noir/vert> - Roulette\n"
        "/slot <mise> - Machine à sous\n"
        "/des <mise> - Jeu de dés\n"
        "/blackjack <mise> - Blackjack\n\n"
        "🏆 CLASSEMENT\n"
        "/classement - Top 10 des plus riches\n\n"
        "❓ AIDE\n"
        "/help - Afficher cette aide"
    )
    
    await update.message.reply_text(help_text)
    
async def cmd_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le compte avec style"""
    try:
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
            player = db.get_player(target_user.id)
            title = f"Compte de {target_user.first_name}"
        else:
            user = update.effective_user
            player = db.get_player(user.id)
            title = "Votre compte"
        
        cash = player['cash']
        bank = player['bank']
        total = cash + bank
        
        # Déterminer le statut
        if total >= 10000000:
            status = "🌟 Légende"
            status_emoji = "👑"
        elif total >= 5000000:
            status = "💎 Millionnaire"
            status_emoji = "💎"
        elif total >= 1000000:
            status = "💰 Riche"
            status_emoji = "💰"
        elif total >= 500000:
            status = "📈 En croissance"
            status_emoji = "📈"
        else:
            status = "📉 Pauvre"
            status_emoji = "📉"
        
        account_text = (
            f"╔══════════════════════════════╗\n"
            f"║   💰 *{title.upper()}* 💰   ║\n"
            f"╚══════════════════════════════╝\n\n"
            f"{status_emoji} *Statut:* {status}\n\n"
            f"💳 *Liquide:* {cash:,} €\n"
            f"🏦 *Banque:* {bank:,} €\n"
            f"{'─' * 30}\n"
            f"📊 *Total:* {total:,} €\n\n"
            f"📈 *Progression:*\n"
            f"{create_progress_bar(min(total / 10000000, 1.0))} {min((total / 10000000) * 100, 100):.1f}%"
        )
        
        await update.message.reply_text(account_text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Erreur dans cmd_account: {e}")
        await update.message.reply_text("❌ Erreur lors de l'affichage du compte")

async def cmd_bank(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le compte bancaire avec style"""
    try:
        user = update.effective_user
        player = db.get_player(user.id)
        
        cash = player['cash']
        bank = player['bank']
        total = cash + bank
        
        # Calculer les intérêts potentiels (fictif, pour le style)
        potential_interest = int(bank * 0.05)
        
        bank_text = (
            f"╔══════════════════════════════╗\n"
            f"║  🏦 *BANQUE DE {player['first_name'][:15].upper()}* 🏦  ║\n"
            f"╚══════════════════════════════╝\n\n"
            f"🔒 *Compte sécurisé*\n\n"
            f"💳 *Solde bancaire:* {bank:,} €\n"
            f"💰 *Argent liquide:* {cash:,} €\n"
            f"{'─' * 30}\n"
            f"📊 *Total:* {total:,} €\n\n"
            f"📈 *Intérêts potentiels:* +{potential_interest:,} €\n"
            f"🛡️ *Protection:* Active ✅\n\n"
            f"💡 *Astuce:* L'argent en banque est\n"
            f"protégé contre les vols !"
        )
        
        await update.message.reply_text(bank_text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        logger.error(f"Erreur dans cmd_bank: {e}")
        await update.message.reply_text("❌ Erreur lors de l'affichage de la banque")

async def cmd_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dépose de l'argent en banque"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /deposit [montant]")
        return
    
    try:
        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("❌ Le montant doit être positif!")
            return
        
        if db.transfer_to_bank(user.id, amount):
            player = db.get_player(user.id)
            await update.message.reply_text(
                f"✅ *Dépôt effectué!*\n\n"
                f"💸 Montant: {amount:,} €\n"
                f"🏦 Nouveau solde bancaire: {player['bank']:,} €\n"
                f"💰 Liquide restant: {player['cash']:,} €",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"❌ Fonds insuffisants!\n"
                f"Vous avez {db.get_player(user.id)['cash']:,} € en liquide"
            )
    except ValueError:
        await update.message.reply_text("❌ Montant invalide!")

async def cmd_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Retire de l'argent de la banque"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /withdraw [montant]")
        return
    
    try:
        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("❌ Le montant doit être positif!")
            return
        
        if db.transfer_from_bank(user.id, amount):
            player = db.get_player(user.id)
            await update.message.reply_text(
                f"✅ *Retrait effectué!*\n\n"
                f"💸 Montant: {amount:,} €\n"
                f"💰 Nouveau liquide: {player['cash']:,} €\n"
                f"🏦 Solde bancaire restant: {player['bank']:,} €",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"❌ Fonds insuffisants en banque!\n"
                f"Solde bancaire: {db.get_player(user.id)['bank']:,} €"
            )
    except ValueError:
        await update.message.reply_text("❌ Montant invalide!")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les statistiques détaillées"""
    user = update.effective_user
    player = db.get_player(user.id)
    
    total = player['cash'] + player['bank']
    
    # Calculer les ratios
    total_braquages = player['braquages_won'] + player['braquages_lost']
    braquage_ratio = (player['braquages_won'] / total_braquages * 100) if total_braquages > 0 else 0
    
    total_robs = player['robs_successful'] + player['robs_failed']
    rob_ratio = (player['robs_successful'] / total_robs * 100) if total_robs > 0 else 0
    
    total_courses = player['courses_won'] + player['courses_lost']
    course_ratio = (player['courses_won'] / total_courses * 100) if total_courses > 0 else 0
    
    stats_text = (
        f"╔══════════════════════════════╗\n"
        f"║  📊 *STATISTIQUES* 📊  ║\n"
        f"╚══════════════════════════════╝\n\n"
        f"👤 *{player['first_name']}*\n\n"
        f"💰 *Finances:*\n"
        f"   Liquide: {player['cash']:,} €\n"
        f"   Banque: {player['bank']:,} €\n"
        f"   Total: {total:,} €\n\n"
        f"📈 *Historique:*\n"
        f"   ✅ Gains: {player['total_earned']:,} €\n"
        f"   ❌ Pertes: {player['total_lost']:,} €\n\n"
        f"🔫 *Braquages:* ({total_braquages} total)\n"
        f"   ✅ Réussis: {player['braquages_won']}\n"
        f"   ❌ Échoués: {player['braquages_lost']}\n"
        f"   📊 Ratio: {braquage_ratio:.1f}%\n\n"
        f"🕵️ *Vols:* ({total_robs} total)\n"
        f"   ✅ Réussis: {player['robs_successful']}\n"
        f"   ❌ Échoués: {player['robs_failed']}\n"
        f"   📊 Ratio: {rob_ratio:.1f}%\n\n"
        f"🏇 *Courses:* ({total_courses} total)\n"
        f"   ✅ Gagnées: {player['courses_won']}\n"
        f"   ❌ Perdues: {player['courses_lost']}\n"
        f"   📊 Ratio: {course_ratio:.1f}%"
    )
    
    await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

# ============ SYSTÈME DE BRAQUAGE ============

async def cmd_braquage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lance ou rejoint un braquage"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: /braquage [montant]\n"
            "Exemple: /braquage 1000000"
        )
        return
    
    try:
        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("❌ Le montant doit être positif!")
            return
        
        player = db.get_player(user.id)
        if player['cash'] < amount:
            await update.message.reply_text(
                f"❌ Fonds insuffisants!\n"
                f"💰 Vous avez {player['cash']:,} € en liquide"
            )
            return
        
        existing_braquage = braquage_manager.get_braquage(chat_id)
        
        if existing_braquage:
            # Rejoindre un braquage existant
            success, message = braquage_manager.join_braquage(chat_id, user.id, amount)
            
            if success:
                db.remove_money(user.id, amount)
                
                braquage = braquage_manager.get_braquage(chat_id)
                num_players = len(braquage['players'])
                success_rate = braquage_manager.get_success_rate(num_players) * 100
                
                # Calculer le temps restant
                time_left = braquage['expires_at'] - datetime.now()
                minutes_left = max(0, int(time_left.total_seconds() // 60))
                seconds_left = max(0, int(time_left.total_seconds() % 60))
                
                # Message de warning si peu de joueurs
                warning = ""
                if num_players < 4:
                    warning = (
                        f"\n⚠️ *Attention:* Avec seulement {num_players} joueur(s), "
                        f"les chances de réussite sont faibles ({success_rate:.0f}%)!\n"
                        f"💡 Essayez d'être au moins 4 pour de meilleures chances."
                    )
                
                keyboard = [
                    [InlineKeyboardButton("🔫 Rejoindre le braquage", callback_data=f"join_braquage_{chat_id}")],
                    [InlineKeyboardButton("❌ Annuler le braquage", callback_data=f"cancel_braquage_{chat_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"✅ *Vous avez rejoint le braquage!*\n\n"
                    f"🔫 *BRAQUAGE EN COURS*\n"
                    f"{'═' * 30}\n\n"
                    f"👤 *{user.first_name}* a misé {amount:,} €\n"
                    f"👥 Joueurs: {num_players}/{MAX_BRAQUAGE_PLAYERS}\n"
                    f"💰 Pot total: {braquage['total_pot']:,} €\n"
                    
                    f"{create_progress_bar(success_rate/100)}\n\n"
                    f"⏰ *Temps restant: {minutes_left}min {seconds_left}s*\n"
                    f"{warning}",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Si le braquage est complet (6 joueurs), l'exécuter immédiatement
                if num_players >= MAX_BRAQUAGE_PLAYERS:
                    if chat_id in braquage_manager.braquage_tasks:
                        braquage_manager.braquage_tasks[chat_id].cancel()
                    
                    await update.message.reply_text(
                        "👥 *Braquage complet!* Lancement immédiat...",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    await braquage_manager.start_braquage_timer(chat_id, context)
            else:
                await update.message.reply_text(message)
        else:
            # Créer un nouveau braquage
            braquage_manager.create_braquage(chat_id, user.id, amount)
            db.remove_money(user.id, amount)
            
            # Taux de réussite pour 1 joueur
            success_rate = braquage_manager.get_success_rate(1) * 100
            
            # Tableau des taux de réussite
            rates_table = ""
            for players, rate in BRAQUAGE_SUCCESS_RATES.items():
                rates_table += f"• {players} joueur(s): {rate*100:.0f}%\n"
            
            keyboard = [
                [InlineKeyboardButton("🔫 Rejoindre le braquage", callback_data=f"join_braquage_{chat_id}")],
                [InlineKeyboardButton("❌ Annuler le braquage", callback_data=f"cancel_braquage_{chat_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"🔫 *NOUVEAU BRAQUAGE LANCÉ!*\n"
                f"{'═' * 30}\n\n"
                f"👤 *Créateur:* {user.first_name}\n"
                f"💰 *Mise de départ:* {amount:,} €\n"
                f"👥 *Joueurs:* 1/{MAX_BRAQUAGE_PLAYERS}\n"
                f"💰 *Pot:* {amount:,} €\n\n"
                f"📈 *Actuel:* {success_rate:.0f}% {create_progress_bar(success_rate/100)}\n\n"
                f"⏰ *Temps restant: 3min 0s*\n\n"              
                f"💡 *Conseil:* Plus il y a de joueurs,\n"
                f"plus les chances de réussite augmentent!\n\n"
                f"*/braquage [montant] pour rejoindre*\n"
                f"*/cancelbraquage pour annuler*",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Démarrer le timer de 3 minutes
            task = asyncio.create_task(braquage_manager.start_braquage_timer(chat_id, context))
            braquage_manager.braquage_tasks[chat_id] = task
    
    except ValueError:
        await update.message.reply_text("❌ Montant invalide! Usage: /braquage [montant]")

async def cmd_cancel_braquage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Annule un braquage"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    success, message = braquage_manager.cancel_braquage(chat_id, user.id)
    await update.message.reply_text(message)

async def cmd_braquage_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le statut du braquage avec le temps restant"""
    chat_id = update.effective_chat.id
    braquage = braquage_manager.get_braquage(chat_id)
    
    if not braquage:
        await update.message.reply_text("❌ Aucun braquage en cours!")
        return
    
    num_players = len(braquage['players'])
    success_rate = braquage_manager.get_success_rate(num_players) * 100
    
    # Calculer le temps restant
    time_left = braquage['expires_at'] - datetime.now()
    if time_left.total_seconds() < 0:
        time_display = "En cours d'exécution..."
    else:
        minutes_left = int(time_left.total_seconds() // 60)
        seconds_left = int(time_left.total_seconds() % 60)
        time_display = f"{minutes_left}min {seconds_left}s"
    
    # Liste des participants
    players_list = []
    for user_id, amount in braquage['players'].items():
        try:
            user_info = await context.bot.get_chat(user_id)
            name = user_info.first_name
        except:
            name = f"Joueur {user_id}"
        
        crown = "👑" if user_id == braquage['creator_id'] else "👤"
        players_list.append(f"{crown} {name}: {amount:,} €")
    
    # Taux de réussite selon le nombre de joueurs
    rates_info = ""
    for players, rate in BRAQUAGE_SUCCESS_RATES.items():
        marker = "➡️" if players == num_players else "•"
        rates_info += f"{marker} {players} joueur(s): {rate*100:.0f}%\n"
    
    status_text = (
        f"🔫 *STATUT DU BRAQUAGE*\n"
        f"{'═' * 30}\n\n"
        f"👥 *Joueurs:* {num_players}/{MAX_BRAQUAGE_PLAYERS}\n"
        f"💰 *Pot total:* {braquage['total_pot']:,} €\n"
        f"📊 *Réussite actuelle:* {success_rate:.0f}%\n"
        f"{create_progress_bar(success_rate/100)}\n\n"
        f"⏰ *Temps:* {time_display}\n\n"
        f"📈 *Taux par joueurs:*\n"
        f"{rates_info}\n"
        f"*Participants:*\n"
        f"{chr(10).join(players_list)}\n\n"
        f"💡 Le braquage se lance automatiquement\n"
        f"à la fin du timer, quel que soit le nombre\n"
        f"de joueurs!"
    )
    
    await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)

async def cmd_force_braquage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Force le lancement d'un braquage (créateur uniquement)"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    braquage = braquage_manager.get_braquage(chat_id)
    
    if not braquage:
        await update.message.reply_text("❌ Aucun braquage en cours!")
        return
    
    if braquage['creator_id'] != user.id:
        await update.message.reply_text("❌ Seul le créateur peut forcer le lancement!")
        return
    
    # Annuler le timer
    if chat_id in braquage_manager.braquage_tasks:
        braquage_manager.braquage_tasks[chat_id].cancel()
    
    await update.message.reply_text(
        "⚡ *Lancement forcé du braquage!*",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Lancer immédiatement
    await braquage_manager.start_braquage_timer(chat_id, context)
# ============ SYSTÈME DE VOL ============

async def cmd_rob(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vole un autre joueur"""
    user = update.effective_user
    
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❌ Répondez au message d'un joueur avec /rob pour le voler!"
        )
        return
    
    target_user = update.message.reply_to_message.from_user
    
    if user.id == target_user.id:
        await update.message.reply_text("❌ Vous ne pouvez pas vous voler vous-même!")
        return
    
    if db.has_rob_penalty(user.id):
        penalty = db.get_rob_penalty(user.id)
        keyboard = [
            [InlineKeyboardButton("💸 Payer l'amende", callback_data=f"pay_penalty_{user.id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🚔 Vous avez une amende de {penalty:,} € à payer!\n"
            f"Utilisez /paypenalty pour payer.",
            reply_markup=reply_markup
        )
        return
    
    target_player = db.get_player(target_user.id)
    
    if target_player['cash'] <= 0:
        await update.message.reply_text("❌ Ce joueur n'a pas d'argent liquide!")
        return
    
    success = random.random() < ROB_SUCCESS_RATE
    user_player = db.get_player(user.id)
    
    if success:
        steal_amount = min(target_player['cash'], random.randint(1000, 100000))
        db.remove_money(target_user.id, steal_amount)
        db.add_money(user.id, steal_amount)
        user_player['robs_successful'] += 1
        
        await update.message.reply_text(
            f"🕵️ *VOL RÉUSSI!*\n\n"
            f"💰 Volé: {steal_amount:,} €\n"
            f"👤 Victime: {target_user.first_name}\n"
            f"💳 Votre solde: {user_player['cash']:,} €",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        db.add_rob_penalty(user.id)
        user_player['robs_failed'] += 1
        
        keyboard = [
            [InlineKeyboardButton("💸 Payer", callback_data=f"pay_penalty_{user.id}")],
            [InlineKeyboardButton(f"❤️ Payer pour {user.first_name}", callback_data=f"pay_other_{user.id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🚔 *VOL ÉCHOUÉ!*\n\n"
            f"👮 La police vous a repéré!\n"
            f"💸 Amende: {ROB_PENALTY:,} €\n\n"
            f"D'autres peuvent payer pour vous.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

async def cmd_pay_penalty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Paie sa propre amende"""
    user = update.effective_user
    
    if not db.has_rob_penalty(user.id):
        await update.message.reply_text("✅ Vous n'avez pas d'amende!")
        return
    
    penalty = db.get_rob_penalty(user.id)
    
    if db.remove_money(user.id, penalty):
        db.remove_rob_penalty(user.id)
        await update.message.reply_text(
            f"✅ *Amende payée!*\n"
            f"💸 Montant: {penalty:,} €\n"
            f"Vous pouvez à nouveau voler!",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            f"❌ Fonds insuffisants! Besoin de {penalty:,} €"
        )

# ============ SYSTÈME DE COURSES ============

async def cmd_course(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lance une course de chevaux"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    if chat_id in course_manager.active_courses:
        await update.message.reply_text("❌ Une course est déjà en cours!")
        return
    
    course_manager.create_course(chat_id, user.id)
    
    horses_text = ""
    for num, info in COURSE_HORSES.items():
        horses_text += f"{num}. {info['emoji']} *{info['name']}* {info['speed']}\n"
    
    keyboard = []
    row = []
    for num, info in COURSE_HORSES.items():
        row.append(InlineKeyboardButton(
            f"{num}. {info['name']}",
            callback_data=f"bet_horse_{chat_id}_{num}"
        ))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🏇 *COURSE DE CHEVAUX* 🏇\n\n"
        f"*Chevaux:*\n{horses_text}\n"
        f"⏱️ Départ dans {COURSE_WAIT_TIME//60} min\n"
        f"👥 0/{MAX_COURSE_PLAYERS} joueurs\n\n"
        f"*/cheval [n°] [mise] pour miser*\n"
        f"*/cancelcourse pour annuler*",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    task = asyncio.create_task(course_manager.start_race(chat_id, context))
    course_manager.race_tasks[chat_id] = task

async def cmd_cheval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mise sur un cheval"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Usage: /cheval [numéro] [montant]")
        return
    
    try:
        horse_num = int(context.args[0])
        amount = int(context.args[1])
        
        if horse_num not in COURSE_HORSES:
            await update.message.reply_text(f"❌ Cheval invalide! (1-{len(COURSE_HORSES)})")
            return
        
        if amount <= 0:
            await update.message.reply_text("❌ La mise doit être positive!")
            return
        
        player = db.get_player(user.id)
        if player['cash'] < amount:
            await update.message.reply_text(
                f"❌ Fonds insuffisants! Vous avez {player['cash']:,} €"
            )
            return
        
        success, message = course_manager.place_bet(chat_id, user.id, horse_num, amount)
        
        if success:
            db.remove_money(user.id, amount)
            
            course = course_manager.active_courses[chat_id]
            num_players = len(course['players'])
            
            await update.message.reply_text(
                f"{message}\n"
                f"👥 {num_players}/{MAX_COURSE_PLAYERS} joueurs\n"
                f"💰 Pot: {course['total_pot']:,} €"
            )
            
            if num_players >= MAX_COURSE_PLAYERS:
                if chat_id in course_manager.race_tasks:
                    course_manager.race_tasks[chat_id].cancel()
                await course_manager.start_race(chat_id, context)
        else:
            await update.message.reply_text(message)
    
    except ValueError:
        await update.message.reply_text("❌ Format invalide!")

async def cmd_cancel_course(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Annule une course"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    success, message = course_manager.cancel_course(chat_id, user.id)
    await update.message.reply_text(message)

# ============ JEUX DE CASINO ============

async def cmd_casino(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Joue à la roulette"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /casino [mise]")
        return
    
    try:
        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("❌ La mise doit être positive!")
            return
        
        player = db.get_player(user.id)
        if player['cash'] < amount:
            await update.message.reply_text(
                f"❌ Fonds insuffisants! Vous avez {player['cash']:,} €"
            )
            return
        
        db.remove_money(user.id, amount)
        
        keyboard = [
            [
                InlineKeyboardButton("🔴 Rouge (x2)", callback_data=f"casino_{user.id}_red_{amount}"),
                InlineKeyboardButton("⚫ Noir (x2)", callback_data=f"casino_{user.id}_black_{amount}")
            ],
            [
                InlineKeyboardButton("📊 Pair (x2)", callback_data=f"casino_{user.id}_even_{amount}"),
                InlineKeyboardButton("📊 Impair (x2)", callback_data=f"casino_{user.id}_odd_{amount}")
            ],
            [
                InlineKeyboardButton("1-12 (x3)", callback_data=f"casino_{user.id}_low_{amount}"),
                InlineKeyboardButton("13-24 (x3)", callback_data=f"casino_{user.id}_mid_{amount}")
            ],
            [
                InlineKeyboardButton("25-36 (x3)", callback_data=f"casino_{user.id}_high_{amount}"),
                InlineKeyboardButton("🎯 Numéro (x36)", callback_data=f"casino_{user.id}_number_{amount}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎰 *ROULETTE*\n\n"
            f"💰 Mise: {amount:,} €\n"
            f"🎲 Choisissez votre pari:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    except ValueError:
        await update.message.reply_text("❌ Montant invalide!")

async def cmd_slot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Machine à sous"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /slot [mise]")
        return
    
    try:
        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("❌ La mise doit être positive!")
            return
        
        player = db.get_player(user.id)
        if player['cash'] < amount:
            await update.message.reply_text(
                f"❌ Fonds insuffisants! Vous avez {player['cash']:,} €"
            )
            return
        
        db.remove_money(user.id, amount)
        
        symbols = {"🍒": 1, "🍋": 2, "🍊": 3, "🍇": 5, "💎": 10, "7️⃣": 20, "⭐": 50, "👑": 100}
        symbol_list = list(symbols.keys())
        weights = [30, 25, 20, 15, 5, 3, 1, 1]
        
        slots = random.choices(symbol_list, weights=weights, k=3)
        
        multiplier = 0
        result_text = ""
        
        if slots[0] == slots[1] == slots[2]:
            multiplier = symbols[slots[0]]
            if multiplier >= 100:
                result_text = "🌟 JACKPOT ROYAL! 🌟"
            elif multiplier >= 50:
                result_text = "💫 SUPER JACKPOT!"
            elif multiplier >= 10:
                result_text = "✨ GROS GAIN!"
            else:
                result_text = "🎉 JACKPOT!"
        elif slots[0] == slots[1] or slots[1] == slots[2]:
            multiplier = symbols[slots[0] if slots[0] == slots[1] else slots[1]] // 2
            result_text = "👍 Double!"
        else:
            result_text = "😢 Perdu!"
        
        gain = amount * multiplier
        db.add_money(user.id, gain)
        
        slot_display = f"[ {slots[0]} | {slots[1]} | {slots[2]} ]"
        
        await update.message.reply_text(
            f"🎰 *MACHINE À SOUS*\n\n"
            f"{slot_display}\n\n"
            f"💰 Mise: {amount:,} €\n"
            f"{result_text}\n"
            f"{'💚 Gain: ' + f'{gain:,} €' if gain > 0 else '💔 Perte: ' + f'{amount:,} €'}",
            parse_mode=ParseMode.MARKDOWN
        )
    
    except ValueError:
        await update.message.reply_text("❌ Montant invalide!")

async def cmd_dice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Jeu de dés"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text("❌ Usage: /dice [mise]")
        return
    
    try:
        amount = int(context.args[0])
        if amount <= 0:
            await update.message.reply_text("❌ La mise doit être positive!")
            return
        
        player = db.get_player(user.id)
        if player['cash'] < amount:
            await update.message.reply_text(
                f"❌ Fonds insuffisants! Vous avez {player['cash']:,} €"
            )
            return
        
        db.remove_money(user.id, amount)
        
        player_dice = [random.randint(1, 6), random.randint(1, 6)]
        dealer_dice = [random.randint(1, 6), random.randint(1, 6)]
        
        player_sum = sum(player_dice)
        dealer_sum = sum(dealer_dice)
        
        if player_sum > dealer_sum:
            multiplier = 2
            result = "GAGNÉ!"
        elif player_sum < dealer_sum:
            multiplier = 0
            result = "PERDU!"
        else:
            multiplier = 1
            result = "ÉGALITÉ!"
        
        gain = amount * multiplier
        
        if gain > 0:
            db.remove_money(user.id, amount)
            db.add_money(user.id, gain)
        elif multiplier == 1:
            db.add_money(user.id, amount)
        
        dice_emojis = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
        
        await update.message.reply_text(
            f"🎲 *JEU DE DÉS*\n\n"
            f"👤 Vous: {dice_emojis[player_dice[0]]} {dice_emojis[player_dice[1]]} = {player_sum}\n"
            f"🤖 Croupier: {dice_emojis[dealer_dice[0]]} {dice_emojis[dealer_dice[1]]} = {dealer_sum}\n\n"
            f"💰 Mise: {amount:,} €\n"
            f"📊 {result}\n"
            f"{'💚 Gain: ' + f'{gain:,} €' if gain > amount else '💔 Perte: ' + f'{amount:,} €' if multiplier == 0 else '🤝 Remboursé: ' + f'{amount:,} €'}",
            parse_mode=ParseMode.MARKDOWN
        )
    
    except ValueError:
        await update.message.reply_text("❌ Montant invalide!")

# ============ CLASSEMENT ============

async def cmd_classement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le classement"""
    leaderboard = db.get_leaderboard(20)
    
    if not leaderboard:
        await update.message.reply_text("📊 Aucun joueur!")
        return
    
    classement_text = (
        f"╔══════════════════════════════╗\n"
        f"║   🏆 *CLASSEMENT* 🏆   ║\n"
        f"╚══════════════════════════════╝\n\n"
    )
    
    for i, (user_id, name, total) in enumerate(leaderboard, 1):
        emoji = get_rank_emoji(i)
        classement_text += f"{emoji} {i}. *{name[:20]}*: {total:,} €\n"
    
    classement_text += f"\n📊 *{len(db.players)}* joueurs au total"
    
    await update.message.reply_text(classement_text, parse_mode=ParseMode.MARKDOWN)

# ============ GESTION DES CALLBACKS ============

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gestionnaire des callbacks"""
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split('_')
    action = data_parts[0]
    
    try:
        if action == "join" and data_parts[1] == "braquage":
            chat_id = int(data_parts[2])
            await query.edit_message_text(
                f"🔫 Pour rejoindre: /braquage [montant]\n"
                f"Exemple: /braquage 1000000"
            )
        
        elif action == "cancel" and data_parts[1] == "braquage":
            chat_id = int(data_parts[2])
            user_id = query.from_user.id
            
            success, message = braquage_manager.cancel_braquage(chat_id, user_id)
            await query.edit_message_text(message)
        
        elif action == "pay" and data_parts[1] == "penalty":
            user_id = int(data_parts[2])
            payer = query.from_user
            
            if payer.id == user_id:
                if db.has_rob_penalty(user_id):
                    penalty = db.get_rob_penalty(user_id)
                    if db.remove_money(user_id, penalty):
                        db.remove_rob_penalty(user_id)
                        await query.edit_message_text(
                            f"✅ Amende de {penalty:,} € payée!"
                        )
                    else:
                        await query.edit_message_text(
                            f"❌ Fonds insuffisants! Besoin de {penalty:,} €"
                        )
        
        elif action == "pay" and data_parts[1] == "other":
            penalized_id = int(data_parts[2])
            payer = query.from_user
            
            if payer.id != penalized_id and db.has_rob_penalty(penalized_id):
                penalty = db.get_rob_penalty(penalized_id)
                if db.remove_money(payer.id, penalty):
                    db.remove_rob_penalty(penalized_id)
                    await query.edit_message_text(
                        f"❤️ {payer.first_name} a payé l'amende de {penalty:,} €!"
                    )
                else:
                    await query.edit_message_text(
                        f"❌ Fonds insuffisants! Besoin de {penalty:,} €"
                    )
        
        elif action == "bet" and data_parts[1] == "horse":
            chat_id = int(data_parts[2])
            horse_num = int(data_parts[3])
            horse_info = COURSE_HORSES.get(horse_num, {"name": "Inconnu", "emoji": "🐎"})
            
            await query.edit_message_text(
                f"🏇 Pour miser sur {horse_info['emoji']} *{horse_info['name']}*:\n"
                f"/cheval {horse_num} [montant]\n\n"
                f"Exemple: /cheval {horse_num} 50000",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif action == "casino":
            user_id = int(data_parts[1])
            bet_type = data_parts[2]
            amount = int(data_parts[3])
            
            if query.from_user.id != user_id:
                await query.answer("Ce n'est pas votre pari!", show_alert=True)
                return
            
            number = random.randint(0, 36)
            color = "rouge" if number % 2 == 0 and number != 0 else "noir" if number % 2 == 1 else "vert"
            
            won = False
            multiplier = 0
            
            if bet_type == "red" and color == "rouge":
                won = True
                multiplier = 2
            elif bet_type == "black" and color == "noir":
                won = True
                multiplier = 2
            elif bet_type == "even" and number % 2 == 0 and number != 0:
                won = True
                multiplier = 2
            elif bet_type == "odd" and number % 2 == 1:
                won = True
                multiplier = 2
            elif bet_type == "low" and 1 <= number <= 12:
                won = True
                multiplier = 3
            elif bet_type == "mid" and 13 <= number <= 24:
                won = True
                multiplier = 3
            elif bet_type == "high" and 25 <= number <= 36:
                won = True
                multiplier = 3
            elif bet_type == "number":
                num_keyboard = []
                for i in range(0, 37, 6):
                    row = []
                    for j in range(6):
                        num = i + j
                        if num <= 36:
                            row.append(InlineKeyboardButton(
                                str(num),
                                callback_data=f"casino_number_{user_id}_{num}_{amount}"
                            ))
                    num_keyboard.append(row)
                
                reply_markup = InlineKeyboardMarkup(num_keyboard)
                await query.edit_message_text(
                    f"🎯 Choisissez un numéro (0-36):\n"
                    f"💰 Mise: {amount:,} €\n"
                    f"Gain potentiel: x36 ({amount * 36:,} €)",
                    reply_markup=reply_markup
                )
                return
            
            if won:
                gain = amount * multiplier
                db.add_money(user_id, gain)
                result_text = (
                    f"🎉 *GAGNÉ!*\n\n"
                    f"🎲 Numéro: {number} ({color})\n"
                    f"💰 Gain: {gain:,} € (x{multiplier})"
                )
            else:
                result_text = (
                    f"💔 *PERDU!*\n\n"
                    f"🎲 Numéro: {number} ({color})\n"
                    f"💸 Perte: {amount:,} €"
                )
            
            await query.edit_message_text(result_text, parse_mode=ParseMode.MARKDOWN)
        
        elif action == "casino" and data_parts[1] == "number":
            user_id = int(data_parts[2])
            chosen_number = int(data_parts[3])
            amount = int(data_parts[4])
            
            if query.from_user.id != user_id:
                await query.answer("Ce n'est pas votre pari!", show_alert=True)
                return
            
            winning_number = random.randint(0, 36)
            
            if chosen_number == winning_number:
                multiplier = 36
                gain = amount * multiplier
                db.add_money(user_id, gain)
                result_text = (
                    f"🌟 *JACKPOT!*\n\n"
                    f"🎯 Votre numéro: {chosen_number}\n"
                    f"🎲 Gagnant: {winning_number}\n"
                    f"💰 Gain: {gain:,} € (x{multiplier})"
                )
            else:
                result_text = (
                    f"💔 *PERDU!*\n\n"
                    f"🎯 Votre numéro: {chosen_number}\n"
                    f"🎲 Gagnant: {winning_number}\n"
                    f"💸 Perte: {amount:,} €"
                )
            
            await query.edit_message_text(result_text, parse_mode=ParseMode.MARKDOWN)
    
    except Exception as e:
        logger.error(f"Erreur callback: {e}")
        await query.edit_message_text("❌ Une erreur est survenue!")

# [Gardez tout votre code ici : Database, BraquageManager, CourseManager, etc.]

# ============ DÉMARRAGE PRINCIPAL ============

# ============ SERVEUR HTTP PING ============

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Serveur HTTP minimal pour les health checks"""
    
    def do_GET(self):
        """Répond aux requêtes GET"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        response = json.dumps({
            "status": "online",
            "timestamp": datetime.now().isoformat(),
            "service": "BraquageBot",
            "uptime": "running"
        })
        self.wfile.write(response.encode())
    
    def log_message(self, format, *args):
        """Réduire les logs HTTP"""
        pass

def start_health_server():
    """Démarre le serveur de health check"""
    try:
        server = HTTPServer(('0.0.0.0', PORT), HealthCheckHandler)
        logger.info(f"🏥 Serveur health check démarré sur le port {PORT}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"❌ Erreur serveur health: {e}")

# ============ KEEP ALIVE ============

async def keep_alive_task():
    """Tâche qui maintient le bot actif"""
    while True:
        try:
            logger.info(f"💓 Heartbeat - {datetime.now().isoformat()}")
            
            # Sauvegarde périodique
            try:
                db.save()
            except:
                pass
            
            # Nettoyage des tâches expirées
            try:
                cleanup_expired_tasks()
            except:
                pass
            
        except Exception as e:
            logger.error(f"❌ Erreur keep_alive: {e}")
        
        await asyncio.sleep(300)  # Toutes les 5 minutes

def cleanup_expired_tasks():
    """Nettoie les braquages et courses expirés"""
    now = datetime.now()
    
    # Nettoyer les braquages
    for chat_id in list(braquage_manager.active_braquages.keys()):
        braquage = braquage_manager.get_braquage(chat_id)
        if braquage and braquage.get('expires_at'):
            if now > braquage['expires_at'] + timedelta(minutes=5):
                for user_id, amount in braquage['players'].items():
                    try:
                        db.add_money(user_id, amount)
                    except:
                        pass
                del braquage_manager.active_braquages[chat_id]
                logger.info(f"🧹 Braquage expiré nettoyé: chat {chat_id}")
    
    # Nettoyer les courses
    for chat_id in list(course_manager.active_courses.keys()):
        course = course_manager.active_courses.get(chat_id)
        if course and course.get('created_at'):
            if now > course['created_at'] + timedelta(minutes=COURSE_WAIT_TIME//60 + 5):
                for user_id, data in course['players'].items():
                    try:
                        db.add_money(user_id, data['bet'])
                    except:
                        pass
                del course_manager.active_courses[chat_id]
                logger.info(f"🧹 Course expirée nettoyée: chat {chat_id}")

# ============ FONCTION PRINCIPALE CORRIGÉE ============

async def run_bot(app):
    """Fonction asynchrone pour exécuter le bot"""
    try:
        # Démarrer la tâche keep-alive
        asyncio.create_task(keep_alive_task())
        
        # Initialiser et démarrer l'application
        await app.initialize()
        await app.start()
        
        logger.info("✅ Bot Telegram connecté!")
        
        # Démarrer le polling
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        logger.info("📡 Polling démarré, en attente de messages...")
        
        # Garder le bot en vie indéfiniment
        stop_event = asyncio.Event()
        
        # Gestionnaire de signal pour arrêt gracieux
        def signal_handler():
            logger.info("🛑 Signal d'arrêt reçu")
            stop_event.set()
        
        # Configurer les gestionnaires de signaux
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows ne supporte pas add_signal_handler
            pass
        
        # Attendre l'événement d'arrêt
        await stop_event.wait()
        
    except asyncio.CancelledError:
        logger.info("🛑 Tâche annulée")
    except Exception as e:
        logger.error(f"❌ Erreur dans run_bot: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Arrêter proprement
        try:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            logger.info("✅ Bot arrêté proprement")
        except:
            pass

def main() -> None:
    """Point d'entrée principal"""
    logger.info("🤖 Démarrage du Bot Braquage sur Render...")
    
    # Démarrer le serveur health check dans un thread séparé
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    logger.info(f"🏥 Health check: http://0.0.0.0:{PORT}/")
    
    try:
        # Créer l'application Telegram
        app = Application.builder().token(BOT_TOKEN).build()
        
        # Ajouter tous les handlers
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("help", cmd_help))
        app.add_handler(CommandHandler("acc", cmd_account))
        app.add_handler(CommandHandler("bank", cmd_bank))
        app.add_handler(CommandHandler("deposit", cmd_deposit))
        app.add_handler(CommandHandler("withdraw", cmd_withdraw))
        app.add_handler(CommandHandler("stats", cmd_stats))
        app.add_handler(CommandHandler("braquage", cmd_braquage))
        app.add_handler(CommandHandler("cancelbraquage", cmd_cancel_braquage))
        app.add_handler(CommandHandler("braquage_status", cmd_braquage_status))
        app.add_handler(CommandHandler("forcebraquage", cmd_force_braquage))
        app.add_handler(CommandHandler("rob", cmd_rob))
        app.add_handler(CommandHandler("paypenalty", cmd_pay_penalty))
        app.add_handler(CommandHandler("course", cmd_course))
        app.add_handler(CommandHandler("cheval", cmd_cheval))
        app.add_handler(CommandHandler("cancelcourse", cmd_cancel_course))
        app.add_handler(CommandHandler("casino", cmd_casino))
        app.add_handler(CommandHandler("slot", cmd_slot))
        app.add_handler(CommandHandler("dice", cmd_dice))
        app.add_handler(CommandHandler("classement", cmd_classement))
        app.add_handler(CallbackQueryHandler(button_callback))
        
        logger.info("✅ Handlers configurés")
        
        # Afficher le message de démarrage
        print(f"""
╔══════════════════════════════════════╗
║     🎭 BOT BRAQUAGE DÉMARRÉ 🎭     ║
╠══════════════════════════════════════╣
║  ✅ Bot Telegram actif              ║
║  🏥 Health check: port {PORT}        ║
║  💓 Keep-alive: actif               ║
║  📊 Auto-cleanup: activé            ║
╚══════════════════════════════════════╝
        """)
        
        # LANCEMENT CORRIGÉ - Utiliser asyncio.run()
        asyncio.run(run_bot(app))
        
    except KeyboardInterrupt:
        logger.info("🛑 Arrêt demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"❌ Erreur fatale: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()