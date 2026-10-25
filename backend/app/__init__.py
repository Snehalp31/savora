import os
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from .api.routes import api
from .persistence import init_db, seed_reference_data, init_operational_tables

load_dotenv(Path(__file__).resolve().parents[1] / '.env')
def create_app(test_config=None):
    app = Flask(__name__)
    init_db()
    from .services.reference_data import get_products, get_locations, get_partners
    seed_reference_data(get_products(), get_locations(), get_partners())
    from .services.reference_data import get_inventory, get_sales
    init_operational_tables(get_inventory(), get_sales())
    app.config.update(test_config or {})
    origins = [origin.strip() for origin in os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174').split(',') if origin.strip()]
    CORS(app, resources={r'/api/*': {'origins': origins}})
    app.register_blueprint(api, url_prefix='/api')
    @app.get('/health')
    def health():
        return jsonify({'status':'ok','service':'savora-api','storage_mode':'sqlite','synthetic_data':True})
    @app.errorhandler(404)
    def not_found(_): return jsonify({'error':'Resource not found'}),404
    @app.errorhandler(400)
    def bad_request(e): return jsonify({'error':str(e.description)}),400
    @app.errorhandler(500)
    def internal(_): return jsonify({'error':'Unexpected server error'}),500
    return app
