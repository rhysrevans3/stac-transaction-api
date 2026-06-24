from settings import settings

if settings.authorizer == "egi":
    from authorizer.egi_authorizer import EGIAuthorizer as Auth
else:
    from authorizer.globus_authorizer import GlobusAuthorizer as Auth

Authorizer = Auth
