import requests
import time
import random

BACKEND = 'http://127.0.0.1:5000/ingest'
PATIENT_ID = 'patient_001'

def gen_vitals():
    hr = random.randint(60, 130)
    spo2 = random.randint(85, 100)
    glucose = random.randint(80, 260)
    temp = round(random.uniform(36.0, 39.0), 1)
    return {
        'heart_rate': hr,
        'spo2': spo2,
        'glucose': glucose,
        'temp': temp
    }

if __name__ == '__main__':
    print('Starting simulator — sending vitals every 2s to', BACKEND)
    while True:
        vitals = gen_vitals()
        payload = {'patient_id': PATIENT_ID, 'vitals': vitals}
        try:
            r = requests.post(BACKEND, json=payload, timeout=3)
            print('Sent:', vitals, '->', r.json())
        except Exception as e:
            print('Error sending:', e)
        time.sleep(2)
