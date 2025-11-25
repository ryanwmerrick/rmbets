import time
from datetime import date

today= date.today()


iso_date = today.isoformat() + "T16:00:00Z"

print(iso_date)