"""Path-restricted ASGI profile for the dedicated Commons listener."""
from app.main import app as beast_application
from app.kernel.commons.service_boundary import CommonsPathBoundary


app = CommonsPathBoundary(beast_application)
