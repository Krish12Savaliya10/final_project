"""Route registration package."""

from routes.admin_routes import register_routes as register_admin_routes
from routes.booking_routes import register_routes as register_booking_routes
from routes.organizer_routes import register_routes as register_organizer_routes
from routes.provider_routes import register_routes as register_provider_routes
from routes.public_routes import register_routes as register_public_routes


def register_all_routes(app):
    register_public_routes(app)
    register_admin_routes(app)
    register_organizer_routes(app)
    register_provider_routes(app)
    register_booking_routes(app)
