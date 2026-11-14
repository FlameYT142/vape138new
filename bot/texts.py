ERR_ARGS = "❌ Вы не до конца заполнили команду, недостаточно аргументов!"
ERR_DM_ONLY = "❌ Эта команда доступна только в личных сообщениях с ботом."
ERR_NO_RIGHTS = "❌ У вас недостаточно прав для этой команды."
ERR_RULE_NOT_FOUND = "❌ Правило {code} не найдено."
ERR_RULE_INACTIVE = "❌ Правило {code} временно неактивно."
ERR_OWNER_IMMUNE = "❌ Владелец неприкосновенен."
ERR_IMMUNITY = "❌ У пользователя статус {status} — иммунитет.\n⚠️ Заявка на наказание отправлена на рассмотрение администрации"
ERR_NEED_RULE = "❌ Укажите номер правила: `.мут @user 1.1`"
ERR_TARGET = "❌ Не удалось определить пользователя. Ответьте реплаем или укажите @username."
ERR_TRAINEE_CHAT_ONLY_WARN = "❌ В чате стажёров доступна только команда `.варн`."
MSG_APPEAL_SENT = "⚠️ Ваша заявка отправлена старшему модератору на рассмотрение."
MSG_APPEAL_VIP = "⚠️ Ваша заявка отправлена старшему модератору на рассмотрение. *(после одобрения ÷2)*"

START_TEXT = ("👋 Привет! Я бот-модератор «Vape Барахолка».\n"
              "Нажми кнопку ниже, чтобы посмотреть правила.")

def mute_report(username, duration_text, rule_code, rule_text, moderator):
    return (f"🔇 @{username} лишается права слова на {duration_text}\n"
            f"💬 Причина: Правило {rule_code} — {rule_text}\n"
            f"👮‍ Модератор: @{moderator}")

def ban_report(username, rule_code, rule_text, moderator):
    return (f"🔨 @{username} забанен навсегда\n"
            f"💬 Причина: Правило {rule_code} — {rule_text}\n"
            f"👮‍ Модератор: @{moderator}")

def unmute_report(username, moderator):
    return f"✅ @{username} размучен. Ограничения сняты.\n👮‍ Модератор: @{moderator}"

def kick_report(username, reason, moderator):
    return (f"👢 @{username} удалён из чата (кик).\n"
            f"💬 Причина: {reason}\n"
            f"👮‍ Модератор: @{moderator}")

def warn_report(username, count, max_count, moderator, reason):
    return (f"❗️ @{username} получает предупреждение ({count}/{max_count})\n"
            f"⏱️ Будет снято через 30 дней\n"
            f"👺 Модератор: @{moderator}\n"
            f"💬 Причина: {reason}")

def role_grant(username, role_label_text, level, actor):
    return f"✅ @{username} назначен(а) {role_label_text} [{level}]\n👮‍ Выдал: @{actor}"

def role_demote(username, role_label_text, level):
    return f"✅ @{username} разжалован(а) до {role_label_text} [{level}]"

TRAINEE_FAILED = ("😔 К сожалению, @{username}, ваша стажировка оказалась неудачной.\n"
                  "Вы набрали 3/3 предупреждения. Приходите в следующий раз!")

MSG_BOT_DELETE_REMINDER = "📩 Хэй! Не забудь удалить бота, которого добавил @{username}, по причине (правило 19), заботимся о вас! :) ❤️"
MSG_POST_DELETE_REMINDER = "📩 Хэй! Не забудь удалить пост нарушителя @{username} по причине (правило {rule}), заботимся о вас! :) ❤️"