
import mysql.connector

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="SKYdcn@0604",
        database="concert_reservation"
    )
