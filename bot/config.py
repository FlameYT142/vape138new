import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
LOG_CHAT_ID = int(os.getenv("LOG_CHAT_ID"))
DB_PATH = os.getenv("DB_PATH", "bot.db")
TZ = os.getenv("TZ", "Asia/Irkutsk")

# Чаты
CHAT_BRATSK = -1003795988356
CHAT_VIHOREVKA = -1003378812518
CHAT_TRAINEE = -1003552769110
BARAHOLKA_CHATS = {CHAT_BRATSK, CHAT_VIHOREVKA}

# Доступ
OWNER_IDS = [8494622112]
TECH_ADMIN_IDS = [1302410770]

ROLES = {
    "owner":        {"level": 11,   "label": "Владелец"},
    "tech_admin":   {"level": 10.5, "label": "Тех-админ"},
    "deputy_owner": {"level": 10,   "label": "Зам владельца"},
    "head":         {"level": 9,    "label": "Руководитель"},
    "deputy_head":  {"level": 8,    "label": "Зам. Руководителя"},
    "manager":      {"level": 7,    "label": "Менеджер"},
    "senior_mod":   {"level": 6,    "label": "Старший модератор"},
    "moderator":    {"level": 5,    "label": "Модератор"},
    "trainee":      {"level": 4,    "label": "Стажёр"},
    "blat":         {"level": 3,    "label": "BLAT LIST"},
    "partner":      {"level": 2,    "label": "Сотрудничество"},
    "vip":          {"level": 1,    "label": "VIP пользователь"},
    "member":       {"level": 0,    "label": "Участник"},
}

STATUS_ROLES = {"vip", "blat", "partner"}
OWNER_ONLY_TARGETS = {"owner", "deputy_owner"}

def role_level(role: str) -> float:
    return ROLES.get(role, ROLES["member"])["level"]

def role_label(role: str) -> str:
    return ROLES.get(role, ROLES["member"])["label"]

def is_tech_admin(user_id: int) -> bool:
    return user_id in TECH_ADMIN_IDS
