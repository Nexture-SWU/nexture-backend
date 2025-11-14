import os
import firebase_admin
from firebase_admin import credentials, firestore, messaging
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(BASE_DIR, ".env"))

cred = credentials.Certificate(os.environ["FIREBASE_CREDENTIAL_PATH"])

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()