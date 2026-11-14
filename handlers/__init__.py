from . import common, moderation, rules, roles, callbacks, trainee

def register_all(dp):
    dp.include_router(common.router)
    dp.include_router(trainee.router)
    dp.include_router(moderation.router)
    dp.include_router(rules.router)
    dp.include_router(roles.router)
    dp.include_router(callbacks.router)
