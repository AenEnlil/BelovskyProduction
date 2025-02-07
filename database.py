import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv('MONGO_URL'))
db = client[os.getenv('MONGO_DB_NAME')]

SURVEYS = 'surveys'


def get_collection(collection_name):
    return db[collection_name]


