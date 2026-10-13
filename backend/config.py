import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "local-demo-secret-change-before-deploy")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(os.path.dirname(__file__), "campus_energy.db"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ENERGY_THRESHOLD_WATTS = float(os.getenv("ENERGY_THRESHOLD_WATTS", "50"))
    WASTE_DURATION_SECONDS = int(os.getenv("WASTE_DURATION_SECONDS", "30"))
    ELECTRICITY_TARIFF_INR = float(os.getenv("ELECTRICITY_TARIFF_INR", "8"))
    MAX_READING_GAP_SECONDS = int(os.getenv("MAX_READING_GAP_SECONDS", "900"))
    ALLOW_DEMO_RESET = os.getenv(
        "ALLOW_DEMO_RESET",
        "false" if os.getenv("FLASK_ENV") == "production" else "true",
    ).lower() == "true"
